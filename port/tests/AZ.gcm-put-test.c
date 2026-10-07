/* HLE flush must notify the fallback PUT watcher, not only kick render. */
#include "libs/video/cellGcmSys.c"
#include <assert.h>
#include <pthread.h>
#include <sched.h>
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
static _Atomic int ready;
static void* wait_put(void* unused)
{
    (void)unused;
    u32 raw = 0;
    /* Deliberately extend the diagnostic wait to 8ms, proving a notification
     * arrives well before timeout. Caller always re-reads the control word. */
    for (unsigned i = 0; i < 8; i++) ps3_poll_backoff_idle_graphics(40, GCM_CONTROL_GUEST_ADDR, &raw, 4);
    ready = 1;
    ps3_poll_backoff_idle_graphics(40, GCM_CONTROL_GUEST_ADDR, &raw, 4);
    return NULL;
}
int main(void)
{
    ppu_hle_inject_base = 0x10000;
    vm_base = calloc(1, 2 * 1024 * 1024); assert(vm_base);
    const u32 ctx = 0x30000, begin = 0x100000;
    s_io_address_table[begin >> 20] = 0;
    vm_write32(ctx, begin); vm_write32(ctx + 4, begin + 0x1000);
    vm_write32(ctx + 8, begin + 0x100);
    pthread_t waiter;
    assert(!pthread_create(&waiter, NULL, wait_put, NULL));
    /* Allow the ladder to settle; synchronize with its registered wait. */
    while (!ready) sched_yield();
    while (!__atomic_load_n(&ps3_poll_waiters, __ATOMIC_ACQUIRE)) sched_yield();
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    const u64 start = (u64)t.tv_sec * 1000000000ULL + t.tv_nsec;
    cellGcmFlushContext((void*)(uintptr_t)ctx);
    pthread_join(waiter, NULL);
    clock_gettime(CLOCK_MONOTONIC, &t);
    const u64 elapsed = (u64)t.tv_sec * 1000000000ULL + t.tv_nsec - start;
    assert(vm_read32(GCM_CONTROL_GUEST_ADDR) == 0x100);
    assert(elapsed < 5000000ULL);
    puts("HLE PUT: cellGcmFlushContext wakes memory watcher before 8ms fallback PASS");
    free(vm_base);
    return 0;
}
