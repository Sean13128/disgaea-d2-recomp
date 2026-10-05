/* Z: stall the real cellAudio thread with a 512-frame host callback and an
 * asynchronous guest producer. No CoreAudio or game assets are required.
 * clang -std=gnu17 -O2 -Ips3recomp/include -I/opt/homebrew/include
 *   codex/Z.audio-clock.c -L/opt/homebrew/lib -lSDL2 -Wl,-dead_strip -o <scratch>/clock
 *   AUDIO_RATE=1 <scratch>/clock fixed <capture.f32le>
 */
#define SDL_GetQueuedAudioSize w_queued_size
#define SDL_QueueAudio w_queue_audio
#ifndef Z_AUDIO_SOURCE
#define Z_AUDIO_SOURCE "libs/audio/cellAudio.c"
#endif
#include Z_AUDIO_SOURCE
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
void guest_poll_notify(uint32_t a, uint32_t size) { (void)a; (void)size; }

static pthread_mutex_t producer_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t producer_cond = PTHREAD_COND_INITIALIZER;
static unsigned pending, submitted, silent, rendered;
static int done;
static uint64_t device_start, device_period;
static unsigned queued_frames;
static unsigned injections;
static uint64_t previous_mix, shortest_gap = UINT64_MAX;
static uint64_t pause_end;
static int baseline;
static FILE* output;

static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

Uint32 w_queued_size(SDL_AudioDeviceID dev)
{
    (void)dev;
    if ((submitted >= 200 && injections == 0) ||
        (submitted >= 400 && injections == 1)) {
        const unsigned ms = injections++ ? 30 : 2000;
        fprintf(stderr, "[Z-inject] mixer stall %u ms before submit %u\n", ms, submitted);
        usleep(ms * 1000);
        pause_end = now_ns();
    }
    /* Deliberately faster than 48 kHz: exercise reverse device starvation. */
    const uint64_t period = (now_ns() - device_start) * 48240 / (512 * 1000000000ULL);
    if (period > device_period) {
        const uint64_t consumed = (period - device_period) * 512;
        queued_frames = consumed < queued_frames ? queued_frames - consumed : 0;
        device_period = period;
    }
    return queued_frames * 2 * sizeof(float);
}

int w_queue_audio(SDL_AudioDeviceID dev, const void* data, Uint32 bytes)
{
    (void)dev;
    const float* pcm = data;
    int nz = 0;
    for (unsigned i = 0; i < bytes / sizeof(float); ++i) nz |= pcm[i] != 0;
    if (bytes == 256 * 2 * sizeof(float)) {
        const uint64_t now = now_ns();
        if (previous_mix && now - previous_mix < shortest_gap) shortest_gap = now - previous_mix;
        previous_mix = now;
        if (++submitted > 16 && !nz) silent++;
        if (output) fwrite(data, 1, bytes, output);
        if (pause_end && now - pause_end > 1000000000ULL) {
            fprintf(stderr, "[Z-recovered] one second after stall at mix block %u\n", submitted);
            pause_end = 0;
        }
    }
    queued_frames += bytes / (2 * sizeof(float));
    return 0;
}

uint32_t sys_event_find_queue_by_key(uint64_t key) { (void)key; return 1; }
int sys_event_queue_push_by_id(uint32_t q, uint64_t s, uint64_t a, uint64_t b, uint64_t c)
{
    (void)q; (void)s; (void)a; (void)b; (void)c;
    pthread_mutex_lock(&producer_mutex);
    pending++;
    pthread_cond_signal(&producer_cond);
    pthread_mutex_unlock(&producer_mutex);
    return 0;
}

static void* produce(void* unused)
{
    (void)unused;
    for (;;) {
        pthread_mutex_lock(&producer_mutex);
        while (!pending && !done) pthread_cond_wait(&producer_cond, &producer_mutex);
        if (done) { pthread_mutex_unlock(&producer_mutex); break; }
        pending--;
        pthread_mutex_unlock(&producer_mutex);
        pthread_mutex_lock(&s_audio_mutex);
        const unsigned slot = s_ports[0].read_index % 8;
        pthread_mutex_unlock(&s_audio_mutex);
        /* The guest mixer cannot render between two immediate notifications. */
        usleep(2000);
        pthread_mutex_lock(&s_audio_mutex);
        const float amplitude = 0.25f + 0.125f * sinf(rendered * 0.04f);
        uint32_t bits;
        memcpy(&bits, &amplitude, 4);
        for (unsigned i = 0; i < 256 * 2; ++i)
            vm_write32(0x1000 + (slot * 256 * 2 + i) * 4, bits);
        rendered++;
        pthread_mutex_unlock(&s_audio_mutex);
    }
    return NULL;
}

int main(int argc, char** argv)
{
    baseline = argc > 1 && !strcmp(argv[1], "baseline");
    if (argc > 2) output = fopen(argv[2], "wb");
    vm_base = calloc(1, 0x10000);
    assert(vm_base);
    mutex_init(&s_audio_mutex);
    s_ports[0].in_use = s_ports[0].running = 1;
    s_ports[0].param.nChannel = 2;
    s_ports[0].param.nBlock = 8;
    s_ports[0].param.level = 1;
    s_ports[0].buffer = (float*)(vm_base + 0x1000);
    s_ports[0].read_idx_addr = 0x100;
    s_notify_queues[0].in_use = 1;
    s_notify_queues[0].key = 1;
    s_sdl_audio_dev = 1;
#ifndef Z_BASELINE
    s_sdl_prime_frames = 1024;
#endif
    device_start = now_ns();
    pthread_t producer;
    assert(!pthread_create(&producer, NULL, produce, NULL));
    assert(!audio_start_mix_thread());
    usleep(8500000);
    audio_stop_mix_thread();
    pthread_mutex_lock(&producer_mutex);
    done = 1;
    pthread_cond_signal(&producer_cond);
    pthread_mutex_unlock(&producer_mutex);
    pthread_join(producer, NULL);
    const double fraction = (double)silent / (submitted - 16);
    printf("512-frame device: blocks=%u rendered=%u silent=%.2f%% (%s)\n",
           submitted, rendered, fraction * 100, baseline ? "baseline" : "fixed");
    printf("minimum guest block gap=%.3fms injections=%u\n", shortest_gap / 1000000.0, injections);
    assert(submitted > 900 && injections == 2);
    if (!baseline) {
        assert(fraction < 0.01);
        assert(shortest_gap >= 4300000ULL);
    }
    if (output) fclose(output);
    free(vm_base);
    return 0;
}
