/* Raw consumed-ring replay: retain packet bytes/order, replay referenced guest
 * memory mutations and run the live GCM walker/register-file draw engine.
 * Scheduler waits and vblank are excluded; jump/call control flow is flattened
 * into consumed packets. --metal-null uses offscreen Metal, without a drawable. */
#if defined(AA_WITH_METAL) || defined(AA_LIVE_DRAIN)
#define cellGcmResolveLocated aa_test_resolve_located
#define cellGcmResolveIO aa_test_resolve_io
#endif
#define main aa_existing_draw_tests
#include "../ps3recomp/libs/video/tests/test_rsx_draw_engine.c"
#undef main
#if defined(AA_WITH_METAL) || defined(AA_LIVE_DRAIN)
#undef cellGcmResolveLocated
#undef cellGcmResolveIO
#endif
#ifndef AA_ENGINE_SOURCE
#define AA_ENGINE_SOURCE "../ps3recomp/libs/video/rsx_draw_engine.c"
#endif
#include AA_ENGINE_SOURCE
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#ifdef __APPLE__
#include <pthread/qos.h>
#endif
#include <time.h>
#ifdef AA_WITH_METAL
#include "../ps3recomp/libs/video/rsx_metal_backend.h"
#endif
static u8* s_memory;
static u8 s_valid[2][1u << 20];
static u64 s_missing, s_draws, s_checksum;
static int s_verify;
static u64 s_vertex_counts[5];
#include "../ps3recomp/libs/video/rsx_commands.h"
static rsx_state s_legacy;
void ps3_ms(const char* key) { (void)key; }
#if !defined(AA_WITH_METAL) && !defined(AA_LIVE_DRAIN)
uint32_t ppu_hle_inject_base = 0x03000000u;
#endif
void vm_write32(uint32_t ea, uint32_t v) { v = __builtin_bswap32(v); memcpy(vm_base + ea, &v, 4); }
static double clock_ms(void)
{
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}
static const u8* replay_read(void* u, u32 loc, u32 off, u32 n)
{
    (void)u;
    if (loc > 1 || !n || (u64)off + n > 0x100000000ull) return NULL;
    for (u32 page = off >> 12; page <= ((u64)off + n - 1) >> 12; page++)
        if (!s_valid[loc][page]) { s_missing++; return NULL; }
    return s_memory + (u64)loc * 0x100000000ull + off;
}
static void checked_draw(void* u, rsx_topology t, const void* data,
                         u32 count, u32 stride, const u32* idx, u32 ni)
{
    (void)u; s_draws++;
    if (s_verify) s_vertex_counts[count < 16 ? 0 : count < 64 ? 1 : count < 256 ? 2 : count < 1024 ? 3 : 4]++;
    if (s_verify) {
        s_checksum = eng_fnv1a(data, count * stride, s_checksum);
        if (ni) s_checksum = eng_fnv1a(idx, ni * 4, s_checksum);
        s_checksum ^= (u64)t << 32 | count;
    }
}
static void raw_packet(const u8* bytes, u32 n, int* sub1_2d)
{
    if (n < 4) return;
    u32 raw; memcpy(&raw, bytes, 4); const u32 w = __builtin_bswap32(raw);
    const u32 type = w >> 29, count = (w >> 18) & 0x7ffu;
    if ((type != 0 && type != 2) || n != 4 + count * 4) {
        fprintf(stderr, "invalid raw packet\n"); exit(1);
    }
    const u32 sub = (w >> 13) & 7u, method = w & 0x1ffcu;
    for (u32 i = 0; i < count; i++) {
        const u32 m = method + (type == 0 ? i * 4 : 0);
        memcpy(&raw, bytes + 4 + i * 4, 4); const u32 v = __builtin_bswap32(raw);
        if (sub == 1) {
            if (m == 0 && v == 0x31337303u) *sub1_2d = 1;
            else if ((m == 0 && v == 0x31337000u) || m >= 0x800u) *sub1_2d = 0;
        }
        if (sub != 0 && !(sub == 1 && !*sub1_2d)) continue;
        const u32 full = sub << 13 | m;
        if (full == 0xe920 || full == 0xe924 || full == 0xe944) continue;
        rsx_draw_engine_method(full, v);
#ifdef AA_BASELINE_DRAIN
        rsx_process_method(&s_legacy, m, v);
#else
        if (m == 0x50 || m == 0x1d6c || m == 0x1d70 || m == 0x1d74)
            rsx_process_method(&s_legacy, m, v);
#endif
    }
}
#ifdef AA_LIVE_DRAIN
void aa_live_drain(const u8* bytes, u32 n);
static u8 s_pending_fifo[1u << 20];
static u32 s_pending_bytes;
static void flush_pending(double* drain)
{
    if (!s_pending_bytes) return;
    double t = clock_ms(); aa_live_drain(s_pending_fifo, s_pending_bytes);
    *drain += clock_ms() - t;
    s_pending_bytes = 0;
}
#endif
static void series(const u8* bytes, size_t length, int seed,
                   double* drain, double* present, u32* frames, u64* packets)
{
    size_t pos = 0;
    int sub1_2d = 0;
    while (pos + 16 <= length) {
        u32 h[4]; memcpy(h, bytes + pos, 16); pos += 16;
        if (pos + h[3] > length) { fprintf(stderr, "truncated capture\n"); exit(1); }
        const u8* p = bytes + pos;
        switch (h[0]) {
        case 0x41414631u:
            if (h[3] != sizeof(g.rsx)) { fprintf(stderr, "dispatch ABI mismatch\n"); exit(1); }
            if (seed) {
                rsx_dispatch_sink sink = g.rsx.sink;
                memcpy(&g.rsx, p, sizeof(g.rsx)); g.rsx.sink = sink;
            }
            break;
        case 'B':
            if (h[3] != sizeof(g.display_buffers)) exit(1);
            if (seed) memcpy(g.display_buffers, p, sizeof(g.display_buffers));
            break;
        case 'M':
#ifdef AA_LIVE_DRAIN
            flush_pending(drain);
#endif
            if (h[1] > 1 || (u64)h[2] + h[3] > 0x100000000ull) exit(1);
            memcpy(s_memory + (u64)h[1] * 0x100000000ull + h[2], p, h[3]);
            if (h[3]) memset(s_valid[h[1]] + (h[2] >> 12), 1,
                              (((u64)h[2] + h[3] - 1) >> 12) - (h[2] >> 12) + 1);
            break;
        case 'F': {
#ifdef AA_LIVE_DRAIN
            if (s_pending_bytes + h[3] > sizeof s_pending_fifo) flush_pending(drain);
            memcpy(s_pending_fifo + s_pending_bytes, p, h[3]); s_pending_bytes += h[3];
#else
            double t = clock_ms(); raw_packet(p, h[3], &sub1_2d); *drain += clock_ms() - t;
#endif
            (*packets)++; break;
        }
        case 'P': {
#ifdef AA_LIVE_DRAIN
            flush_pending(drain);
#endif
            double t = clock_ms(); rsx_draw_engine_present_buffer(h[1]); *present += clock_ms() - t;
            (*frames)++; break;
        }
        default: fprintf(stderr, "unknown record %x\n", h[0]); exit(1);
        }
        pos += h[3];
    }
#ifdef AA_LIVE_DRAIN
    flush_pending(drain);
#endif
    if (pos != length) exit(1);
}
int main(int argc, char** argv)
{
#ifdef __APPLE__
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
#endif
    if (argc < 2) { fprintf(stderr, "usage: AA-replay capture.fifo [--metal-null] [repeats]\n"); return 1; }
    int metal = argc > 2 && !strcmp(argv[2], "--metal-null");
    u32 repeats = argc > 3 ? (u32)atoi(argv[3]) : 100;
    int fd = open(argv[1], O_RDONLY); struct stat st;
    if (fd < 0 || fstat(fd, &st) || st.st_size < 16) return 1;
    const u8* file = mmap(NULL, st.st_size, PROT_READ, MAP_PRIVATE, fd, 0); close(fd);
    if (file == MAP_FAILED) return 1;
    u32 header[4]; memcpy(header, file, 16);
    s_memory = mmap(NULL, 0x200000000ull, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (s_memory == MAP_FAILED) return 1;
    vm_base = s_memory; rsx_state_init(&s_legacy);
    rsx_draw_engine_set_default(1);
    rsx_draw_backend backend = g_stub_backend;
    backend.draw = checked_draw;
    if (metal) {
#ifdef AA_WITH_METAL
        setenv("PS3RECOMP_METAL_HEADLESS", "1", 1);
        setenv("PS3RECOMP_RSX_ENGINE", "dispatch", 1);
        if (rsx_metal_backend_init(header[1], header[2], "AA FIFO replay")) {
            fprintf(stderr, "Metal unavailable; no GPU measurement\n"); return 2;
        }
#else
        fprintf(stderr, "build replay with AA_WITH_METAL for --metal-null\n"); return 2;
#endif
    } else {
        rsx_draw_engine_set_backend(&backend);
        if (rsx_draw_engine_init(header[1], header[2])) return 1;
    }
    rsx_draw_engine_set_guest_memory(replay_read, NULL);
    double drain = 0, present = 0; u32 frames = 0; u64 packets = 0;
    s_verify = !metal; s_checksum = 14695981039346656037ull;
    series(file, st.st_size, 1, &drain, &present, &frames, &packets);
    printf("Warmup: frames=%u draws=%llu packets=%llu missing_reads=%llu checksum=%016llx\n",
           frames, (unsigned long long)s_draws, (unsigned long long)packets,
           (unsigned long long)s_missing, (unsigned long long)s_checksum);
    printf("Vertex count buckets <16/<64/<256/<1024/larger: %llu/%llu/%llu/%llu/%llu\n",
           (unsigned long long)s_vertex_counts[0], (unsigned long long)s_vertex_counts[1],
           (unsigned long long)s_vertex_counts[2], (unsigned long long)s_vertex_counts[3], (unsigned long long)s_vertex_counts[4]);
    s_verify = 0; s_draws = 0; drain = present = 0; frames = 0; packets = 0; s_missing = 0;
    for (u32 run = 0; run < repeats; run++) series(file, st.st_size, 0, &drain, &present, &frames, &packets);
    printf("%s: %u frames, %llu draws, %llu raw packets; drain %.3f ms/frame, present %.3f ms/frame; missing_reads=%llu\n",
           metal ? "Metal-null (offscreen GPU)" : "No Metal (mock backend)", frames,
           (unsigned long long)s_draws, (unsigned long long)packets,
           drain / frames, present / frames, (unsigned long long)s_missing);
#ifndef AA_BASELINE_DRAIN
    printf("Converted vertex cache: hits=%llu misses=%llu bytes=%u\n",
           (unsigned long long)s_vertex_cache_hits, (unsigned long long)s_vertex_cache_misses, s_vertex_cache_bytes);
#endif
    rsx_draw_engine_shutdown();
    munmap(s_memory, 0x200000000ull); munmap((void*)file, st.st_size);
    return !frames || s_missing ? 1 : 0;
}
