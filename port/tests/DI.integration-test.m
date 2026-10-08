// Real window + real cached collector, synthetic inputs, no SDK sampler/assets.
#define d2_flags_diagnostics_snapshot diagnostics_cached_getter
#include "../src/d2_flags.m"
#undef d2_flags_diagnostics_snapshot
void d2_flags_diagnostics_snapshot(void (^completion)(NSDictionary*));
#include "../src/d2_diagnostics.m"
#include <assert.h>
static unsigned requests, callbacks, machQueries;
static double requestTimes[16];
kern_return_t task_threads(task_t task, thread_act_array_t* list, mach_msg_type_number_t* count)
{ (void)task; (void)list; (void)count; machQueries++; abort(); }
int d2_flags_guest_location(unsigned* map, unsigned* stage) { (void)map; (void)stage; abort(); }
void rsx_metal_backend_capture_png(const char* path, void (*done)(void*, int), void* user)
{ (void)path; (void)done; (void)user; abort(); }
void d2_flags_diagnostics_snapshot(void (^completion)(NSDictionary*))
{
    assert(NSThread.isMainThread && requests < 16);
    requestTimes[requests++] = monotonic();
    diagnostics_cached_getter(^(NSDictionary* snapshot) { callbacks++; completion(snapshot); });
}
static void spin(double seconds)
{ [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:seconds]]; }
int main(void)
{
    @autoreleasepool {
        [NSApplication sharedApplication];
        double now = monotonic(); s_launch = now - 100;
        s_flags_queue = dispatch_queue_create("DI integrated synthetic cache", DISPATCH_QUEUE_SERIAL);
        NSMutableDictionary* old = [NSMutableDictionary new], *current = [NSMutableDictionary new];
        for (unsigned i = 1; i <= 128; i++) {
            old[@(i)] = @{ @"seconds": @1, @"name": @"synthetic worker" };
            current[@(i)] = @{ @"seconds": @1.1, @"name": @"synthetic worker" };
        }
        s_cpu_history = [@[
            @{ @"time": @(now - 1), @"available": @YES, @"threads": [old copy] },
            @{ @"time": @(now), @"available": @YES, @"threads": [current copy] }] mutableCopy];
        for (unsigned i = 1; i <= 1200; i++) ps3_host_frame_event(now - 20 + i / 60.0, 1, i % 2 == 0);
        d2_diagnostics_toggle(); spin(0.1);
        assert(requests == 1 && s_diagnostics.table.numberOfRows == 128);
        NSArray* fpsLines = [s_diagnostics.frames.stringValue componentsSeparatedByString:@"\n"];
        double guest = 0, display = 0;
        assert(sscanf([fpsLines[0] UTF8String], "Guest flips: %lf FPS", &guest) == 1);
        assert(sscanf([fpsLines[1] UTF8String], "Display presentations: %lf FPS", &display) == 1);
        // The real getter's rolling window includes time spent constructing AppKit.
        assert(guest > 0 && display > 0 && guest > display && guest <= 61 && display <= 31);
        assert([s_diagnostics.activity.stringValue containsString:@"CPU: available"]);
        for (unsigned i = 0; i < 1000; i++) [s_diagnostics poll];
        assert(requests == 1); // completed requests also obey the 1Hz throttle
        spin(1.05); assert(requests == 2);
        d2_diagnostics_close();
        NSString* before = [s_diagnostics.frames.stringValue copy];
        unsigned hiddenStart = requests;
        for (unsigned i = 0; i < 1000; i++) [s_diagnostics poll];
        spin(1.1);
        assert(requests == hiddenStart && !s_diagnostics.timer);
        assert([s_diagnostics.frames.stringValue isEqual:before]);
        d2_diagnostics_toggle(); spin(0.1);
        assert(s_diagnostics.table.numberOfRows == 128 && requests == 3);
        for (unsigned i = 1; i < requests; i++) assert(requestTimes[i] - requestTimes[i - 1] >= 1);
        [NSApp hide:nil];
        assert(NSApp.isHidden);
        unsigned appHiddenStart = requests;
        spin(1.1);
        assert(requests == appHiddenStart && "hidden application must not request diagnostics");
        [NSApp unhideWithoutActivation];
        d2_diagnostics_close();
        dispatch_sync(s_flags_queue, ^{});
        assert(callbacks == requests && !machQueries && !s_cpu_timer);
        printf("[DI integrated] real UI+getter: 128 rows; requests=%u callbacks=%u; ≥1s spacing; 1000 visible burst polls throttled; 1000 hidden polls + 1.1s closed run loop: hidden requests=0; Mach enumerations=0 new samplers=0\n", requests, callbacks);
    }
    return 0;
}
