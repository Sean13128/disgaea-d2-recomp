/* Include the actual backend, as test_metal_resource_lifetime.m does. */
#include "libs/video/rsx_metal_backend.m"
#include <assert.h>
/* Exercise the shared compositor too, with a quiet system UI model. */
// The compositor is a separate translation unit in production. Namespace its
// file-static globals here so shutdown cannot nil the backend's queue/layer.
#define s_queue overlay_queue
#define s_layer overlay_layer
#define s_inflight overlay_inflight
#include "libs/video/rsx_metal_overlay.m"
#undef s_inflight
#undef s_layer
#undef s_queue
void ps3_overlay_poll(void) {}
void ps3_overlay_snapshot(SysOverlaySnapshot* ui) { memset(ui, 0, sizeof *ui); }
void ps3_overlay_set_renderer(int available) { (void)available; }

static void conversion_chain(const char* dump)
{
    s_headless = 1;
    rsx_metal_overlay_init(s_dev, s_queue, nil, nil);
    s_offscreen = sized_texture(1280, 720); assert(s_offscreen);
    if (dump) {
        setenv("PS3RECOMP_METAL_FRAME_DUMP", dump, 1);
        setenv("PS3RECOMP_METAL_FRAME_DUMP_EVERY", "1", 1);
    }
    for (unsigned scale = 2; scale <= 6; scale++) {
        if (scale == 5) continue;
        rsx_metal_backend_configure(scale, 0, 0, 1, 0); eng_apply_host_settings();
        // A rendered offscreen source and a separate registered-scanout-sized target.
        u32 scene = eng_color_target_create(NULL, RSX_BE_FMT_R8G8B8A8, 1280, 720, NULL, 0);
        u32 display = eng_color_target_create(NULL, RSX_BE_FMT_R8G8B8A8, 1280, 720, NULL, 0);
        id<MTLTexture> src = eng_obj(scene), dst = eng_obj(display);
        assert(dst.width == eng_scaled(1280) && dst.height == eng_scaled(720));
        u8* pixels = malloc(src.width * src.height * 4); assert(pixels);
        for (unsigned y = 0; y < src.height; y++) for (unsigned x = 0; x < src.width; x++) {
            size_t i = (y * src.width + x) * 4;
            pixels[i] = (x & 1) ? 255 : 0;
            pixels[i+1] = (y & 1) ? 255 : 0;
            pixels[i+2] = 31; pixels[i+3] = 255;
        }
        [src replaceRegion:MTLRegionMake2D(0, 0, src.width, src.height) mipmapLevel:0
            withBytes:pixels bytesPerRow:src.width*4];
        eng_blit(NULL, scene, display, 0, 0, 1280, 720, 0, 0, 1280, 720, 1);
        eng_present(NULL, display); // encodes copy, presents and captures this scaled texture
        u8* result = malloc(dst.width * dst.height * 4); assert(result);
        [dst getBytes:result bytesPerRow:dst.width*4
            fromRegion:MTLRegionMake2D(0, 0, dst.width, dst.height) mipmapLevel:0];
        assert(memcmp(pixels, result, dst.width * dst.height * 4) == 0);
        assert(s_eng_native[display-1].w == 1280 && s_eng_native[display-1].h == 720);
        u8 native[4] = {0}; eng_readback(NULL, display, 20, 20, 1, 1, native, 4);
        assert(native[2] == 31 && native[3] == 255);
        if (scale == 4) assert(native[0] >= 127 && native[0] <= 128 && native[1] >= 127 && native[1] <= 128);
        free(result); free(pixels);
        eng_obj_release(NULL, scene); eng_obj_release(NULL, display);
        printf("[AG2-metal] RESC-style copy + eng_present %.1fx %ux%u, exact subpixels, native readback: PASS\n",
            scale / 2.0, eng_scaled(1280), eng_scaled(720));
    }
    unsetenv("PS3RECOMP_METAL_FRAME_DUMP");
    rsx_metal_overlay_shutdown();
    assert(s_queue && "overlay shutdown must preserve the backend queue");

    // Partial 1:1 rectangles with nonzero origins and fractional scale edges.
    for (unsigned scale = 2; scale <= 6; scale++) {
        if (scale == 5) continue;
        rsx_metal_backend_configure(scale, 0, 0, 1, 0); eng_apply_host_settings();
        u32 source = eng_color_target_create(NULL, RSX_BE_FMT_R8G8B8A8, 7, 5, NULL, 0);
        u32 destination = eng_color_target_create(NULL, RSX_BE_FMT_R8G8B8A8, 9, 7, NULL, 0);
        const float red[4] = {1,0,0,1}, black[4] = {0,0,0,1};
        eng_clear_color(NULL, source, red); eng_clear_color(NULL, destination, black);
        eng_blit(NULL, source, destination, 1, 1, 3, 2, 3, 2, 3, 2, 0);
        id<MTLCommandBuffer> cb = [s_queue commandBuffer];
        eng_encode_records(cb, nil); s_eng_rec_count = 0;
        [cb commit]; [cb waitUntilCompleted]; assert(!cb.error);
        id<MTLTexture> dst = eng_obj(destination);
        u8* pixels = malloc(dst.width * dst.height * 4);
        [dst getBytes:pixels bytesPerRow:dst.width*4
            fromRegion:MTLRegionMake2D(0, 0, dst.width, dst.height) mipmapLevel:0];
        for (unsigned y = 0; y < dst.height; y++) for (unsigned x = 0; x < dst.width; x++) {
            BOOL inside = x >= eng_scaled(3) && x < eng_scaled(6) && y >= eng_scaled(2) && y < eng_scaled(4);
            const u8* pixel = pixels + (y*dst.width+x)*4;
            if (pixel[0] != (inside ? 255 : 0) || pixel[1] || pixel[2] || pixel[3] != 255) {
                fprintf(stderr, "[AH-metal] partial copy %.1fx (%u,%u) inside=%d RGBA=%u,%u,%u,%u\n",
                    scale / 2.0, x, y, inside, pixel[0], pixel[1], pixel[2], pixel[3]);
                assert(0 && "independent source/destination clears and partial copy");
            }
        }
        free(pixels);
        if (scale != 3) {
            const u8 rgb[12] = {255,0,0,255, 0,255,0,255, 0,0,255,255};
            u32 upload = eng_texture_create(NULL, RSX_BE_FMT_R8G8B8A8, 3, 1, 1, 1, 0xAAE4, 0x85);
            eng_texture_upload(NULL, upload, 0, 0, 3, 1, rgb, 12, 1);
            assert(eng_obj(upload).width == 3); // input is native at 2x too
            eng_clear_color(NULL, destination, black);
            eng_blit(NULL, upload, destination, 0, 0, 3, 1, 2, 2, 3, 1, 0);
            eng_obj_release(NULL, upload); // pending transfer must retain this resource
            cb = [s_queue commandBuffer]; eng_encode_records(cb, nil); s_eng_rec_count = 0;
            [cb commit]; [cb waitUntilCompleted]; assert(!cb.error);
            u8 pixel[4];
            for (u32 x = 0; x < 3; x++) {
                [dst getBytes:pixel bytesPerRow:4
                    fromRegion:MTLRegionMake2D(eng_scaled(2+x), eng_scaled(2), 1, 1) mipmapLevel:0];
                assert(!memcmp(pixel, rgb+x*4, 4));
            }
            // Shift the uploaded row in place; overlapping copy must snapshot.
            eng_blit(NULL, destination, destination, 2, 2, 2, 1, 3, 2, 2, 1, 0);
            cb = [s_queue commandBuffer]; eng_encode_records(cb, nil); s_eng_rec_count = 0;
            [cb commit]; [cb waitUntilCompleted]; assert(!cb.error);
            for (u32 x = 0; x < 2; x++) {
                [dst getBytes:pixel bytesPerRow:4
                    fromRegion:MTLRegionMake2D(eng_scaled(3+x), eng_scaled(2), 1, 1) mipmapLevel:0];
                assert(!memcmp(pixel, rgb+x*4, 4));
            }
            eng_collect_retired_objects();
        }
        eng_obj_release(NULL, source); eng_obj_release(NULL, destination);
    }
    puts("[AG2-metal] independent differently sized clears, partial rectangles at 1/1.5/2/3x, native NV308A upload + deferred lifetime: PASS");
}


