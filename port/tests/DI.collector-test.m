// Synthetic cached telemetry only: never initialize the recurring Mach sampler.
#include "../src/d2_flags.m"
#include <assert.h>
static unsigned machQueries;
// Make accidental diagnostics sampling fatal; all cache inputs are synthetic.
kern_return_t task_threads(task_t task, thread_act_array_t* list, mach_msg_type_number_t* count)
{ (void)task; (void)list; (void)count; machQueries++; abort(); }
static int compare_ms(const void* a, const void* b)
{ double x = *(const double*)a, y = *(const double*)b; return (x > y) - (x < y); }
extern void d2_flags_diagnostics_snapshot(void (^completion)(NSDictionary*)) __attribute__((weak_import));
int d2_flags_guest_location(unsigned* map, unsigned* stage) { (void)map; (void)stage; abort(); }
void rsx_metal_backend_capture_png(const char* path, void (*done)(void*, int), void* user)
{ (void)path; (void)done; (void)user; abort(); }
static NSDictionary* read_snapshot(void)
{
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    __block NSDictionary* value;
    d2_flags_diagnostics_snapshot(^(NSDictionary* snapshot) { value = snapshot; dispatch_semaphore_signal(done); });
    assert(dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC)) == 0);
    return value;
}
int main(void)
{
    @autoreleasepool {
        assert(d2_flags_diagnostics_snapshot && "missing read-only asynchronous cached diagnostics getter");
        NSDictionary* uninitialized = read_snapshot();
        assert([uninitialized[@"cpu_status"] isEqual:@"unavailable"] && "uninitialized cache is unavailable, not CPU warmup");
        s_launch = monotonic();
        s_flags_queue = dispatch_queue_create("diagnostics synthetic cache", DISPATCH_QUEUE_SERIAL);
        s_cpu_history = [NSMutableArray new];
        dispatch_semaphore_t held = dispatch_semaphore_create(0), release = dispatch_semaphore_create(0);
        dispatch_async(s_flags_queue, ^{ dispatch_semaphore_signal(held); dispatch_semaphore_wait(release, DISPATCH_TIME_FOREVER); });
        dispatch_semaphore_wait(held, DISPATCH_TIME_FOREVER);
        dispatch_semaphore_t completed = dispatch_semaphore_create(0);
        __block NSDictionary* snapshot;
        double start = monotonic();
        d2_flags_diagnostics_snapshot(^(NSDictionary* value) {
            assert(!NSThread.isMainThread); snapshot = value; dispatch_semaphore_signal(completed);
        });
        double ms = (monotonic() - start) * 1000;
        assert(ms < 5 && !snapshot); // queue can be busy; caller must never wait for it
        dispatch_semaphore_signal(release);
        assert(dispatch_semaphore_wait(completed, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC)) == 0);
        assert([snapshot[@"cpu_status"] isEqual:@"warmup"]);
        assert([snapshot[@"threads"] count] == 0 && !s_cpu_timer);
        printf("[DI collector] asynchronous cache-only getter; blocked-queue enqueue %.3f ms (<5); warmup: PASS\n", ms);
        double now = monotonic();
        NSDictionary* before = @{ @"time": @(now - 2), @"available": @YES,
            @"threads": @{ @7: @{ @"seconds": @1, @"name": @"PPU main" } } };
        NSDictionary* after = @{ @"time": @(now), @"available": @YES,
            @"threads": @{ @7: @{ @"seconds": @2, @"name": @"PPU main" },
                           @8: @{ @"seconds": @1, @"name": @"new worker" } } };
        dispatch_sync(s_flags_queue, ^{ [s_cpu_history addObjectsFromArray:@[before, after]]; });
        d2_flags_diagnostics_snapshot(^(NSDictionary* value) { snapshot = value; dispatch_semaphore_signal(completed); });
        assert(dispatch_semaphore_wait(completed, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC)) == 0);
        assert([snapshot[@"cpu_status"] isEqual:@"available"]);
        assert([snapshot[@"cpu_window_seconds"] doubleValue] == 2);
        NSArray* rows = snapshot[@"threads"];
        assert(rows.count == 2);
        assert([rows[0][@"id"] isEqual:@7] && [rows[0][@"cpu_percent"] doubleValue] == 50);
        assert([rows[0][@"cpu_status"] isEqual:@"available"]);
        assert([rows[1][@"id"] isEqual:@8] && [rows[1][@"cpu_status"] isEqual:@"warmup"]);
        assert(rows[1][@"cpu_percent"] == NSNull.null);
        puts("[DI collector] cached CPU deltas, stable IDs, new-thread warmup (not zero): PASS");
        dispatch_sync(s_flags_queue, ^{
            NSDictionary* failed = @{ @"time": @(now + 1), @"available": @NO, @"threads": @{} };
            [s_cpu_history setArray:@[before, failed]];
            assert([diagnostics_cpu(now + 1)[@"cpu_status"] isEqual:@"unavailable"]);
            [s_cpu_history setArray:@[failed, after]];
            assert([diagnostics_cpu(now)[@"cpu_status"] isEqual:@"warmup"]);
            [s_cpu_history setArray:@[before, after]];
            NSDictionary* stale = diagnostics_cpu(now + 5);
            assert([stale[@"cpu_status"] isEqual:@"unavailable"]);
            assert([stale[@"threads"][0][@"cpu_status"] isEqual:@"unavailable"]);
            assert(stale[@"threads"][0][@"cpu_percent"] == NSNull.null);
            NSDictionary* reset = @{ @"time": @(now), @"available": @YES,
                @"threads": @{ @7: @{ @"seconds": @0.5, @"name": @"renamed" } } };
            [s_cpu_history setArray:@[before, reset]];
            NSDictionary* row = diagnostics_cpu(now)[@"threads"][0];
            assert([row[@"cpu_status"] isEqual:@"unknown"] && row[@"cpu_percent"] == NSNull.null);
            assert([row[@"name"] isEqual:@"renamed"]);
            [s_cpu_history setArray:@[after, after]];
            assert([diagnostics_cpu(now)[@"cpu_status"] isEqual:@"warmup"]);
        });
        puts("[DI collector] failed/stale samples unavailable; regression unknown; invalid interval warmup: PASS");
        snapshot = read_snapshot();
        assert([snapshot[@"guest_frame_status"] isEqual:@"unavailable"]);
        assert(snapshot[@"guest_active_interval_ms"] == NSNull.null);
        assert(snapshot[@"display_latest_interval_ms"] == NSNull.null);
        now = monotonic(); s_launch = now - 100;
        ps3_host_frame_event(now - 80, 1, 0);
        for (unsigned i = 0; i < 4096; i++) ps3_host_frame_event(now - 0.8 + i * 0.0001, 0, 1);
        snapshot = read_snapshot();
        assert([snapshot[@"guest_frame_status"] isEqual:@"available"]);
        assert([snapshot[@"guest_fps_1s"] doubleValue] == 0);
        assert([snapshot[@"guest_active_interval_ms"] doubleValue] >= 80000);
        assert([snapshot[@"worst_frame_ms_10s"] doubleValue] >= 80000);
        assert(snapshot[@"guest_latest_interval_ms"] == NSNull.null); // evicted, not fabricated
        assert(fabs([snapshot[@"display_latest_interval_ms"] doubleValue] - 0.1) < 0.001);
        assert([snapshot[@"frame_ring_count"] unsignedIntValue] == 4096);
        assert(![snapshot[@"frame_window_1s_complete"] boolValue]);
        assert(![snapshot[@"frame_window_10s_complete"] boolValue]);
        puts("[DI collector] directional availability, ms intervals, ongoing >10s stall after ring eviction, truncation: PASS");
        // Fixed workload, bounded repetitions: 128 cached threads + the full 4096-event ring.
        NSMutableDictionary* oldThreads = [NSMutableDictionary new], *newThreads = [NSMutableDictionary new];
        for (unsigned i = 1; i <= 128; i++) {
            oldThreads[@(i)] = @{ @"seconds": @1, @"name": @"synthetic worker" };
            newThreads[@(i)] = @{ @"seconds": @1.1, @"name": @"synthetic worker" };
        }
        now = monotonic();
        dispatch_sync(s_flags_queue, ^{ [s_cpu_history setArray:@[
            @{ @"time": @(now - 1), @"available": @YES, @"threads": [oldThreads copy] },
            @{ @"time": @(now), @"available": @YES, @"threads": [newThreads copy] }]]; });
        double times[256], total = 0;
        unsigned requests = 0, callbacks = 0;
        for (unsigned i = 0; i < 256; i++) { @autoreleasepool {
            start = monotonic(); requests++;
            NSDictionary* measured = read_snapshot(); callbacks++;
            times[i] = (monotonic() - start) * 1000; total += times[i];
            assert([measured[@"threads"] count] == 128 && [measured[@"frame_ring_count"] intValue] == 4096);
        } }
        qsort(times, 256, sizeof(double), compare_ms);
        assert(requests == 256 && callbacks == 256 && !machQueries && !s_cpu_timer);
        assert(total / 256 < 10); // coarse regression guard, not a gameplay-overhead claim
        printf("[DI benchmark] ASan/UBSan O1; requests=%u callbacks=%u; 128 threads/4096 events; enqueue-to-callback mean=%.3f ms p95=%.3f ms max=%.3f ms; Mach enumerations=%u new timers=0\n",
            requests, callbacks, total / 256, times[243], times[255], machQueries);
    }
    return 0;
}
