/* Exercise the real FIFO walker with pending VSYNC and a mid-frame wrap. */
#define main q_sync_checks
#include "Q.sync-test.c"
#undef main

ps3_guest_caller_fn g_ps3_guest_caller;
PPU_THREAD_LOCAL ppu_context* g_active_ctx;
void ppu_dump_guest_stack(ppu_context* ctx, const char* tag) { (void)ctx; (void)tag; }
void ppu_dump_bctrl_ring(uint32_t id, const char* tag) { (void)id; (void)tag; }

/* Rendering is disabled here; FIFO parsing, semaphore writes and cursor
 * publication are real. No GPU is needed to test scheduling boundaries. */
u32 g_rsx_last_reference;
int rsx_draw_engine_enabled(void) { return 1; }
int rsx_live_draw_enabled(void) { return 0; }
static u32 conversion[6], converted;
void rsx_draw_engine_method(u32 m, u32 v) {
    if (m >= 0xE900 && m <= 0xE914) {
        conversion[(m-0xE900)/4] = v;
        if (m == 0xE914) { assert(!s_fifo_flip_reached); ++converted; }
    }
}
void rsx_draw_engine_set_display_buffer(u32 id, u32 location, u32 offset, u32 pitch, u32 w, u32 h)
{ (void)id; (void)location; (void)offset; (void)pitch; (void)w; (void)h; }
void rsx_draw_engine_upload_color(u32 l, u32 o, u32 p, u32 x, u32 y, u32 w)
{ (void)l; (void)o; (void)p; (void)x; (void)y; (void)w; }
int rsx_draw_engine_blit(u32 sl, u32 src, u32 sp, float x, float y, float sx, float sy,
                         u32 dl, u32 dst, u32 dp, u32 dx, u32 dy, u32 w, u32 h, int linear)
{ (void)sl; (void)src; (void)sp; (void)x; (void)y; (void)sx; (void)sy; (void)dl;
  (void)dst; (void)dp; (void)dx; (void)dy; (void)w; (void)h; (void)linear; return 0; }
void rsx_live_draw_method(u32 m, u32 v) { (void)m; (void)v; }
void rsx_state_init(rsx_state* state) { memset(state, 0, sizeof *state); }
int rsx_process_method(rsx_state* state, u32 m, u32 v)
{ (void)state; (void)m; (void)v; return 0; }
void rsx_raise_user_cmd(u32 v) { (void)v; }
int rsx_live_draw_blit(u32 a, u32 b, u32 c, u32 d, u32 e, u32 f, u32 g, u32 h)
{ (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h; return 0; }
void rsx_live_draw_note_resolve(u32 a, u32 b, u32 c, u32 d)
{ (void)a; (void)b; (void)c; (void)d; }
int rsx_live_draw_resolve_blit(u32 a, u32 b, u32 c, u32 d, u32 e, u32 f,
                              u32 g, u32 h, u32 i, u32 j, u32 k, u32 l)
{ (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h;
  (void)i; (void)j; (void)k; (void)l; return 0; }

void rsx_draw_engine_record_begin(void) {}
void rsx_draw_engine_record_packet(u32 offset, const void* data, u32 bytes)
{ (void)offset; (void)data; (void)bytes; }
rsx_backend* rsx_get_backend(void) { return NULL; }
#include "libs/video/cellResc.h"
static void* resc_wait(void* context)
{
    cellRescSetWaitFlip(context); returned = 1; return NULL;
}
int main(void)
{
    assert(q_sync_checks() == 0);
    s_flip_request_count = s_presented_flip_count = s_completed_flip_count = 0;
    s_flip_pending = s_fifo_flip_reached = 0;
    s_flip_handler_opd = 0; s_host_enabled = 0;
    const u32 ctx = 0x2000, begin = 0x100000, config = 0x3000, src = 0x3100;
    s_gcm_context_ea = ctx; s_fifo_getoff = 0;
    vm_write32(ctx, begin); vm_write32(ctx + 4, begin + 0x10000); vm_write32(ctx + 8, begin);
    vm_write32(GCM_CONTROL_GUEST_ADDR, 0); vm_write32(GCM_CONTROL_GUEST_ADDR+4, 0);
    assert(cellGcmSetDisplayBuffer(0, 0x100000, 5120, 1280, 720) == CELL_OK);
    assert(cellRescInit((CellRescInitConfig*)(uintptr_t)config) == CELL_OK);
    vm_write32(src, 0xA5); vm_write32(src+4, 1024);
    vm_write16(src+8, 256); vm_write16(src+10, 256); vm_write32(src+12, 0x40000);
    assert(cellRescSetSrc(2, (CellRescSrc*)(uintptr_t)src) == CELL_OK);
    assert(cellRescSetConvertAndFlip((void*)(uintptr_t)ctx, 2) == CELL_OK);
    assert(vm_read32(ctx+8) == begin+32 && !converted && !s_fifo_flip_reached);
    assert(vm_read32(begin) == ((6u<<18)|0xE900u));
    assert(vm_read32(begin+28) == GCM_FLIP_MARKER);
    assert(s_flip_request_count == 0); // marker has not reached the walker
    pthread_t waiter; returned = 0;
    assert(!pthread_create(&waiter, NULL, resc_wait, (void*)(uintptr_t)ctx));
    usleep(2000); assert(!returned);
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR) == 32);
    vm_write32(GCM_CONTROL_GUEST_ADDR, 32);
    cellGcm_rsx_process_fifo();
    assert(converted == 1 && conversion[0] == 0x40000 && conversion[1] == 1024);
    assert(conversion[2] == 256 && conversion[3] == 256 && conversion[4] == 0xA5 && conversion[5] == 0);
    assert(s_fifo_flip_reached && s_completed_flip_count == 0);
    assert(cellGcm_take_flip_pending()); cellGcmTickFlip();
    assert(s_completed_flip_count == 1);
    pthread_join(waiter, NULL); assert(returned);
    puts("PASS RESC context/index ABI, conversion packet consumed before flip, WaitFlip blocks until one request/retirement");
    return 0;
}
