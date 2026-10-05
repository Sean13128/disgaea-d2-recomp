#define main ag_fixture_main
#include "AG.metal-test.m"
#undef main
static dispatch_semaphore_t capture_done;
static void captured(void* user, int success)
{
    assert(!NSThread.isMainThread);
    *(int*)user = success ? 1 : -1;
    dispatch_semaphore_signal(capture_done);
}
static void wait_capture(int* result)
{
    assert(!dispatch_semaphore_wait(capture_done, dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC)));
    assert(*result);
}
int main(int argc, const char** argv)
{
    @autoreleasepool {
        assert(argc == 2);
        capture_done = dispatch_semaphore_create(0);
        int result = 0;
        rsx_metal_backend_capture_png(NULL, captured, &result);
        wait_capture(&result); assert(result == -1);
        puts("[AN metal] missing frame/device reports failure off main: PASS");
        s_dev = MTLCreateSystemDefaultDevice();
        if (!s_dev) { puts("[AN metal] SKIP: no Metal device"); return 77; }
        s_queue = [s_dev newCommandQueue];
        rsx_metal_overlay_init(s_dev, s_queue, nil, nil);
        id<MTLTexture> guest = sized_texture(8, 4), display = sized_texture(8, 4);
        unsigned char red[8*4*4];
        for (unsigned i=0; i<32; i++) { red[i*4]=0; red[i*4+1]=0; red[i*4+2]=255; red[i*4+3]=255; }
        [guest replaceRegion:MTLRegionMake2D(0,0,8,4) mipmapLevel:0 withBytes:red bytesPerRow:32];
        id<MTLCommandBuffer> cb = [s_queue commandBuffer];
        rsx_metal_overlay_encode(cb, guest, display); [cb commit]; rsx_metal_overlay_end();
        NSString* path = [@(argv[1]) stringByAppendingPathComponent:@"flag.png"];
        result = 0; rsx_metal_backend_capture_png(path.UTF8String, captured, &result);
        wait_capture(&result); assert(result == 1);
        NSBitmapImageRep* png = [NSBitmapImageRep imageRepWithData:[NSData dataWithContentsOfFile:path]];
        assert(png.pixelsWide == 8 && png.pixelsHigh == 4);
        NSColor* pixel = [png colorAtX:0 y:0]; // raw stored components; color-managed conversion shifts them
        assert(pixel.redComponent > .99 && pixel.greenComponent < .01 && pixel.blueComponent < .01);
        puts("[AN metal] preserved frame PNG, dimensions and BGRA→RGBA color: PASS");
        rsx_metal_overlay_shutdown();
    }
    return 0;
}
