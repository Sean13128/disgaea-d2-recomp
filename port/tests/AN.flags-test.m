#include "../src/d2_flags.m"
#include <assert.h>
int d2_flags_guest_location(unsigned* map, unsigned* stage) { *map = 30101; *stage = 7; return 1; }
void rsx_metal_backend_capture_png(const char* path, void (*done)(void*, int), void* user)
{ (void)path; done(user, 0); }
static NSArray* read_records(NSString* folder)
{
    NSString* file = [folder stringByAppendingPathComponent:@"flags.jsonl"];
    NSString* text = [NSString stringWithContentsOfFile:file encoding:NSUTF8StringEncoding error:nil];
    NSMutableArray* result = [NSMutableArray new];
    for (NSString* line in [text componentsSeparatedByString:@"\n"]) {
        if (!line.length) continue;
        NSDictionary* record = [NSJSONSerialization JSONObjectWithData:[line dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        assert(record); [result addObject:record];
    }
    return result;
}
int main(int argc, const char** argv)
{
    @autoreleasepool {
        assert(argc == 2);
        NSString* root = [@(argv[1]) stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
        NSString* folder = [root stringByAppendingPathComponent:@"writer"];
        NSString* note = @"white portrait\nquote: \"hello\" · 日本語";
        assert(append_record(folder, @{ @"type": @"flag", @"session": @"test", @"number": @1, @"note": note, @"map_id": NSNull.null }));
        assert(append_record(folder, @{ @"type": @"note", @"session": @"test", @"number": @1, @"note": @"updated" }));
        NSArray* records = read_records(folder);
        assert(records.count == 2 && [records[0][@"note"] isEqual:note]);
        assert(records[0][@"map_id"] == NSNull.null);
        assert(!append_record([folder stringByAppendingPathComponent:@"flags.jsonl/child"], @{}));
        puts("[AN flags] JSONL append, Unicode/newline escaping, nulls, failure preservation: PASS");

        s_launch = 100;
        for (unsigned i = 1; i <= 1200; i++) ps3_host_frame_event(100 + i / 60.0, 1, i % 2 == 0);
        NSDictionary* rates = frame_stats(120);
        assert([rates[@"guest_fps_1s"] doubleValue] >= 59 && [rates[@"guest_fps_1s"] doubleValue] <= 61);
        assert([rates[@"display_fps_10s"] doubleValue] >= 29 && [rates[@"display_fps_10s"] doubleValue] <= 31);
        assert([rates[@"worst_frame_ms_10s"] doubleValue] > 16);
        ps3_host_frame_event(120.1, 1, 0); // nil drawable is a guest flip only
        rates = frame_stats(120.1); assert([rates[@"worst_frame_ms_10s"] doubleValue] >= 99);
        rates = frame_stats(122.1); assert([rates[@"guest_fps_1s"] doubleValue] == 0);
        assert([rates[@"worst_frame_ms_10s"] doubleValue] >= 1999);
        puts("[AN flags] independent guest/display rolling windows + current stall: PASS");

        NSDictionary* before = @{ @"time": @10, @"threads": @{ @7: @{ @"seconds": @1, @"name": @"PPU main" } } };
        NSDictionary* after = @{ @"time": @12, @"threads": @{ @7: @{ @"seconds": @2, @"name": @"PPU main" }, @8: @{ @"seconds": @1, @"name": @"new" } } };
        NSArray* cpu = cpu_rates(after, before);
        assert(cpu.count == 1 && [cpu[0][@"cpu_percent"] doubleValue] == 50);
        NSDictionary* actual = cpu_sample(); assert([actual[@"available"] boolValue]);
        assert([actual[@"threads"] count]);
        puts("[AN flags] Mach CPU totals, stable thread IDs, two-second rates: PASS");

        NSString* hdd = [root stringByAppendingPathComponent:@"hdd0"];
        setenv("PS3_HDD0_ROOT", hdd.UTF8String, 1);
        assert([flags_folder() isEqual:[root stringByAppendingPathComponent:@"flags"]]);
        d2_flags_init(); dispatch_source_cancel(s_cpu_timer);
        unsigned number = s_number;
        assert(!d2_flags_key_event(122, 1, 0));
        assert(d2_flags_key_event(120, 0, 0) && d2_flags_key_event(120, 1, 1));
        assert(s_number == number);
        double start = monotonic(); assert(d2_flags_key_event(120, 1, 0));
        double ms = (monotonic() - start) * 1000;
        assert(ms < 5); assert(s_number == number + 1);
        dispatch_sync(s_flags_queue, ^{}); dispatch_sync(s_flags_queue, ^{});
        records = read_records(flags_folder());
        assert(records.count == 2);
        assert([records[0][@"map_id"] unsignedIntValue] == 30101);
        assert([records[0][@"frame_cap"] unsignedIntValue] == 60);
        assert([records[1][@"screenshot_status"] isEqual:@"unavailable"]);
        printf("[AN flags] F2 repeat/up suppression, sibling path, complete async bookmark, handler %.3f ms (<5): PASS\n", ms);
    }
    return 0;
}
