/* ThreadSanitizer target: the cellAudio mixer thread started and stopped from
 * competing threads, which must neither double-create nor double-join it. */
#include "libs/audio/cellAudio.c"
#include <assert.h>

uint8_t* vm_base;
int g_resv_store_active;
uint32_t g_ww_lo, g_ww_hi;
void ppu_resv_break_store(uint64_t a) { (void)a; }
void ps3_ww_report_inline(uint32_t a, uint64_t v, int w) { (void)a; (void)v; (void)w; }
int spu_coh_is_reserved(uint32_t a) { (void)a; return 0; }
void spu_coh_notify_write(uint32_t a) { (void)a; }
void spu_lockline_lock(void) {}
void spu_lockline_unlock(void) {}
void guest_poll_notify(uint32_t a, uint32_t n) { (void)a; (void)n; }
void cellAtracHostCheckStalls(uint64_t n, int running) { (void)n; (void)running; }
uint32_t sys_event_find_queue_by_key(uint64_t key) { (void)key; return 0; }
int sys_event_queue_push_by_id(uint32_t q, uint64_t s, uint64_t a, uint64_t b, uint64_t c)
{
    (void)q; (void)s; (void)a; (void)b; (void)c;
    return 0;
}

static void* cycle(void* arg)
{
    (void)arg;
    for (int i = 0; i < 40; i++) {
        audio_stop_mix_thread();
        assert(audio_start_mix_thread() == 0);
    }
    return NULL;
}

int main(void)
{
    setenv("SDL_AUDIODRIVER", "dummy", 1);
    assert(cellAudioInit() == CELL_OK);
    pthread_t a, b;
    assert(!pthread_create(&a, NULL, cycle, NULL));
    assert(!pthread_create(&b, NULL, cycle, NULL));
    pthread_join(a, NULL);
    pthread_join(b, NULL);
    assert(cellAudioQuit() == CELL_OK);
    puts("PASS: concurrent mixer start/stop");
    return 0;
}