static float depth_value(id<MTLTexture> depth)
{
    MTLTextureDescriptor* td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatR32Float width:1 height:1 mipmapped:NO];
    td.usage = MTLTextureUsageRenderTarget;
    id<MTLTexture> dst = [s_dev newTextureWithDescriptor:td];
    MTLRenderPipelineDescriptor* pd = [MTLRenderPipelineDescriptor new];
    pd.vertexFunction = [s_eng_helper_lib newFunctionWithName:@"eng_fullscreen_vs"];
    pd.fragmentFunction = [s_eng_helper_lib newFunctionWithName:@"eng_depth_fs"];
    pd.colorAttachments[0].pixelFormat = MTLPixelFormatR32Float;
    id<MTLRenderPipelineState> pso = [s_dev newRenderPipelineStateWithDescriptor:pd error:nil];
    assert(pso);
    MTLRenderPassDescriptor* rp = [MTLRenderPassDescriptor renderPassDescriptor];
    rp.colorAttachments[0].texture = dst; rp.colorAttachments[0].storeAction = MTLStoreActionStore;
    id<MTLCommandBuffer> cb = [s_queue commandBuffer];
    id<MTLRenderCommandEncoder> enc = [cb renderCommandEncoderWithDescriptor:rp];
    [enc setRenderPipelineState:pso]; [enc setFragmentTexture:depth atIndex:0];
    [enc setFragmentSamplerState:s_eng_point_sampler atIndex:0];
    [enc drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3]; [enc endEncoding];
    [cb commit]; [cb waitUntilCompleted]; assert(!cb.error);
    float value = 0;
    [dst getBytes:&value bytesPerRow:4 fromRegion:MTLRegionMake2D(0, 0, 1, 1) mipmapLevel:0];
    return value;
}

