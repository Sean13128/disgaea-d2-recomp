/* Deterministic inputs for the four lifted synth2 kernels in the live sample.
 * AO.synth-bench.py compiles their exact generated bodies, without dispatching
 * onward into the image. Hash the entire register file, LS and exit PC. */
#include "spu_helpers.h"
#include <time.h>
#include <assert.h>

int g_spu_ls_watch_n = 0;
void spu_ls_watch_slow(uint32_t a, int w, const uint8_t* p, uint32_t pc, uint32_t lr)
{ (void)a; (void)w; (void)p; (void)pc; (void)lr; }
SPU_THREAD_LOCAL void (*g_spu_trampoline_fn)(spu_context*);
void ao_mix(spu_context*);
void ao_scale(spu_context*);
void ao_clear(spu_context*);
void ao_interp(spu_context*);

static uint64_t hash(const void* p, size_t n, uint64_t h)
{
    const uint8_t* b = p;
    while (n--) { h ^= *b++; h *= UINT64_C(1099511628211); }
    return h;
}
static double cpu_time(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}
static void init(spu_context* c, unsigned variant)
{
    memset(c, 0, sizeof *c);
    c->ls = c->ls_store;
    for (unsigned i = 0; i < SPU_LS_SIZE; i += 16) {
        u128 v;
        for (unsigned j = 0; j < 4; j++)
            v._f32[j] = (float)((int)((i + j * 71 + variant * 13) % 201) - 100) / 1024.0f;
        spu_ls_write128(c, i, v);
    }
    for (unsigned i = 0; i < 128; i++) c->gpr[i] = spu_splat_u32(i * 37);
    c->gpr[1] = spu_splat_u32(0x3f000);
    c->gpr[80] = spu_splat_u32(0x8000);
    c->gpr[81] = spu_splat_u32(0xa000);
    c->gpr[90] = spu_splat_u32(0xb000);
    c->gpr[82] = c->gpr[83] = c->gpr[86] = c->gpr[87] = spu_zero();
    for (unsigned i = 0; i < 4; i++) {
        c->gpr[82]._f32[i] = 0.125f; c->gpr[83]._f32[i] = -0.25f;
        c->gpr[86]._f32[i] = 0.5f; c->gpr[87]._f32[i] = 0.25f;
        c->gpr[89]._f32[i] = 0.25f; c->gpr[93]._f32[i] = 0.015625f;
        c->gpr[9]._f32[i] = 0.25f; c->gpr[10]._f32[i] = -0.5f;
    }
    /* Broadcast preferred input sample in SPU byte order. */
    c->gpr[11] = spu_ila(0x00010203);
}
static void prepare(spu_context* c, unsigned k, unsigned variant)
{
    unsigned offset = (variant & 3) * 4;
    if (k == 0) {
        c->gpr[6] = spu_splat_u32(0x10000);
        c->gpr[7] = spu_splat_u32(0x14000 + offset);
        c->gpr[8] = spu_zero(); c->gpr[82] = spu_splat_u32(64);
    } else if (k == 1) {
        c->gpr[5] = spu_splat_u32(256);
        c->gpr[8] = spu_splat_u32(0x18000 + offset);
        c->gpr[6] = spu_zero();
        for (unsigned j = 0; j < 4; j++) c->gpr[6]._f32[j] = -1.0f;
    } else if (k == 2) {
        c->gpr[5] = spu_splat_u32(0x1c000 + offset);
        c->gpr[6] = spu_zero(); c->gpr[7] = spu_zero();
        c->gpr[85] = spu_splat_u32(256);
    } else {
        c->gpr[88] = spu_splat_u32(variant & 255);
        c->gpr[92] = spu_zero(); c->gpr[85] = spu_splat_u32(1);
    }
}
int main(int argc, char** argv)
{
    unsigned rounds = argc > 1 ? (unsigned)strtoul(argv[1], 0, 0) : 20000;
    const char* names[] = {"6280-mix", "24E0-scale", "0D88-clear", "1010-interp"};
    void (*funcs[])(spu_context*) = {ao_mix, ao_scale, ao_clear, ao_interp};
    spu_context* c = calloc(1, sizeof *c);
    assert(c);
    g_spu_ls_probe = g_spu_smc_watch = 0;
    for (unsigned k = 0; k < 4; k++) {
        uint64_t h = UINT64_C(1469598103934665603);
        uint64_t pcm = h;
        for (unsigned variant = 0; variant < 16; variant++) {
            init(c, variant); prepare(c, k, variant); funcs[k](c);
            h = hash(c->gpr, sizeof c->gpr, h);
            h = hash(c->ls, SPU_LS_SIZE, h); h = hash(&c->pc, sizeof c->pc, h);
            if (k == 0) for (unsigned sample = 0; sample < 256; sample++) {
                u128 left = spu_ls_read128(c, 0x10c00 + sample * 4);
                u128 right = spu_ls_read128(c, 0x11000 + sample * 4);
                float stereo[2] = {left._f32[sample & 3], right._f32[sample & 3]};
                pcm = hash(stereo, sizeof stereo, pcm);
            }
        }
        init(c, 0);
        double start = cpu_time();
        for (unsigned i = 0; i < rounds; i++) { prepare(c, k, i); funcs[k](c); }
        double elapsed = cpu_time() - start;
        printf("%s rounds=%u cpu_ms=%.3f ns/call=%.1f state_fnv64=%016llx\n",
               names[k], rounds, elapsed * 1e3, elapsed * 1e9 / rounds, (unsigned long long)h);
        if (k == 0) printf("stereo PCM: 16 variants x 256 frames pcm_fnv64=%016llx\n", (unsigned long long)pcm);
    }
    free(c);
}
