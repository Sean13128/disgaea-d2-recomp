/* Player issue bookmarks. AppKit only queues requests and displays small UI;
 * Mach sampling, JSON, readback and disk writes run off the main thread. */
#import <AppKit/AppKit.h>
#include <mach/mach.h>
#include <pthread.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include "d2_flags.h"
#include "rsx_metal_backend.h"

static dispatch_queue_t s_flags_queue;
static dispatch_source_t s_cpu_timer;
static double s_launch, s_scale = 1;
static unsigned s_cap = 60, s_number;
static NSString* s_session;
static NSMutableArray* s_cpu_history;
static NSWindow* s_flags_window;
static NSTextField* s_toast;
static NSPanel* s_note_panel;
static NSTextField* s_note;
static NSDictionary* s_note_identity;
static pthread_mutex_t s_frames_lock = PTHREAD_MUTEX_INITIALIZER;
static struct { double time, guest_ms, display_ms; int guest, display; } s_frames[4096];
static unsigned s_frame_count;
static double s_last_guest, s_last_display;

static double monotonic(void)
{
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* Same events as AL's Show FPS counters, including failed/nil drawables. */
void ps3_host_frame_event(double now, int guest, int display)
{
    pthread_mutex_lock(&s_frames_lock);
    unsigned i = s_frame_count++ % 4096;
    s_frames[i].time = now; s_frames[i].guest = guest; s_frames[i].display = display;
    s_frames[i].guest_ms = guest && s_last_guest ? (now - s_last_guest) * 1000 : 0;
    s_frames[i].display_ms = display && s_last_display ? (now - s_last_display) * 1000 : 0;
    if (guest) s_last_guest = now;
    if (display) s_last_display = now;
    pthread_mutex_unlock(&s_frames_lock);
}

static NSDictionary* frame_stats(double now)
{
    unsigned g1 = 0, d1 = 0, g10 = 0, d10 = 0;
    double worst = 0, display_worst = 0;
    double last_guest = 0, last_display = 0;
    pthread_mutex_lock(&s_frames_lock);
    for (unsigned j = 0; j < MIN(s_frame_count, 4096); j++) {
        unsigned i = (s_frame_count - 1 - j) % 4096;
        double age = now - s_frames[i].time;
        if (age < 0) continue;
        if (!last_guest && s_frames[i].guest) last_guest = s_frames[i].time;
        if (!last_display && s_frames[i].display) last_display = s_frames[i].time;
        if (age >= 10) continue;
        g10 += s_frames[i].guest; d10 += s_frames[i].display;
        if (age < 1) { g1 += s_frames[i].guest; d1 += s_frames[i].display; }
        worst = MAX(worst, s_frames[i].guest_ms);
        display_worst = MAX(display_worst, s_frames[i].display_ms);
    }
    // Include a currently stalled frame, even when no new flips arrive.
    if (last_guest) worst = MAX(worst, (now - last_guest) * 1000);
    if (last_display) display_worst = MAX(display_worst, (now - last_display) * 1000);
    BOOL available = s_frame_count != 0;
    pthread_mutex_unlock(&s_frames_lock);
    double one = MAX(0.001, MIN(1, now - s_launch)), ten = MAX(0.001, MIN(10, now - s_launch));
    return @{ @"guest_fps_1s": @(g1 / one), @"display_fps_1s": @(d1 / one),
        @"guest_fps_10s": @(g10 / ten), @"display_fps_10s": @(d10 / ten),
        @"worst_frame_ms_10s": @(worst), @"worst_display_frame_ms_10s": @(display_worst),
        @"window_1s": @(one), @"window_10s": @(ten), @"frame_metrics_available": @(available) };
}

static NSString* flags_folder(void)
{
    const char* hdd = getenv("PS3_HDD0_ROOT");
    NSString* parent = hdd && *hdd ? [[NSString stringWithUTF8String:hdd].stringByStandardizingPath
        stringByDeletingLastPathComponent] : [NSHomeDirectory() stringByAppendingPathComponent:
        @"Library/Application Support/DisgaeaD2Recomp"];
    return [parent stringByAppendingPathComponent:@"flags"];
}

/* One writer queue, one JSON object per line. Notes are append-only events so
 * the initial bookmark survives a crash or an unfinished text field. */
static BOOL append_record(NSString* folder, NSDictionary* record)
{
    NSError* error = nil;
    NSData* data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:&error];
    if (!data || ![NSFileManager.defaultManager createDirectoryAtPath:folder
        withIntermediateDirectories:YES attributes:nil error:&error]) {
        fprintf(stderr, "[D2 flag] write failed: %s\n", error.localizedDescription.UTF8String); return NO;
    }
    NSString* path = [folder stringByAppendingPathComponent:@"flags.jsonl"];
    int fd = open(path.fileSystemRepresentation, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd < 0) { perror("[D2 flag] open"); return NO; }
    NSMutableData* line = [data mutableCopy]; [line appendBytes:"\n" length:1];
    const char* bytes = line.bytes; size_t left = line.length;
    while (left) {
        ssize_t n = write(fd, bytes, left);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        bytes += n; left -= n;
    }
    BOOL ok = !left && fsync(fd) == 0;
    if (close(fd)) ok = NO;
    if (!ok) perror("[D2 flag] append");
    // Emit the identical record as a searchable block in the main log.
    fprintf(stderr, "[D2 flag] BEGIN\n%.*s\n[D2 flag] END saved=%d\n",
        (int)data.length, (const char*)data.bytes, ok);
    return ok;
}

