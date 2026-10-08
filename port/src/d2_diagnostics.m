/* Separate, read-only native troubleshooting UI. All AppKit stays on main. */
#import <AppKit/AppKit.h>
#include <assert.h>
#include "d2_diagnostics.h"
#include "d2_flags.h"

static NSString* diag_metric(id number, NSString* unit)
{
    return [number isKindOfClass:NSNumber.class] && isfinite([number doubleValue]) ?
        [NSString stringWithFormat:@"%.1f %@", [number doubleValue], unit] : @"unavailable";
}
static NSTextField* diag_label(NSView* parent, NSString* identifier, NSString* text, NSRect frame)
{
    NSTextField* label = [NSTextField wrappingLabelWithString:text];
    label.frame = frame; label.accessibilityIdentifier = identifier;
    label.selectable = YES; label.font = [NSFont monospacedDigitSystemFontOfSize:12 weight:NSFontWeightRegular];
    label.autoresizingMask = NSViewWidthSizable | NSViewMinYMargin;
    [parent addSubview:label]; return label;
}

/* Exact names from SDK entry points and D2 group-create logs, NOT a registry.
 * Arbitrary substring matches must never create guest identities. */
static NSString* diag_role(NSString* name)
{
    if ([name isEqual:@"PPU main"]) return @"PPU candidate";
    if ([@[@"NisGraphicsSpu_Group", @"_synth2 Group"] containsObject:name]) return @"SPU candidate";
    if ([@[@"RSX render", @"RSX submit", @"RSX copy"] containsObject:name]) return @"Host render candidate";
    return @"Other / unknown";
}
static NSString* diag_usage(NSArray* rows, NSString* role)
{
    NSUInteger observed = 0, measured = 0; double total = 0;
    for (NSDictionary* row in rows) if ([diag_role(row[@"name"]) isEqual:role]) {
        observed++;
        if ([row[@"cpu_status"] isEqual:@"available"] && [row[@"cpu_percent"] isKindOfClass:NSNumber.class] && isfinite([row[@"cpu_percent"] doubleValue])) {
            measured++; total += [row[@"cpu_percent"] doubleValue];
        }
    }
    if (!observed) return @"unavailable (no named candidates observed)";
    return [NSString stringWithFormat:@"%@ subtotal · %lu measured / %lu observed%@", measured ? diag_metric(@(total), @"%") : @"unavailable",
        measured, observed, measured < observed ? @" · remaining CPU warmup/unavailable/unknown" : @""];
}