static unsigned stencil_value(id<MTLTexture> depth)
{
    id<MTLBuffer> dst = [s_dev newBufferWithLength:256 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> cb = [s_queue commandBuffer];
    id<MTLBlitCommandEncoder> enc = [cb blitCommandEncoder];
    [enc copyFromTexture:depth sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0)
        sourceSize:MTLSizeMake(1, 1, 1) toBuffer:dst destinationOffset:0
        destinationBytesPerRow:256 destinationBytesPerImage:256 options:MTLBlitOptionStencilFromDepthStencil];
    [enc endEncoding]; [cb commit]; [cb waitUntilCompleted]; assert(!cb.error);
    return *(unsigned char*)dst.contents;
}

/* Frame-cap pacing: 60 fps with +/-1 ms jitter shows every frame at a 60 cap,
 * alternate frames at 30, all at 120; uncapped always shows. */
static unsigned cap_shown(unsigned cap, double jitter)
{
    double next = 0; unsigned shown = 0;
    for (int i = 1; i <= 600; i++) {
        double now = i / 60.0 + ((i * 7) % 3 - 1) * jitter;
        if (rsx_host_cap_due(now, cap, next)) { shown++; next = rsx_host_cap_next(now, cap, next); }
    }
    return shown;
}

int main(int argc, char** argv)
{
    assert(cap_shown(60, 0.001) == 600 && cap_shown(0, 0.001) == 600);
    assert(cap_shown(120, 0.001) == 600 && cap_shown(30, 0.001) == 300);
    @autoreleasepool {
        s_dev = MTLCreateSystemDefaultDevice();
        if (!s_dev) { puts("[AG-metal] SKIP: no Metal device"); return 77; }
        s_queue = [s_dev newCommandQueue]; assert(s_queue);
        assert(eng_init(NULL, 1280, 720) == 0);
        const u8 seed[24] = {128,64,32,255,128,64,32,255,128,64,32,255,
                            128,64,32,255,128,64,32,255,128,64,32,255};
        u32 color = eng_color_target_create(NULL, RSX_BE_FMT_R8G8B8A8, 3, 2, seed, 12);
        u32 other = eng_color_target_create(NULL, RSX_BE_FMT_R8G8B8A8, 3, 2, seed, 12);
        u32 view = eng_surface_view(NULL, color, 0xAAE4, 0x8B);
        u32 depth = eng_depth_target_create(NULL, 3, 2);
        u32 uploaded = eng_texture_create(NULL, RSX_BE_FMT_R8G8B8A8, 3, 2, 1, 1, 0xAAE4, 0x8B);
        assert(color && other && view && depth && uploaded);
        MTLRenderPassDescriptor* clear = [MTLRenderPassDescriptor renderPassDescriptor];
        clear.depthAttachment.texture = eng_obj(depth);
        clear.depthAttachment.loadAction = MTLLoadActionClear;
        clear.depthAttachment.storeAction = MTLStoreActionStore; clear.depthAttachment.clearDepth = 0.375;
        clear.stencilAttachment.texture = eng_obj(depth);
        clear.stencilAttachment.loadAction = MTLLoadActionClear;
        clear.stencilAttachment.storeAction = MTLStoreActionStore; clear.stencilAttachment.clearStencil = 91;
        id<MTLCommandBuffer> cb = [s_queue commandBuffer];
        [[cb renderCommandEncoderWithDescriptor:clear] endEncoding]; [cb commit];
        for (unsigned scale = 2; scale <= 6; scale++) {
            if (scale == 5) continue;
            rsx_metal_backend_configure(scale, 0, 0, 1, 60); eng_apply_host_settings();
            assert(s_eng_scale == scale);
            assert(eng_obj(color).width == rsx_host_scale_edge(3, scale));
            assert(eng_obj(color).height == rsx_host_scale_edge(2, scale));
            assert(eng_obj(view).width == eng_obj(color).width);
            assert(eng_obj(other).width == eng_obj(color).width);
            assert(eng_obj(uploaded).width == 3 && eng_obj(uploaded).height == 2);
            assert(s_eng_native[color-1].w == 3 && s_eng_native[color-1].h == 2);
            u8 output[24] = {0}; eng_readback(NULL, color, 0, 0, 3, 2, output, 12);
            assert(memcmp(seed, output, sizeof seed) == 0);
            assert(fabsf(depth_value(eng_obj(depth)) - 0.375f) < 0.0001f);
            assert(stencil_value(eng_obj(depth)) == 91);
            puts("[AG-metal] scaled target + MRT + RTT view, native upload/readback, retained depth/stencil: PASS");
        }
        rsx_metal_backend_configure(2, 0, 0, 1, 60); eng_apply_host_settings();
        assert(eng_obj(color).width == 3 && stencil_value(eng_obj(depth)) == 91);

        // Exercise the actual draw encoder's scaled viewport/scissor on GPU.
        id<MTLLibrary> lib = [s_dev newLibraryWithSource:
            @"#include <metal_stdlib>\nusing namespace metal;\nfragment float4 red() { return float4(1,0,0,1); }"
            options:nil error:nil]; assert(lib);
        MTLRenderPipelineDescriptor* pd = [MTLRenderPipelineDescriptor new];
        pd.vertexFunction = [s_eng_helper_lib newFunctionWithName:@"eng_fullscreen_vs"];
        pd.fragmentFunction = [lib newFunctionWithName:@"red"];
        pd.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
        pd.depthAttachmentPixelFormat = pd.stencilAttachmentPixelFormat = MTL_DEPTH_FORMAT;
        s_eng_pipe_count = 1;
        s_eng_pipe[0].pso = [s_dev newRenderPipelineStateWithDescriptor:pd error:nil]; assert(s_eng_pipe[0].pso);
        u32 target = eng_color_target_create(NULL, RSX_BE_FMT_R8G8B8A8, 7, 5, NULL, 0);
        for (unsigned scale = 2; scale <= 4; scale++) {
            rsx_metal_backend_configure(scale, 0, 0, 1, 60); eng_apply_host_settings();
            id<MTLTexture> t = eng_obj(target);
            cb = [s_queue commandBuffer];
            EngRecord record = {0}; record.pipeline = 1; record.topology = MTLPrimitiveTypeTriangle;
            record.vertex_count = 3; record.vp[2] = 7; record.vp[3] = 5;
            record.sc[0] = record.sc[1] = 1; record.sc[2] = 4; record.sc[3] = 2;
            for (unsigned i = 0; i < RSX_BE_MAX_TEXTURES; i++) record.samp[i] = -1;
            for (unsigned i = 0; i < RSX_BE_MAX_VERTEX_TEXTURES; i++) record.vsamp[i] = -1;
            record.rt[0] = target; record.nrt = 1;
            const float black[4] = {0,0,0,1};
            eng_clear_color(NULL, target, black);
            s_eng_rec[s_eng_rec_count++] = record;
            eng_encode_records(cb, nil); s_eng_rec_count = 0;
            u32 fallback = s_eng_native[target-1].fallback_depth;
            assert(eng_obj(fallback).width == t.width && eng_obj(fallback).height == t.height);
            [cb commit]; [cb waitUntilCompleted]; assert(!cb.error);
            u8* pixels = calloc(t.width * t.height, 4);
            [t getBytes:pixels bytesPerRow:t.width*4 fromRegion:MTLRegionMake2D(0,0,t.width,t.height) mipmapLevel:0];
            for (unsigned y = 0; y < t.height; y++) for (unsigned x = 0; x < t.width; x++) {
                BOOL inside = x >= eng_scaled(1) && x < eng_scaled(5) && y >= eng_scaled(1) && y < eng_scaled(3);
                assert(pixels[(y*t.width+x)*4] == (inside ? 255 : 0));
            }
            free(pixels);
        }
        puts("[AG-metal] actual scaled viewport/scissor pixels + target-sized fallback depth: PASS");
        conversion_chain(argc > 1 ? argv[1] : NULL);
    }
    return 0;
}
