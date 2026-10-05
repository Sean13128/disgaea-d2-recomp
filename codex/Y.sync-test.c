/* Exercise the real FIFO walker with pending VSYNC and a mid-frame wrap. */
#define main q_sync_checks
#include "Q.sync-test.c"
#undef main

void cellResc_notify_flip(void) {}
void cellResc_notify_vblank(void) {}
ps3_guest_caller_fn g_ps3_guest_caller;
PPU_THREAD_LOCAL ppu_context* g_active_ctx;
void ppu_dump_guest_stack(ppu_context* ctx, const char* tag) { (void)ctx; (void)tag; }
void ppu_dump_bctrl_ring(uint32_t id, const char* tag) { (void)id; (void)tag; }

/* Rendering is disabled here; FIFO parsing, semaphore writes and cursor
 * publication are real. No GPU is needed to test scheduling boundaries. */
u32 g_rsx_last_reference;
int rsx_draw_engine_enabled(void) { return 0; }
int rsx_live_draw_enabled(void) { return 0; }
void rsx_draw_engine_method(u32 m, u32 v) { (void)m; (void)v; }
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

int main(void)
{
    assert(q_sync_checks() == 0);
    s_flip_request_count = s_presented_flip_count = s_completed_flip_count = 0;
    s_flip_pending = 0;
    s_vblank_epoch_ns = get_timestamp_ns();
    const u32 ctx = 0x2000, begin = 0x100000, tail = begin + 0x100;
    s_gcm_context_ea = ctx;
    s_fifo_getoff = 0;
    s_fifo_flip_reached = 0;
    vm_write32(GCM_CONTROL_GUEST_ADDR, 0);
    vm_write32(GCM_CONTROL_GUEST_ADDR + 4, 0);
    ack(begin);
    s_flip_mode = CELL_GCM_DISPLAY_VSYNC;
    s_display_buffer_set[0] = 1;
    s_flip_handler_opd = 0;
    memset(vm_base + begin, 0, 0x1000); /* NOPs, followed by a real label write */
    vm_write32(begin, (1u << 18) | 0x64);
    vm_write32(begin + 4, 0x20);
    vm_write32(begin + 8, (1u << 18) | 0x6c);
    vm_write32(begin + 12, 0x1234);
    vm_write32(ctx, begin);
    vm_write32(ctx + 4, begin + 0x1000);
    vm_write32(ctx + 8, tail);
    vm_write32(GCM_CONTROL_GUEST_ADDR, tail - begin);
    u32 target = s_flip_request_count + 1;
    assert(cellGcmSetFlipCommand(0) == CELL_OK);
    usleep(20000); /* already eligible by clock, still has unread commands */
    assert(!cellGcm_take_flip_pending());
    assert(!s_fifo_flip_reached && s_flip_pending);
    returned = 0;
    pthread_t thread;
    assert(!pthread_create(&thread, NULL, recycle, (void*)(uintptr_t)ctx));
    assert(WaitForSingleObject(cellGcm_fifo_kick_event(), 1000) == WAIT_OBJECT_0);
    cellGcm_rsx_process_fifo();
    assert(gcm_fifo_drained() == tail);
    assert(vm_read32(GCM_LABEL_GUEST_BASE + 0x20) == 0x1234);
    assert(s_fifo_flip_reached && s_completed_flip_count < target);
    assert(cellGcm_take_flip_pending());
    cellGcmTickFlip();
    /* The jump and remaining commands may drain only after retiring this
     * reached boundary. Consumption BEFORE it never waited for presentation. */
    for (unsigned n = 0; !returned && n < 100; n++) {
        cellGcm_fifo_kick_wait(1);
        cellGcm_rsx_process_fifo();
    }
    assert(returned);
    pthread_join(thread, NULL);
    assert(vm_read32(ctx + 8) == begin && gcm_fifo_drained() == begin);
    puts("PASS pending VSYNC drains earlier commands and acknowledges ring tail before presentation; jump resumes after boundary retirement");
    /* A frame larger than the ring has no flip yet. Both tail and jump must
     * recycle while its records remain unpresented. */
    s_fifo_getoff = 0;
    vm_write32(GCM_CONTROL_GUEST_ADDR, 0);
    vm_write32(GCM_CONTROL_GUEST_ADDR + 4, 0);
    ack(begin);
    vm_write32(ctx + 8, tail);
    vm_write32(tail, 0);
    returned = 0;
    assert(!pthread_create(&thread, NULL, recycle, (void*)(uintptr_t)ctx));
    for (unsigned n = 0; !returned && n < 100; n++) {
        cellGcm_fifo_kick_wait(1);
        cellGcm_rsx_process_fifo();
    }
    assert(returned);
    pthread_join(thread, NULL);
    assert(s_completed_flip_count == target);
    puts("PASS mid-frame ring-full flush drains and recycles without a flip or vblank presentation");
    /* Keep next-frame methods behind a decoded flip. Making all pending
     * requests drainable would merge the next frame into this batch. */
    vm_write32(begin, 0xFEAD0000);
    vm_write32(begin + 4, (1u << 18) | 0x64);
    vm_write32(begin + 8, 0x20);
    vm_write32(begin + 12, (1u << 18) | 0x6c);
    vm_write32(begin + 16, 0x5678);
    vm_write32(GCM_CONTROL_GUEST_ADDR, 20);
    cellGcm_rsx_process_fifo();
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 4) == 4);
    assert(vm_read32(GCM_LABEL_GUEST_BASE + 0x20) == 0x1234);
    cellGcm_rsx_process_fifo();
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 4) == 4);
    usleep(20000);
    assert(cellGcm_take_flip_pending());
    cellGcmTickFlip();
    cellGcm_rsx_process_fifo();
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 4) == 20);
    assert(vm_read32(GCM_LABEL_GUEST_BASE + 0x20) == 0x5678);
    puts("PASS decoded FIFO flip holds only subsequent commands through presentation; no next-frame batch mixing");
    return 0;
}