@interface D2DiagnosticsController : NSObject <NSWindowDelegate, NSTableViewDataSource>
@property(strong) NSWindow* window;
@property(strong) NSTextField* frames;
@property(strong) NSTextField* intervals;
@property(strong) NSTextField* activity;
@property(strong) NSTableView* table;
@property(copy) NSArray* rows;
@property(strong) NSTimer* timer;
@property BOOL pending;
@property NSUInteger generation;
@property double lastRequest;
- (void)poll;
- (void)start;
- (void)consume:(NSDictionary*)value;
@end
static D2DiagnosticsController* s_diagnostics;
@implementation D2DiagnosticsController
- (void)consume:(NSDictionary*)value
{
    assert(NSThread.isMainThread);
    NSMutableArray* fps = [NSMutableArray new], *intervals = [NSMutableArray new];
    for (NSString* stream in @[@"guest", @"display"]) {
        NSString* title = [stream isEqual:@"guest"] ? @"Guest flips" : @"Display presentations";
        BOOL available = [value[[stream stringByAppendingString:@"_frame_status"]] isEqual:@"available"];
        NSString* one = available ? diag_metric(value[[stream stringByAppendingString:@"_fps_1s"]], @"FPS") : @"unavailable";
        NSString* ten = available ? diag_metric(value[[stream stringByAppendingString:@"_fps_10s"]], @"FPS") : @"unavailable";
        [fps addObject:[NSString stringWithFormat:@"%@: %@ (%.2f s) / %@ (%.2f s)%@", title, one,
            [value[@"window_1s"] doubleValue], ten, [value[@"window_10s"] doubleValue],
            [value[@"frame_window_1s_complete"] boolValue] && [value[@"frame_window_10s_complete"] boolValue] ? @"" : @" · bounded ring: rates/maxima may be lower bounds"]];
        NSString* worstKey = [stream isEqual:@"guest"] ? @"worst_frame_ms_10s" : @"worst_display_frame_ms_10s";
        [intervals addObject:[NSString stringWithFormat:@"%@: latest completed %@ · ongoing age %@ · max %@", title,
            diag_metric(value[[stream stringByAppendingString:@"_latest_interval_ms"]], @"ms"),
            diag_metric(value[[stream stringByAppendingString:@"_active_interval_ms"]], @"ms"),
            available ? diag_metric(value[worstKey], @"ms") : @"unavailable"]];
    }
    _frames.stringValue = [fps componentsJoinedByString:@"\n"];
    _intervals.stringValue = [[intervals componentsJoinedByString:@"\n"] stringByAppendingFormat:
        @"\nMax: completed intervals ending in last %.2f s + ongoing age (may exceed window). Latest may be unavailable after ring eviction.", [value[@"window_10s"] doubleValue]];
    id selected = _table.selectedRow >= 0 && (NSUInteger)_table.selectedRow < _rows.count ? _rows[_table.selectedRow][@"id"] : nil;
    _rows = [value[@"threads"] copy] ?: @[];
    [_table reloadData];
    [_table deselectAll:nil];
    for (NSUInteger i = 0; selected && i < _rows.count; i++) if ([_rows[i][@"id"] isEqual:selected]) {
        [_table selectRowIndexes:[NSIndexSet indexSetWithIndex:i] byExtendingSelection:NO]; break;
    }
    NSString* age = [value[@"cpu_sample_age_seconds"] isKindOfClass:NSNumber.class] ?
        [NSString stringWithFormat:@"%.2f s", [value[@"cpu_sample_age_seconds"] doubleValue]] : @"unavailable";
    NSString* window = [value[@"cpu_window_seconds"] doubleValue] > 0 ?
        [NSString stringWithFormat:@"%.2f s", [value[@"cpu_window_seconds"] doubleValue]] : @"unavailable";
    _activity.stringValue = [NSString stringWithFormat:
        @"CPU: %@ · interval %@ · cached sample age %@ (stale >3 s → unavailable)\nPPU name candidates: %@\nSPU name candidates (graphics + synth2): %@\nHost render name candidates: %@\nHost audio: unavailable (mixer unnamed; device worker mapping not exported)\nOther / unknown (may include guest PPU, render, audio, OS): %@",
        value[@"cpu_status"] ?: @"warmup", window, age, diag_usage(_rows, @"PPU candidate"), diag_usage(_rows, @"SPU candidate"),
        diag_usage(_rows, @"Host render candidate"), diag_usage(_rows, @"Other / unknown")];
}
- (NSInteger)numberOfRowsInTableView:(NSTableView*)table { (void)table; return _rows.count; }
- (id)tableView:(NSTableView*)table objectValueForTableColumn:(NSTableColumn*)column row:(NSInteger)index
{
    (void)table;
    if (index < 0 || (NSUInteger)index >= _rows.count) return @"";
    NSDictionary* row = _rows[index];
    if ([column.identifier isEqual:@"id"]) return [row[@"id"] description];
    if ([column.identifier isEqual:@"name"]) return row[@"name"];
    if ([column.identifier isEqual:@"role"]) return diag_role(row[@"name"]);
    return [row[@"cpu_status"] isEqual:@"available"] ? diag_metric(row[@"cpu_percent"], @"%") : row[@"cpu_status"] ?: @"unknown";
}
- (void)windowWillClose:(NSNotification*)note
{
    (void)note; assert(NSThread.isMainThread);
    [_timer invalidate]; _timer = nil; _generation++;
}
- (void)poll
{
    assert(NSThread.isMainThread);
    if (!_window.isVisible || _window.isMiniaturized) return;
    double now = NSProcessInfo.processInfo.systemUptime;
    if (_pending || now - _lastRequest < 1) return;
    _lastRequest = now; _pending = YES;
    NSUInteger generation = _generation;
    d2_flags_diagnostics_snapshot(^(NSDictionary* value) {
        dispatch_async(dispatch_get_main_queue(), ^{
            self.pending = NO;
            if (generation != self.generation || !self.window.isVisible) return;
            [self consume:value];
        });
    });
}
- (void)start
{
    assert(NSThread.isMainThread);
    if (_timer) return;
    __weak D2DiagnosticsController* weakSelf = self;
    _timer = [NSTimer timerWithTimeInterval:1 repeats:YES block:^(NSTimer* timer) { (void)timer; [weakSelf poll]; }];
    _timer.tolerance = 0.1;
    [NSRunLoop.mainRunLoop addTimer:_timer forMode:NSRunLoopCommonModes];
    [self poll];
}
@end

