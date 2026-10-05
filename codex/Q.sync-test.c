/* Focused synchronization regressions; no game data required. */
#include "../ps3recomp/libs/video/cellGcmSys.c"
#include <pthread.h>
#include <assert.h>
#include <unistd.h>

uint8_t* vm_base;
int g_resv_store_active;
uint32_t g_ww_lo, g_ww_hi;
int spu_coh_is_reserved(uint32_t ea) { (void)ea; return 0; }
void spu_lockline_lock(void) {}
void spu_lockline_unlock(void) {}
void spu_coh_notify_write(uint32_t ea) { (void)ea; }
void ppu_resv_break_store(uint64_t ea) { (void)ea; }
void ps3_ww_report_inline(uint32_t ea, uint64_t v, int n) { (void)ea; (void)v; (void)n; }
static atomic_int returned;
static void* flip_wait(void* arg)
{
    (void)arg;
    cellGcmSetWaitFlip();
    returned = 1;
    return NULL;
}
static void* recycle(void* arg)
{
    cellGcm_fifo_recycle((u32)(uintptr_t)arg);
    returned = 1;
    return NULL;
}
static void ack(u32 ea)
{
    atomic_store_explicit(&g_gcm_fifo_drained_ea, ea, memory_order_release);
    gcm_progress_notify();
}
int main(void)
{
    /* These checks isolate completion ordering; T checks real VSYNC pacing. */
    s_flip_mode = CELL_GCM_DISPLAY_HSYNC;
    ppu_hle_inject_base = 0x10000;
    vm_base = calloc(1, 2 * 1024 * 1024);
    assert(vm_base);
    pthread_t thread;
    s_flip_status = CELL_GCM_FLIP_STATUS_WAITING;
    s_flip_request_count = 1;
    s_flip_pending = 1;
    assert(!pthread_create(&thread, NULL, flip_wait, NULL));
    usleep(2000);
    cellGcmTickFlip();
    assert(!returned && s_flip_status == CELL_GCM_FLIP_STATUS_WAITING);
    assert(cellGcm_take_flip_pending());
    cellGcmTickFlip();
    pthread_join(thread, NULL);
    assert(returned && s_flip_status == CELL_GCM_FLIP_STATUS_DONE);
    cellGcmSetWaitFlip(); /* completion before registration must not be lost */
    puts("PASS flip waits for presented frame, completion before/after registration");
    s_flip_status = CELL_GCM_FLIP_STATUS_WAITING; /* unrelated later producer */
    s_flip_request_count = 2;
    cellGcm_wait_flip_count(1);
    assert(s_flip_status == CELL_GCM_FLIP_STATUS_WAITING);
    u64 generation = gcm_progress_begin();
    gcm_progress_notify();
    gcm_progress_wait(generation, INFINITE);
    puts("PASS RESC target completion independent of later GCM flip, no lost generation wake");

    const u32 ctx = 0x2000, begin = 0x100000, tail = begin + 0x100;
    memset(s_io_address_table, 0xff, sizeof(s_io_address_table));
    memset(s_ea_address_table, 0xff, sizeof(s_ea_address_table));
    populate_offset_table(begin, 0, 0x100000);
    vm_write32(ctx, begin);
    vm_write32(ctx + 4, begin + 0x10000);
    vm_write32(ctx + 8, tail);
    ack(begin); /* stale ack from previous lap must not permit overwrite */
    /* Flip retirement also kicks this auto-reset event. Consume those older
     * kicks so the following waits identify this recycle's tail and jump. */
    while (WaitForSingleObject(cellGcm_fifo_kick_event(), 0) == WAIT_OBJECT_0) {}
    returned = 0;
    assert(!pthread_create(&thread, NULL, recycle, (void*)(uintptr_t)ctx));
    assert(WaitForSingleObject(cellGcm_fifo_kick_event(), 1000) == WAIT_OBJECT_0);
    assert(!returned && vm_read32(ctx + 8) == tail);
    ack(tail);
    assert(WaitForSingleObject(cellGcm_fifo_kick_event(), 1000) == WAIT_OBJECT_0);
    assert(vm_read32(tail) == 0x20000000 && !returned);
    ack(begin);
    pthread_join(thread, NULL);
    assert(returned && vm_read32(ctx + 8) == begin);
    puts("PASS recycle requires tail then jump acknowledgments, preserving unread commands");

    s_ref_qhead = s_ref_qtail = 0;
    gcm_ref_push_at(10, 0);
    gcm_ref_push_at(11, 0);
    gcm_ref_publish_one();
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 8) == 10);
    gcm_ref_publish_one();
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 8) == 10);
    usleep(300);
    gcm_ref_publish_one();
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR + 8) == 11);
    puts("PASS back-to-back drain/poll publishers preserve ordered fence visibility");

    s_gcm_initialized = 1;
    gcm_start_put_watch();
    usleep(2000);
    while (WaitForSingleObject(cellGcm_fifo_kick_event(), 0) == WAIT_OBJECT_0) {}
    vm_write32(GCM_CONTROL_GUEST_ADDR, 0x100);
    ps3_poll_notify(GCM_CONTROL_GUEST_ADDR, 4);
    assert(WaitForSingleObject(cellGcm_fifo_kick_event(), 1000) == WAIT_OBJECT_0);
    puts("PASS committed put store wakes notified bridge and render event");
    s_fifo_wait_label_value = 7;
    s_fifo_wait_label_ea = GCM_LABEL_GUEST_BASE + 0x20;
    usleep(2000);
    vm_write32(s_fifo_wait_label_ea, 7);
    ps3_poll_notify(s_fifo_wait_label_ea, 4);
    assert(WaitForSingleObject(cellGcm_fifo_kick_event(), 1000) == WAIT_OBJECT_0);
    s_fifo_wait_label_ea = 0;
    s_gcm_initialized = 0;
    puts("PASS CPU label release wakes blocked RSX acquire without moving put");
    /* The watcher check only submits dummy bytes. Leave an empty FIFO for
     * the subsequent T flip-order tests, which have no command consumer. */
    vm_write32(GCM_CONTROL_GUEST_ADDR + 4, vm_read32(GCM_CONTROL_GUEST_ADDR));
    return 0;
}
