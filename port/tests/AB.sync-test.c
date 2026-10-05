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
static atomic_int ab_slow, ab_entered, ab_release;
static u32 ab_live_value;
int rsx_draw_engine_enabled(void) { return 0; }
int rsx_live_draw_enabled(void) { return 0; }
void rsx_draw_engine_method(u32 m, u32 v) { (void)m; (void)v; }
void rsx_live_draw_method(u32 m, u32 v) { (void)m; (void)v; }
void rsx_state_init(rsx_state* state) { memset(state, 0, sizeof *state); }
int rsx_process_method(rsx_state* state, u32 m, u32 v)
{
    (void)state;
    if (m == 0x50) g_rsx_last_reference = v;
    if (m == 0x104) ab_live_value = vm_read32(v);
    if (m == 0x100 && ab_slow) {
        ab_entered = 1;
        while (!ab_release) usleep(10);
    }
    return 0;
}
void rsx_raise_user_cmd(u32 v) { (void)v; }
int rsx_live_draw_blit(u32 a, u32 b, u32 c, u32 d, u32 e, u32 f, u32 g, u32 h)
{ (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h; return 0; }
void rsx_live_draw_note_resolve(u32 a, u32 b, u32 c, u32 d)
{ (void)a; (void)b; (void)c; (void)d; }
int rsx_live_draw_resolve_blit(u32 a, u32 b, u32 c, u32 d, u32 e, u32 f,
                              u32 g, u32 h, u32 i, u32 j, u32 k, u32 l)
{ (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h;
  (void)i; (void)j; (void)k; (void)l; return 0; }

static const u32 ab_begin = 0x100000, ab_ctx = 0x2000;
static void ab_reset(void)
{
    assert(s_host_head == s_host_tail);
    s_host_head = s_host_tail = s_host_executed = 0;
    s_host_submitted = s_host_get = s_host_call = s_host_read = 0;
    s_host_initialized = 1;
    s_host_packet = NULL;
    s_host_flip_ticket = UINT64_MAX;
    s_fifo_getoff = 0;
    s_fifo_flip_reached = s_flip_pending = 0;
    s_flip_request_count = s_presented_flip_count = s_completed_flip_count = 0;
    s_ref_qhead = s_ref_qtail = 0;
    s_gcm_context_ea = ab_ctx;
    s_flip_mode = CELL_GCM_DISPLAY_HSYNC;
    s_display_buffer_set[0] = 1;
    s_flip_handler_opd = 0;
    vm_write32(GCM_CONTROL_GUEST_ADDR, 0);
    vm_write32(GCM_CONTROL_GUEST_ADDR + 4, 0);
    vm_write32(GCM_CONTROL_GUEST_ADDR + 8, 0);
    memset(vm_base + ab_begin, 0, 0x1000);
    vm_write32(ab_ctx, ab_begin);
    vm_write32(ab_ctx + 4, ab_begin + 0x1000);
    vm_write32(ab_ctx + 8, ab_begin);
}
static void ab_method(u32 off, u32 method, u32 value)
{
    vm_write32(ab_begin + off, (1u << 18) | method);
    vm_write32(ab_begin + off + 4, value);
}
static void ab_submit(u32 put)
{
    vm_write32(GCM_CONTROL_GUEST_ADDR, put);
    gcm_host_snapshot(-1);
}
static void ab_drain(void)
{
    for (unsigned i = 0; s_host_head != s_host_tail && i < 100; i++) cellGcm_rsx_process_fifo();
    assert(s_host_head == s_host_tail);
}
static void* ab_execute(void* unused)
{
    (void)unused;
    cellGcm_rsx_process_fifo();
    return NULL;
}
static void* ab_copy(void* unused)
{
    (void)unused;
    gcm_host_snapshot(-1);
    returned = 1;
    return NULL;
}
int main(void)
{
    assert(!q_sync_checks());
    while (s_put_watch_started) usleep(100);
    cellGcm_fifo_enable_snapshot();
    s_gcm_initialized = 1;
    ab_reset();
    const u32 label = GCM_LABEL_GUEST_BASE + 0x20;
    vm_write32(label, 0);
    ab_method(0, 0x64, 0x20);
    ab_method(8, 0x6c, 0x1111);
    ab_method(16, 0x50, 0x1234);
    ab_method(24, 0x1800, 1u << 24);
    ab_submit(32);
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 4) == 32);
    assert(!vm_read32(label) && !vm_read32(GCM_CONTROL_GUEST_ADDR + 8));
    assert(!s_report_data[0].timestamp);
    memset(vm_base + ab_begin, 0xee, 32); /* immediately overwrite copied words */
    assert(!cellGcmSetFlipCommand(0));
    assert(!cellGcm_take_flip_pending()); /* get == put is only COPY completion */
    cellGcm_rsx_process_fifo();
    assert(vm_read32(label) == 0x1111 && vm_read32(GCM_CONTROL_GUEST_ADDR + 8) == 0x1234);
    assert(s_report_data[0].timestamp && s_report_data[0].value == 0xffff);
    assert(cellGcm_take_flip_pending()); cellGcmTickFlip();
    puts("PASS snapshot publishes get before execution; overwritten label/reference/report packets execute before direct flip");

    ab_reset(); vm_write32(label, 0);
    ab_method(0, 0x64, 0x20); ab_method(8, 0x68, 7); ab_method(16, 0x6c, 9);
    ab_submit(24);
    assert(!cellGcmSetFlipCommand(0));
    for (unsigned i = 0; i < 12; i++) cellGcm_rsx_process_fifo();
    assert(vm_read32(label) == 0 && s_host_executed == 1 && !cellGcm_take_flip_pending());
    vm_write32(label, 7); cellGcm_rsx_process_fifo();
    assert(vm_read32(label) == 9 && cellGcm_take_flip_pending()); cellGcmTickFlip();
    puts("PASS copied semaphore acquire stalls only the ordered consumer; label and flip cannot pass it");

    ab_reset(); vm_write32(label, 0);
    vm_write32(ab_begin, 0xfead0000);
    ab_method(4, 0x64, 0x20); ab_method(12, 0x6c, 33); ab_submit(20);
    cellGcm_rsx_process_fifo();
    assert(!vm_read32(label) && s_host_executed == 1);
    cellGcm_rsx_process_fifo(); assert(!vm_read32(label));
    assert(cellGcm_take_flip_pending()); cellGcmTickFlip(); ab_drain();
    assert(vm_read32(label) == 33);
    puts("PASS copied FIFO flip holds next-frame commands until its distinct presentation");

    ab_reset(); vm_write32(label, 0);
    s_host_get = 0xff0;
    vm_write32(ab_begin + 0xff0, 0x20000000u); /* cross ring end to head */
    vm_write32(ab_begin, 0x200u | 2u);       /* CALL outside submitted linear span */
    ab_method(0x200, 0x64, 0x20); ab_method(0x208, 0x6c, 77);
    vm_write32(ab_begin + 0x210, 0x00020000u);
    ab_method(4, 0x50, 88);
    ab_submit(12);
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 4) == 12);
    memset(vm_base + ab_begin, 0xcc, 0x1000);
    ab_drain(); usleep(300); cellGcm_ref_on_poll();
    assert(vm_read32(label) == 77 && vm_read32(GCM_CONTROL_GUEST_ADDR + 8) == 88);
    puts("PASS ring-end JUMP and CALL/RET resolve at snapshot time, surviving guest branch/target overwrite");

    ab_reset();
    ab_method(0, 0x64, 0x20); ab_method(8, 0x6c, 101);
    ab_submit(16); assert(!cellGcmSetFlipCommand(0));
    vm_write32(ab_begin + 16, 0x20000000u); ab_submit(0);
    ab_method(0, 0x64, 0x20); ab_method(8, 0x6c, 202); ab_submit(16);
    assert(!cellGcmSetFlipCommand(0));
    cellGcm_rsx_process_fifo(); assert(vm_read32(label) == 101);
    assert(cellGcm_take_flip_pending()); cellGcmTickFlip();
    cellGcm_rsx_process_fifo(); assert(vm_read32(label) == 202);
    assert(cellGcm_take_flip_pending()); cellGcmTickFlip(); ab_drain();
    puts("PASS direct flip tickets distinguish the same FIFO boundary across two recycled laps");

    ab_reset();
    for (u32 i = 0; i < GCM_HOST_SLOTS; i++) ab_submit((i + 1) * 4);
    assert(s_host_tail - s_host_head == GCM_HOST_SLOTS);
    vm_write32(GCM_CONTROL_GUEST_ADDR, (GCM_HOST_SLOTS + 1) * 4);
    returned = 0; pthread_t thread;
    assert(!pthread_create(&thread, NULL, ab_copy, NULL));
    usleep(2000); assert(!returned);
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 4) == GCM_HOST_SLOTS * 4);
    cellGcm_rsx_process_fifo(); pthread_join(thread, NULL); assert(returned); ab_drain();
    puts("PASS bounded rotating buffers apply backpressure without speculative get publication or dropped commands");

    ab_reset();
    vm_write32(ab_begin, (2u << 18) | 0x100);
    vm_write32(ab_begin + 4, 1);
    ab_submit(8); assert(s_host_submitted == 0 && !vm_read32(GCM_CONTROL_GUEST_ADDR + 4));
    vm_write32(ab_begin + 8, 2); ab_submit(12); ab_drain();
    assert(s_host_executed == 1);
    puts("PASS incomplete committed method packet stays unread until its entire payload is submitted");

    ab_reset();
    vm_write32(ab_begin + 0x800, 1);
    ab_method(0, 0x104, ab_begin + 0x800); ab_submit(8);
    vm_write32(ab_begin + 0x800, 2); ab_drain(); assert(ab_live_value == 2);
    puts("PASS referenced guest data is read at execution time rather than frozen with command bytes");

    ab_reset(); vm_write32(label, 0);
    ab_slow = 1; ab_entered = ab_release = 0;
    ab_method(0, 0x100, 1); ab_submit(8);
    pthread_t consumer; assert(!pthread_create(&consumer, NULL, ab_execute, NULL));
    while (!ab_entered) usleep(10);
    assert(!cellGcmSetFlipCommand(0));
    ab_method(8, 0x64, 0x20); ab_method(16, 0x6c, 909); ab_submit(24);
    ab_release = 1; pthread_join(consumer, NULL); ab_slow = 0;
    assert(!vm_read32(label) && s_host_executed == 1 && cellGcm_take_flip_pending());
    cellGcmTickFlip(); ab_drain(); assert(vm_read32(label) == 909);
    puts("PASS direct flip arriving during a render slice prevents later submitted commands passing its ticket");

    ab_reset(); vm_write32(label, 0);
    ab_method(0, 0x64, 0x20); ab_method(8, 0x6c, 10); ab_submit(16);
    cellGcm_syscall_set_fifo(0, 0);
    assert(s_host_head == s_host_tail);
    ab_method(0, 0x64, 0x20); ab_method(8, 0x6c, 20); ab_submit(16); ab_drain();
    assert(vm_read32(label) == 20);
    puts("PASS explicit FIFO reset discards staged old commands and restarts copy/execute cursors together");

    ab_reset();
    gcm_host_start();
    ab_slow = 1; ab_entered = ab_release = 0;
    ab_method(0, 0x100, 1); ab_submit(8);
    assert(!pthread_create(&consumer, NULL, ab_execute, NULL));
    while (!ab_entered) usleep(10);
    vm_write32(ab_ctx + 8, ab_begin + 0x100);
    returned = 0; assert(!pthread_create(&thread, NULL, recycle, (void*)(uintptr_t)ab_ctx));
    pthread_join(thread, NULL);
    assert(returned && vm_read32(ab_ctx + 8) == ab_begin);
    assert(s_host_executed == 0 && s_host_submitted == 64); /* first packet, NOPs + JUMP */
    memset(vm_base + ab_begin, 0xee, 0x100); /* reuse ring with renderer still blocked */
    ab_release = 1; pthread_join(consumer, NULL); ab_slow = 0;
    ab_drain();
    s_gcm_initialized = 0; SetEvent(s_host_event);
    while (s_host_started) usleep(100);
    gcm_host_shutdown();
    assert(!s_host_initialized && s_host_head == s_host_tail && !s_host_submitted);
    puts("PASS RSX copy worker acknowledges both recycle phases while render consumer is blocked inside encoding; shutdown clears staging");
    return 0;
}