int d2_diagnostics_visible(void)
{
    assert(NSThread.isMainThread);
    return s_diagnostics.window.isVisible;
}
void d2_diagnostics_close(void)
{
    assert(NSThread.isMainThread);
    [s_diagnostics.window close];
}
void d2_diagnostics_toggle(void)
{
    assert(NSThread.isMainThread);
    if (d2_diagnostics_visible()) { d2_diagnostics_close(); return; }
    if (!s_diagnostics) {
        s_diagnostics = [D2DiagnosticsController new];
        s_diagnostics.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 980, 760)
            styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
            backing:NSBackingStoreBuffered defer:NO];
        s_diagnostics.window.title = @"Diagnostics";
        s_diagnostics.window.releasedWhenClosed = NO;
        s_diagnostics.window.delegate = s_diagnostics;
        s_diagnostics.window.collectionBehavior = NSWindowCollectionBehaviorFullScreenAuxiliary;
        s_diagnostics.window.contentMinSize = NSMakeSize(980, 700);
        NSView* content = s_diagnostics.window.contentView;
        s_diagnostics.frames = diag_label(content, @"diagnostics.frames", @"Frame telemetry: warmup", NSMakeRect(16, 664, 948, 66));
        s_diagnostics.intervals = diag_label(content, @"diagnostics.intervals", @"Frame intervals: warmup", NSMakeRect(16, 554, 948, 100));
        s_diagnostics.activity = diag_label(content, @"diagnostics.activity", @"CPU: warmup", NSMakeRect(16, 420, 948, 124));
        NSTextField* limits = diag_label(content, @"diagnostics.limits",
            @"Disgaea D2: single loaded guest; active guest PID/state unavailable (no runtime snapshot API).\nAttribution is host-thread name based, not guest identities: PPU main, two known D2 SPU group names, RSX render/submit/copy only. Other PPU workers may be unknown; names can be stale or reused.\nCPU = host user+system time / wall interval; 100% = one core, not guest instructions or GPU time. IDs are stable Mach host thread IDs, not PS3 IDs. Rows are successful cached observations, not instantaneous running/waiting state.\nGuest flips count accepted guest submissions; display counts submitted drawable presents, not scan-out or GPU completion.\nVisible polling ≤1 Hz; close stops requests. Existing F2 telemetry sampler remains unchanged.", NSMakeRect(16, 12, 948, 148));
        limits.autoresizingMask = NSViewWidthSizable;
        s_diagnostics.table = [[NSTableView alloc] initWithFrame:NSZeroRect];
        s_diagnostics.table.accessibilityLabel = @"Host thread CPU activity";
        s_diagnostics.table.dataSource = s_diagnostics; s_diagnostics.table.rowHeight = 22;
        NSArray* columns = @[@[@"id", @"Host thread ID", @140], @[@"name", @"Host thread name", @340],
            @[@"role", @"Name-based attribution (candidate only)", @300], @[@"cpu", @"Host CPU / status", @160]];
        for (NSArray* spec in columns) {
            NSTableColumn* column = [[NSTableColumn alloc] initWithIdentifier:spec[0]];
            column.title = spec[1]; column.width = [spec[2] doubleValue];
            [s_diagnostics.table addTableColumn:column];
        }
        NSScrollView* scroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(16, 168, 948, 236)];
        scroll.documentView = s_diagnostics.table; scroll.hasVerticalScroller = YES; scroll.hasHorizontalScroller = YES;
        scroll.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
        [content addSubview:scroll];
        [s_diagnostics.window center];
    }
    [s_diagnostics.window makeKeyAndOrderFront:nil];
    [s_diagnostics start];
}
