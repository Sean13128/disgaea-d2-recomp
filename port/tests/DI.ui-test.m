// Real AppKit menu against settings; no assets, saves, or guest RAM.
#include "../src/d2_settings.m"
#include <assert.h>
#include "../src/d2_diagnostics.m"
static NSMutableArray* requestTimes;
static NSMutableArray* completions;
void d2_flags_diagnostics_snapshot(void (^completion)(NSDictionary*))
{
    assert(NSThread.isMainThread);
    [requestTimes addObject:@(NSProcessInfo.processInfo.systemUptime)];
    [completions addObject:[completion copy]];
}
static void spin(double seconds)
{ [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:seconds]]; }
static NSTextField* field(NSView* view, NSString* identifier)
{
    if ([view isKindOfClass:NSTextField.class] && [view.accessibilityIdentifier isEqual:identifier]) return (NSTextField*)view;
    for (NSView* child in view.subviews) { NSTextField* found = field(child, identifier); if (found) return found; }
    return nil;
}
static NSTableView* thread_table(NSView* view)
{
    if ([view isKindOfClass:NSTableView.class]) return (NSTableView*)view;
    for (NSView* child in view.subviews) { NSTableView* found = thread_table(child); if (found) return found; }
    return nil;
}
void rsx_metal_backend_configure(unsigned scale, unsigned filter, int stretch, int vsync, unsigned cap)
{ (void)scale; (void)filter; (void)stretch; (void)vsync; (void)cap; }
void cellAudioHostSetGain(float gain, int muted) { (void)gain; (void)muted; }
float cellAudioHostGetGain(void) { return 1; }
int main(void)
{
    @autoreleasepool {
        [NSApplication sharedApplication];
        requestTimes = [NSMutableArray new]; completions = [NSMutableArray new];
        s_settings = [defaults() mutableCopy]; s_controller = [D2SettingsController new];
        s_window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 320, 180)
            styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
        install_menu();
        NSMenu* game = [NSApp.mainMenu itemWithTitle:@"Game"].submenu;
        NSMenuItem* diagnostics = [game itemWithTitle:@"Diagnostics…"];
        assert(diagnostics && "Game menu must expose Diagnostics…");
        assert(diagnostics.target && diagnostics.action);
        assert([s_controller validateMenuItem:diagnostics] && diagnostics.state == NSControlStateValueOff);
        [game performActionForItemAtIndex:[game indexOfItem:diagnostics]];
        assert(d2_diagnostics_visible());
        assert([s_controller validateMenuItem:diagnostics] && diagnostics.state == NSControlStateValueOn);
        NSWindow* window = nil;
        for (NSWindow* candidate in NSApp.windows) if ([candidate.title isEqual:@"Diagnostics"]) window = candidate;
        assert(window && window != s_window && "separate native Diagnostics window must open");
        assert(window.isVisible && !window.releasedWhenClosed);
        assert(requestTimes.count == 1 && "visible Diagnostics must request the cached snapshot");
        spin(1.1);
        assert(requestTimes.count == 1); // bounded: no second request while completion is pending
        [window performClose:nil];
        assert(!d2_diagnostics_visible());
        assert(![s_diagnostics valueForKey:@"timer"]);
        spin(1.1); assert(requestTimes.count == 1);
        [game performActionForItemAtIndex:[game indexOfItem:diagnostics]];
        assert(window.isVisible && d2_diagnostics_visible());
        assert(requestTimes.count == 1); // reopening cannot duplicate an outstanding request
        void (^oldCompletion)(NSDictionary*) = completions[0];
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ oldCompletion(@{}); });
        spin(0.1);
        spin(1.1); assert(requestTimes.count == 2);
        assert([requestTimes[1] doubleValue] - [requestTimes[0] doubleValue] >= 1);
        [game performActionForItemAtIndex:[game indexOfItem:diagnostics]];
        assert(!window.isVisible && !d2_diagnostics_visible());
        assert(![s_diagnostics valueForKey:@"timer"]);
        unsigned hidden = (unsigned)requestTimes.count;
        spin(1.1); assert(requestTimes.count == hidden);
        printf("[DI UI] visible requests=%lu; outstanding coalescing; closed timer=nil; hidden requests=0 over 2×1.1s: PASS\n", requestTimes.count);
        puts("[DI UI] native Game→Diagnostics… action/checkmark; separate window, close/reopen/toggle: PASS");
        NSTextField* frames = field(window.contentView, @"diagnostics.frames");
        NSTextField* intervals = field(window.contentView, @"diagnostics.intervals");
        assert(frames && intervals && "native labelled telemetry fields must exist");
        assert([frames.stringValue containsString:@"warmup"]);
        NSDictionary* telemetry = @{ @"guest_frame_status": @"available", @"display_frame_status": @"available",
            @"guest_fps_1s": @60, @"guest_fps_10s": @59.5, @"display_fps_1s": @30, @"display_fps_10s": @29.5,
            @"window_1s": @1, @"window_10s": @10, @"frame_window_1s_complete": @YES, @"frame_window_10s_complete": @YES,
            @"guest_latest_interval_ms": @16.7, @"display_latest_interval_ms": @33.3,
            @"guest_active_interval_ms": @12000, @"display_active_interval_ms": @200,
            @"worst_frame_ms_10s": @12000, @"worst_display_frame_ms_10s": @200,
            @"cpu_status": @"warmup", @"threads": @[] };
        [s_diagnostics performSelector:NSSelectorFromString(@"consume:") withObject:telemetry];
        assert([frames.stringValue containsString:@"Guest flips: 60.0 FPS"]);
        assert([frames.stringValue containsString:@"Display presentations: 30.0 FPS"]);
        assert([frames.stringValue containsString:@"1.00 s"] && [frames.stringValue containsString:@"10.00 s"]);
        assert([intervals.stringValue containsString:@"16.7 ms"] && [intervals.stringValue containsString:@"12000.0 ms"]);
        assert([intervals.stringValue containsString:@"ongoing"] && [intervals.stringValue containsString:@"may exceed window"]);
        [s_diagnostics performSelector:NSSelectorFromString(@"consume:") withObject:@{}];
        assert([frames.stringValue containsString:@"unavailable"] && ![frames.stringValue containsString:@"0.0 FPS"]);
        assert([intervals.stringValue containsString:@"unavailable"]);
        puts("[DI UI] distinct FPS, explicit actual windows, completed/ongoing ms intervals, unavailable (not zero): PASS");
        NSTableView* table = thread_table(window.contentView);
        assert(table && "per-thread native CPU table must exist");
        NSTextField* activity = field(window.contentView, @"diagnostics.activity");
        NSTextField* limits = field(window.contentView, @"diagnostics.limits");
        assert(activity && limits);
        assert([activity.stringValue containsString:@"warmup"]);
        assert([limits.stringValue containsString:@"single loaded guest"]);
        assert([limits.stringValue containsString:@"guest PID/state unavailable"]);
        assert([limits.stringValue containsString:@"host-thread name based"]);
        assert([limits.stringValue containsString:@"not guest instructions"]);
        assert([limits.stringValue containsString:@"submitted drawable presents"]);
        assert([limits.stringValue containsString:@"not scan-out"]);
        assert([diag_role(@"RSX render") isEqual:@"Host render candidate"] && "port frame-clock names RSX render explicitly");
        NSArray* rows = @[
            @{ @"id": @7, @"name": @"PPU main", @"cpu_status": @"available", @"cpu_percent": @50 },
            @{ @"id": @8, @"name": @"NisGraphicsSpu_Group", @"cpu_status": @"available", @"cpu_percent": @10 },
            @{ @"id": @9, @"name": @"_synth2 Group", @"cpu_status": @"warmup", @"cpu_percent": NSNull.null },
            @{ @"id": @10, @"name": @"RSX submit", @"cpu_status": @"available", @"cpu_percent": @3 },
            @{ @"id": @11, @"name": @"not-PPU-or-audio", @"cpu_status": @"unknown", @"cpu_percent": NSNull.null } ];
        NSDictionary* cpu = @{ @"cpu_status": @"available", @"cpu_window_seconds": @2,
            @"cpu_sample_age_seconds": @0.2, @"threads": rows };
        [s_diagnostics performSelector:NSSelectorFromString(@"consume:") withObject:cpu];
        assert(table.numberOfRows == 5);
        NSTableColumn* idColumn = [table tableColumnWithIdentifier:@"id"];
        NSTableColumn* cpuColumn = [table tableColumnWithIdentifier:@"cpu"];
        NSTableColumn* roleColumn = [table tableColumnWithIdentifier:@"role"];
        assert(idColumn && cpuColumn && roleColumn);
        id<NSTableViewDataSource> source = table.dataSource;
        assert(([[source tableView:table objectValueForTableColumn:idColumn row:0] isEqual:@"7"]));
        assert(([[source tableView:table objectValueForTableColumn:cpuColumn row:0] isEqual:@"50.0 %"]));
        assert(([[source tableView:table objectValueForTableColumn:cpuColumn row:2] isEqual:@"warmup"]));
        assert(([[source tableView:table objectValueForTableColumn:cpuColumn row:4] isEqual:@"unknown"]));
        assert(([[source tableView:table objectValueForTableColumn:roleColumn row:4] isEqual:@"Other / unknown"]));
        assert([activity.stringValue containsString:@"PPU"] && [activity.stringValue containsString:@"SPU"]);
        assert([activity.stringValue containsString:@"Host render"] && [activity.stringValue containsString:@"Host audio: unavailable"]);
        assert([activity.stringValue containsString:@"2.00 s"] && [activity.stringValue containsString:@"0.20 s"]);
        [table selectRowIndexes:[NSIndexSet indexSetWithIndex:1] byExtendingSelection:NO];
        NSArray* changed = @[rows[1], @{ @"id": @11, @"name": @"renamed", @"cpu_status": @"unavailable", @"cpu_percent": NSNull.null }];
        [s_diagnostics performSelector:NSSelectorFromString(@"consume:") withObject:@{ @"cpu_status": @"unavailable", @"threads": changed }];
        assert(table.numberOfRows == 2 && table.selectedRow == 0); // same host ID despite reordering/removal
        assert(([[source tableView:table objectValueForTableColumn:cpuColumn row:1] isEqual:@"unavailable"]));
        assert([activity.stringValue containsString:@"unavailable"]);
        puts("[DI UI] stable host ID rows, CPU statuses, selection-preserving update, role limits and guest/audio unknowns: PASS");
        [s_diagnostics consume:cpu];
        for (NSTextField* text in @[frames, intervals, activity, limits]) {
            NSSize required = [text.cell cellSizeForBounds:NSMakeRect(0, 0, text.bounds.size.width, 10000)];
            assert(required.height <= text.bounds.size.height && "diagnostic labels must not clip attribution/units/unknowns");
        }
        d2_diagnostics_toggle();
        assert(window.isVisible);
        ps3_host_window_created(NULL);
        assert(!window.isVisible && !s_diagnostics.timer && "game teardown must close Diagnostics and stop polling");
        puts("[DI UI] game-window teardown stops diagnostics: PASS");
    }
    return 0;
}
