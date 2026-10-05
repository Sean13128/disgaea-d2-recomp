/* Reuse the existing backend/overlay harness's host stubs. */
#define main ag_fixture_main
#include "AG.metal-test.m"
#undef main
int main(void)
{
    @autoreleasepool {
        // Invoke close's implementation with no window allocation: this path
        // only requests stop, leaving the drawable alive for active saves.
        void (*close_action)(id, SEL, id) = (void*)[Ps3MetalWindow instanceMethodForSelector:@selector(performClose:)];
        close_action(nil, @selector(performClose:), nil); assert(s_closed);
        s_closed = 0;
        assert([[Ps3MetalAppDelegate new] applicationShouldTerminate:nil] == NSTerminateCancel);
        assert(s_closed); s_closed = 0;
        puts("[AL-lifecycle-ui] red close and Cmd+Q share deferred stop: PASS");
        s_dev = MTLCreateSystemDefaultDevice();
        if (!s_dev) { puts("[AL-metal] SKIP: no Metal device"); return 77; }
        s_queue = [s_dev newCommandQueue];
        assert(eng_init(NULL, 1280, 720) == 0);
        s_headless = 0; s_inflight = dispatch_semaphore_create(MTL_MAX_INFLIGHT);
        setenv("PS3RECOMP_METAL_NIL_DRAWABLE", "1", 1);
        u32 target = eng_color_target_create(NULL, RSX_BE_FMT_R8G8B8A8, 8, 8, NULL, 0);
        assert(target);
        const float red[4] = {1,0,0,1};
        eng_clear_color(NULL, target, red);
        assert(s_eng_rec_count);
        u32 stage_offset;
        assert(eng_stage_reserve(16, &stage_offset));
        memset(s_eng_stage + stage_offset, 0, 16);
        int outcome = eng_encode_and_commit(eng_obj(target));
        assert(outcome == 1); // guest submission, no host drawable
        assert(s_eng_rec_count == 0 && s_eng_stage_used == 0);
        id<MTLCommandBuffer> fence = [s_queue commandBuffer];
        [fence commit]; [fence waitUntilCompleted]; assert(!fence.error);
        unsigned char pixels[8*8*4];
        [eng_obj(target) getBytes:pixels bytesPerRow:32 fromRegion:MTLRegionMake2D(0,0,8,8) mipmapLevel:0];
        assert(pixels[0] == 255 && pixels[1] == 0 && pixels[3] == 255);
        for (int i=0; i<MTL_MAX_INFLIGHT; i++) assert(!dispatch_semaphore_wait(s_inflight, DISPATCH_TIME_NOW));
        for (int i=0; i<MTL_MAX_INFLIGHT; i++) dispatch_semaphore_signal(s_inflight);
        puts("[AL-metal] nil drawable submits guest clear, resets records/stage, balances inflight: PASS");
        eng_shutdown(NULL); s_inflight = nil;
    }
    return 0;
}
