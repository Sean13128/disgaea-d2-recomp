#define main original_engine_tests
#include "libs/video/tests/test_rsx_draw_engine.c"
#undef main

static unsigned copies, resolves;
static u32 copy_src, copy_dst, copy_dest[4];
static float copy_rect[4];
static u8 uploaded_pixel[4];
static void copy(void* user, u32 src, u32 dst, float sx, float sy, float sw, float sh,
                 u32 dx, u32 dy, u32 dw, u32 dh, int linear)
{
    (void)user; (void)linear;
    ++copies; copy_src = src; copy_dst = dst;
    copy_rect[0] = sx; copy_rect[1] = sy; copy_rect[2] = sw; copy_rect[3] = sh;
    copy_dest[0] = dx; copy_dest[1] = dy; copy_dest[2] = dw; copy_dest[3] = dh;
}
static void read_native(void* user, u32 surface, u32 x, u32 y, u32 w, u32 h, void* output, u32 pitch)
{
    (void)user; (void)surface; (void)x; (void)y;
    ++resolves;
    for (u32 row = 0; row < h; row++) for (u32 col = 0; col < w; col++)
        memcpy((u8*)output + row*pitch + col*4, g_stub_pixel, 4);
}
static void upload(void* user, u32 texture, u32 face, u32 mip, u32 w, u32 h,
                    const void* src, u32 pitch, u32 rows)
{
    memcpy(uploaded_pixel, src, 4);
    stub_texture_upload(user, texture, face, mip, w, h, src, pitch, rows);
}
int main(void)
{
    if (original_engine_tests()) return 1;
    vm_base = calloc(1, GUEST_BYTES); ppu_vm_size = GUEST_BYTES;
    rsx_draw_engine_set_display_buffer(0, RSX_LOCATION_LOCAL, 0x100000, 5120, 1280, 720);
    engine_up();
    rsx_draw_backend backend = g_stub_backend;
    backend.blit = copy; backend.readback = read_native; backend.texture_upload = upload;
    rsx_draw_engine_set_backend(&backend);
    m(M_CLEAR_BUFFERS, 0xF0u);
    const u32 source = stub.cleared[0];
    const u32 resc[6] = {0x40000, 1024, 256, 256, 0xA5, 0};
    for (u32 i = 0; i < 6; i++) m(0xE900 + i*4, resc[i]);
    CHECK(copies == 1 && copy_src == source && copy_dst != source, "RESC copies into display registered before backend initialization");
    CHECK(copy_rect[2] == 256 && copy_rect[3] == 256 && copy_dest[2] == 1280 && copy_dest[3] == 720,
          "RESC passes native source/destination rectangles without double scaling");
    rsx_draw_engine_present_buffer(0);
    CHECK(presented_surface == copy_dst, "flip presents RESC destination instead of current offscreen target");
    CHECK(rsx_draw_engine_blit(0, 0x40000, 1024, 2, 3, .5f, .25f, 0, 0x100000, 5120, 7, 8, 40, 32, 1),
          "NV3089-style scaled partial copy stays on GPU");
    CHECK(copy_rect[0] == 2 && copy_rect[1] == 3 && copy_rect[2] == 20 && copy_rect[3] == 8 &&
          copy_dest[0] == 7 && copy_dest[1] == 8, "scaled transfer preserves origins, steps and destination rectangle");
    const unsigned before = copies;
    CHECK(rsx_draw_engine_blit(0, 0x40000, 1024, 0, 0, 1, 1, 0, 0x40000, 1024, 0, 0, 256, 256, 1) && copies == before,
          "D2 same-address RESC conversion is a no-op");
    CHECK(rsx_draw_engine_blit(0, 0x40000, 1024, 0, 0, 1, 1, 0, 0x40000, 1024, 1, 1, 100, 100, 0) && copy_src == copy_dst,
          "overlapping target copy uses backend snapshot instead of native memory");
    CHECK(!rsx_draw_engine_blit(0, 0x40000, 1024, 0, 0, 1, 1, 1, 0x200000, 1024, 0, 0, 256, 256, 0) && resolves == 1,
          "RTT copy into guest memory resolves native pixels before CPU transfer");
    const u8 argb[4] = {0x44,0x11,0x22,0x33};
    CHECK(!memcmp(vm_base + GUEST_LOCAL_EA + 0x40000, argb, 4), "native readback restores guest ARGB order");
    memcpy(vm_base + GUEST_LOCAL_EA + 0x100000 + 9*5120 + 12*4, argb, 4);
    rsx_draw_engine_upload_color(0, 0x100000, 5120, 12, 9, 1);
    CHECK(!memcmp(uploaded_pixel, g_stub_pixel, 4) && copy_dest[0] == 12 && copy_dest[1] == 9 && copy_dest[2] == 1,
          "NV308A native color upload targets the scaled surface through native coordinates");
    engine_down(); free(vm_base);
    printf(g_failures ? "AG2 checks FAILED\n" : "AG2 conversion checks passed\n");
    return g_failures ? 1 : 0;
}