static NSDictionary* cpu_sample(void)
{
    thread_act_array_t threads = NULL; mach_msg_type_number_t count = 0;
    NSMutableDictionary* entries = [NSMutableDictionary new];
    kern_return_t result = task_threads(mach_task_self(), &threads, &count);
    if (result == KERN_SUCCESS) {
        for (unsigned i = 0; i < count; i++) {
            thread_basic_info_data_t basic;
            thread_identifier_info_data_t identity;
            thread_extended_info_data_t extended;
            mach_msg_type_number_t n = THREAD_BASIC_INFO_COUNT;
            kern_return_t b = thread_info(threads[i], THREAD_BASIC_INFO, (thread_info_t)&basic, &n);
            n = THREAD_IDENTIFIER_INFO_COUNT;
            kern_return_t id_result = thread_info(threads[i], THREAD_IDENTIFIER_INFO, (thread_info_t)&identity, &n);
            n = THREAD_EXTENDED_INFO_COUNT;
            kern_return_t e = thread_info(threads[i], THREAD_EXTENDED_INFO, (thread_info_t)&extended, &n);
            if (b == KERN_SUCCESS && id_result == KERN_SUCCESS) {
                double seconds = basic.user_time.seconds + basic.user_time.microseconds * 1e-6 +
                    basic.system_time.seconds + basic.system_time.microseconds * 1e-6;
                NSString* name = e == KERN_SUCCESS ? [NSString stringWithUTF8String:extended.pth_name] : nil;
                entries[@(identity.thread_id)] = @{ @"seconds": @(seconds), @"name": name.length ? name : @"unnamed" };
            }
            mach_port_deallocate(mach_task_self(), threads[i]);
        }
        vm_deallocate(mach_task_self(), (vm_address_t)threads, count * sizeof(thread_t));
    }
    return @{ @"time": @(monotonic()), @"threads": entries, @"available": @(result == KERN_SUCCESS) };
}

static NSArray* cpu_rates(NSDictionary* current, NSDictionary* previous)
{
    NSMutableArray* rates = [NSMutableArray new];
    double elapsed = [current[@"time"] doubleValue] - [previous[@"time"] doubleValue];
    if (elapsed <= 0 || !previous) return rates;
    for (NSNumber* identity in current[@"threads"]) {
        NSDictionary* entry = current[@"threads"][identity], *old = previous[@"threads"][identity];
        if (!old) continue;
        double cpu = MAX(0, ([entry[@"seconds"] doubleValue] - [old[@"seconds"] doubleValue]) / elapsed * 100);
        [rates addObject:@{ @"id": identity, @"name": entry[@"name"], @"cpu_percent": @(cpu) }];
    }
    [rates sortUsingComparator:^NSComparisonResult(NSDictionary* a, NSDictionary* b) {
        return [b[@"cpu_percent"] compare:a[@"cpu_percent"]];
    }];
    return rates;
}

