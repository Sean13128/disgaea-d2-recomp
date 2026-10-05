/* Q's synchronization checks plus the vblank/flip firmware contract. */
#define main q_sync_checks
#include "Q.sync-test.c"
#undef main

static unsigned flips_delivered, vblanks_delivered;
void cellResc_notify_flip(void) { flips_delivered++; }
void cellResc_notify_vblank(void) { vblanks_delivered++; }
ps3_guest_caller_fn g_ps3_guest_caller;
PPU_THREAD_LOCAL ppu_context* g_active_ctx;
void ppu_dump_guest_stack(ppu_context* ctx, const char* tag) { (void)ctx; (void)tag; }
void ppu_dump_bctrl_ring(uint32_t id, const char* tag) { (void)id; (void)tag; }
static unsigned guest_flips;
static void callback(uint32_t opd, uint64_t a, uint64_t b, uint64_t c, uint64_t d,
                     uint64_t e, uint64_t f, uint64_t g, uint64_t h)
{
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h;
    assert(opd == 0x1000);
    guest_flips++;
}
static void* enqueue(void* unused)
{
    (void)unused;
    gcm_queue_flip(0);
    returned = 1;
    return NULL;
}

static void next_vblank(void)
{
    u64 before = cellGcmGetVBlankCount();
    do { usleep(200); } while (cellGcmGetVBlankCount() == before);
    cellGcmTickVBlank();
}

int main(void)
{
    /* Old Q checks test presentation ordering without a real display clock. */
    s_flip_mode = CELL_GCM_DISPLAY_HSYNC;
    assert(q_sync_checks() == 0);
    s_flip_request_count = s_presented_flip_count = s_completed_flip_count = 0;
    s_flip_pending = 0;
    s_flip_status = CELL_GCM_FLIP_STATUS_DONE;
    s_last_present_vblank = 0;
    s_vblank_epoch_ns = get_timestamp_ns();
    s_vblank_count = 0;
    GCM_PENDING_TAKE();
    s_flip_mode = CELL_GCM_DISPLAY_VSYNC;

    u64 before = cellGcmGetVBlankCount();
    for (unsigned i = 0; i < 1000; i++) assert(cellGcmGetVBlankCount() == before);
    cellGcmTickVBlank();
    cellGcmTickVBlank();
    assert(cellGcmGetVBlankCount() == before);
    usleep(55000);
    assert(cellGcmGetVBlankCount() >= before + 3);
    puts("PASS vblank reads/tick calls do not manufacture ticks; clock advances without flips or presentation");

    next_vblank(); /* submit close to a fresh tick */
    s_display_buffer_set[0] = s_display_buffer_set[1] = 1;
    s_flip_handler_opd = 0x1000;
    g_ps3_guest_caller = callback;
    assert(cellGcmSetFlipCommand(0) == CELL_OK);
    assert(cellGcmSetFlipCommand(1) == CELL_OK);
    assert(!guest_flips);
    vm_write32(GCM_LABEL_GUEST_BASE + 0x10, 1);
    u64 last_flip = cellGcmGetLastFlipTime();
    assert(!cellGcm_take_flip_pending());
    cellGcmTickFlip();
    ppu_gcm_pump();
    assert(!flips_delivered && s_completed_flip_count == 0);
    assert(cellGcmGetLastFlipTime() == last_flip);
    assert(vm_read32(GCM_LABEL_GUEST_BASE + 0x10) == 1);
    returned = 0;
    pthread_t waiter;
    assert(!pthread_create(&waiter, NULL, flip_wait, NULL));
    usleep(2000);
    assert(!returned);
    next_vblank();
    assert(cellGcm_take_flip_pending());
    assert(s_current_display_buffer_id == 0);
    assert(!returned && !cellGcm_take_flip_pending()); /* submitted, not completed */
    cellGcmTickFlip();
    ppu_gcm_pump();
    assert(flips_delivered == 1 && guest_flips == 1 && s_completed_flip_count == 1);
    assert(vm_read32(GCM_LABEL_GUEST_BASE + 0x10) == 0);
    assert(cellGcmGetLastFlipTime() > last_flip);
    assert(cellGcmGetLastFlipTime() <= get_timestamp_ns() / 1000);
    cellGcm_wait_flip_count(1); /* RESC's first flip, independent of second */
    assert(!returned && !cellGcm_take_flip_pending());
    next_vblank();
    assert(cellGcm_take_flip_pending() && s_current_display_buffer_id == 1);
    cellGcmTickFlip();
    ppu_gcm_pump();
    pthread_join(waiter, NULL);
    assert(returned && flips_delivered == 2 && guest_flips == 2 && cellGcmGetFlipStatus() == 0);
    puts("PASS two queued VSYNC flips retire separately on subsequent vblanks; status/label/time/handlers and waits follow presentation");

    next_vblank();
    for (unsigned i = 0; i < 4; i++) gcm_queue_flip(i);
    before = cellGcmGetVBlankCount();
    usleep(100000); /* slow/occluded backend: skip missed presents */
    assert(cellGcmGetVBlankCount() >= before + 6);
    assert(cellGcm_take_flip_pending());
    cellGcmTickFlip();
    assert(!cellGcm_take_flip_pending());
    puts("PASS missed refreshes advance counters without bursting queued VSYNC completions");
    s_flip_mode = CELL_GCM_DISPLAY_HSYNC;
    for (unsigned i = 1; i < 4; i++) {
        assert(cellGcm_take_flip_pending());
        cellGcmTickFlip();
    }
    assert(!cellGcm_take_flip_pending());
    puts("PASS HSYNC permits presentation without waiting for another vblank");
    for (unsigned i = 0; i < GCM_FLIP_QUEUE_SIZE; i++) gcm_queue_flip(0);
    returned = 0;
    assert(!pthread_create(&waiter, NULL, enqueue, NULL));
    usleep(2000);
    assert(!returned);
    assert(cellGcm_take_flip_pending());
    cellGcmTickFlip();
    pthread_join(waiter, NULL);
    assert(returned);
    for (unsigned i = 0; i < GCM_FLIP_QUEUE_SIZE; i++) {
        assert(cellGcm_take_flip_pending());
        cellGcmTickFlip();
    }
    assert(!cellGcm_take_flip_pending());
    puts("PASS full flip queue backpressure wakes on completion and loses no queued flips");
    return 0;
}