@interface D2FlagNotes : NSObject <NSTextFieldDelegate>
- (void)finish:(id)sender;
@end
static D2FlagNotes* s_note_controller;
static void finish_note(BOOL keep)
{
    if (!s_note_identity) return;
    NSMutableDictionary* note = [s_note_identity mutableCopy];
    note[@"type"] = @"note"; note[@"note"] = keep ? s_note.stringValue : @"";
    NSString* folder = flags_folder();
    dispatch_async(s_flags_queue, ^{ @autoreleasepool { append_record(folder, note); } });
    s_note_identity = nil; [s_note_panel orderOut:nil]; [s_flags_window makeKeyWindow];
}
@implementation D2FlagNotes
- (void)finish:(id)sender { (void)sender; finish_note(YES); }
- (BOOL)control:(NSControl*)control textView:(NSTextView*)view doCommandBySelector:(SEL)selector
{
    (void)control; (void)view;
    if (selector == @selector(cancelOperation:)) { finish_note(NO); return YES; }
    return NO;
}
@end

/* Allocate native note controls while attaching the window, before F2. */
static void prepare_note_panel(void)
{
    if (!s_note_panel) {
        s_note_controller = [D2FlagNotes new];
        s_note_panel = [[NSPanel alloc] initWithContentRect:NSMakeRect(0, 0, 420, 90)
            styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskUtilityWindow backing:NSBackingStoreBuffered defer:NO];
        s_note_panel.title = @"Issue note (optional)"; s_note_panel.hidesOnDeactivate = YES;
        s_note_panel.collectionBehavior = NSWindowCollectionBehaviorFullScreenAuxiliary;
        NSTextField* hint = [NSTextField labelWithString:@"Return saves · Escape dismisses · game keeps running"];
        hint.frame = NSMakeRect(12, 58, 400, 20); [s_note_panel.contentView addSubview:hint];
        s_note = [[NSTextField alloc] initWithFrame:NSMakeRect(12, 15, 396, 30)];
        s_note.delegate = s_note_controller; s_note.target = s_note_controller; s_note.action = @selector(finish:);
        [s_note_panel.contentView addSubview:s_note];
    }
}

static void show_flag(unsigned number, NSDictionary* identity, BOOL saved)
{
    if (!s_flags_window) return;
    s_toast.stringValue = [NSString stringWithFormat:saved ? @"Flagged #%u" : @"Flag #%u could not be saved", number];
    s_toast.hidden = NO;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        if (s_number == number) s_toast.hidden = YES;
    });
    if (!saved) return;
    finish_note(YES);
    if (!s_note_panel) return;
    s_note_identity = identity; s_note.stringValue = @"";
    [s_note_panel setFrameTopLeftPoint:NSMakePoint(NSMidX(s_flags_window.frame) - 210, NSMaxY(s_flags_window.frame) - 80)];
    [s_note_panel makeKeyAndOrderFront:nil]; [s_note_panel makeFirstResponder:s_note];
}

void d2_flags_init(void)
{
    if (s_flags_queue) return;
    s_launch = monotonic(); s_session = NSUUID.UUID.UUIDString;
    s_flags_queue = dispatch_queue_create("D2 flags", DISPATCH_QUEUE_SERIAL);
    s_cpu_history = [NSMutableArray new];
    s_cpu_timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, s_flags_queue);
    dispatch_source_set_timer(s_cpu_timer, DISPATCH_TIME_NOW, NSEC_PER_SEC, 100 * NSEC_PER_MSEC);
    dispatch_source_set_event_handler(s_cpu_timer, ^{ @autoreleasepool {
        [s_cpu_history addObject:cpu_sample()];
        while (s_cpu_history.count > 4) [s_cpu_history removeObjectAtIndex:0];
    } });
    dispatch_resume(s_cpu_timer);
    const char* automatic = getenv("D2_FLAG_TEST_AFTER_SECONDS");
    double seconds = automatic ? strtod(automatic, NULL) : 0;
    if (isfinite(seconds) && seconds > 0 && seconds <= 3600)
        [NSTimer scheduledTimerWithTimeInterval:seconds repeats:NO block:^(NSTimer* timer) {
            (void)timer; d2_flags_request();
        }];
}

void d2_flags_configure(double scale, unsigned cap) { s_scale = scale; s_cap = cap; }
void d2_flags_attach_window(void* window)
{
    finish_note(YES); [s_toast removeFromSuperview];
    s_flags_window = (__bridge NSWindow*)window;
    if (!s_flags_window) { s_toast = nil; return; }
    prepare_note_panel();
    // Reuse the settings/FPS in-window AppKit overlay, without a modal guest UI.
    s_toast = [NSTextField labelWithString:@""];
    s_toast.frame = NSMakeRect(12, 46, 330, 26); s_toast.hidden = YES;
    s_toast.textColor = NSColor.whiteColor;
    s_toast.backgroundColor = [NSColor.blackColor colorWithAlphaComponent:0.7];
    s_toast.drawsBackground = YES; s_toast.font = [NSFont systemFontOfSize:15 weight:NSFontWeightMedium];
    [s_flags_window.contentView addSubview:s_toast];
}

void d2_flags_request(void)
{
    // F2 uses the same main-thread input path as F1. No I/O or Mach calls here.
    if (!s_flags_queue) return;
    unsigned number = ++s_number, cap = s_cap;
    double now = monotonic(), wall = NSDate.date.timeIntervalSince1970, scale = s_scale;
    NSDictionary* identity = @{ @"session": s_session, @"number": @(number) };
    dispatch_async(s_flags_queue, ^{ @autoreleasepool {
        NSString* folder = flags_folder();
        NSString* screenshot = [folder stringByAppendingPathComponent:
            [NSString stringWithFormat:@"%@-%u.png", s_session, number]];
        if ([NSFileManager.defaultManager createDirectoryAtPath:folder
                withIntermediateDirectories:YES attributes:nil error:nil]) {
            // Snapshot before Mach sampling/fsync can delay the bookmark.
            void* context = (__bridge_retained void*)@{ @"folder": folder, @"identity": identity };
            extern void d2_flags_capture_done(void*, int);
            rsx_metal_backend_capture_png(screenshot.fileSystemRepresentation, d2_flags_capture_done, context);
        }
        NSMutableDictionary* record = [identity mutableCopy];
        record[@"type"] = @"flag"; record[@"schema_version"] = @1;
        record[@"wall_time_unix"] = @(wall);
        NSISO8601DateFormatter* format = [NSISO8601DateFormatter new];
        format.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
        record[@"time"] = [format stringFromDate:[NSDate dateWithTimeIntervalSince1970:wall]];
        record[@"seconds_since_launch"] = @(now - s_launch);
        [record addEntriesFromDictionary:frame_stats(now)];
        unsigned map = 0, stage = 0;
        BOOL location = d2_flags_guest_location(&map, &stage);
        record[@"map_id"] = location ? @(map) : NSNull.null;
        record[@"stage_id"] = location ? @(stage) : NSNull.null;
        NSDictionary* current = cpu_sample(), *previous = s_cpu_history.firstObject;
        for (NSDictionary* sample in s_cpu_history)
            if ([sample[@"time"] doubleValue] <= [current[@"time"] doubleValue] - 1.5) previous = sample;
        record[@"threads"] = cpu_rates(current, previous);
        record[@"cpu_window_seconds"] = previous ? @([current[@"time"] doubleValue] - [previous[@"time"] doubleValue]) : @0;
        record[@"cpu_available"] = current[@"available"];
        mach_task_basic_info_data_t task; mach_msg_type_number_t n = MACH_TASK_BASIC_INFO_COUNT;
        record[@"rss_bytes"] = task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&task, &n) == KERN_SUCCESS ?
            @(task.resident_size) : NSNull.null;
        record[@"render_scale"] = @(scale); record[@"frame_cap"] = @(cap);
        record[@"audio_underruns"] = NSNull.null; // cellAudio has no exported underrun counter.
        record[@"note"] = @"";
        record[@"screenshot"] = screenshot;
        BOOL saved = append_record(folder, record);
        dispatch_async(dispatch_get_main_queue(), ^{ show_flag(number, identity, saved); });
    } });
}

void d2_flags_capture_done(void* context, int success)
{
    NSDictionary* capture = (__bridge_transfer NSDictionary*)context;
    dispatch_async(s_flags_queue, ^{ @autoreleasepool {
        NSMutableDictionary* event = [capture[@"identity"] mutableCopy];
        event[@"type"] = @"screenshot"; event[@"screenshot_status"] = success ? @"saved" : @"unavailable";
        append_record(capture[@"folder"], event);
    } });
}

int d2_flags_key_event(unsigned code, int down, int repeat)
{
    if (code != 120) return 0; // Physical F2; F1 is 122.
    if (down && !repeat) d2_flags_request();
    return 1;
}
