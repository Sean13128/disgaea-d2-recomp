/* Native vertex-program upload (src/d2_shader.cpp) against the lifted body it
 * replaces: identical guest memory, end-state ppu_context, and the same calls
 * (flush callback, func_002FF1A0) in the same order with the same context and
 * stack argument. Covers FIFO-full flush (wrap to begin, failing flush),
 * packets running off the VM, ucode aliasing the FIFO, the cursor word inside
 * the copy, and an armed store watch (all-scalar path). */
#include "ppu_recomp.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <string>
extern "C" {
uint8_t* vm_base;
extern uint32_t ppu_vm_size;
extern uint32_t g_barrier_sync_watch;
void ppu_register_function(uint64_t addr, void (*fn)(ppu_context*));
const func_entry function_table[] = {{0, nullptr, nullptr}};
const uint64_t function_table_count = 0;
uint32_t ps3_hle_count(void) { return 0; }   /* no HLE imports here (ppu_hle.cpp) */
}
void d2_original_002FE4AC(ppu_context*);   /* the lift, from shader_lift.cpp */
enum : uint32_t { VM = 0x400000, CTX = 0x10000, OPD = 0x10100, CB = 0x12000,
                  PROG = 0x20000, UCODE = 0x40000, FIFO = 0x100000, SP = 0x3F0000 };

static void w32(uint32_t a, uint32_t v) { v = __builtin_bswap32(v); memcpy(vm_base + a, &v, 4); }
static uint32_t r32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return __builtin_bswap32(v); }

static std::string calls;     /* every call the body makes, with its context */
static unsigned flush_mode;   /* 0 wrap to begin, 1 fail, 2 wrap + nonzero high r3 bits */
static uint32_t rng;
static uint32_t next() { rng = rng * 1664525u + 1013904223u; return rng; }

static void note(const char* who, ppu_context* c)
{
    char b[96];
    snprintf(b, sizeof b, "%s lr=%llx cr=%x ctr=%llx|", who, (unsigned long long)c->lr, c->cr,
             (unsigned long long)c->ctr);
    calls += b;
    for (int i = 0; i < 32; i++) { snprintf(b, sizeof b, "%llx,", (unsigned long long)c->gpr[i]); calls += b; }
    for (uint32_t i = 0; i < 16; i++) { snprintf(b, sizeof b, "%02x", vm_base[(uint32_t)c->gpr[1] + 0x70 + i]); calls += b; }
    calls += '\n';
}

/* Volatile registers come back changed, as a real callee leaves them. */
static void clobber(ppu_context* c)
{
    for (int i : {0, 4, 5, 6, 7, 8, 9, 10, 11, 12}) c->gpr[i] ^= (uint64_t)next() << 7;
    c->ctr = next();
    c->cr = (c->cr & 0x00FFF000u) | (next() & 0xFF000FFFu);
}

static void flush(ppu_context* c)
{
    note("flush", c);
    const uint32_t ctx = (uint32_t)c->gpr[3];
    clobber(c);
    if (flush_mode == 1) { c->gpr[3] = 0x80010000; return; }
    w32(ctx + 8, r32(ctx));                   /* wrap: jump back to begin */
    c->gpr[3] = flush_mode == 2 ? 0x1234500000000ull : 0;
}

void func_002FF1A0(ppu_context* c)
{
    note("ff1a0", c);
    const uint32_t ctx = (uint32_t)c->gpr[3], cur = r32(ctx + 8);
    if (cur >= 0x10000 && cur + 8 <= VM) {                  /* emits a method, moves on */
        w32(cur, 0x00041A00 | (uint32_t)c->gpr[4] >> 4);
        w32(cur + 4, r32((uint32_t)c->gpr[5]));
        w32(ctx + 8, cur + 8);
    }
    clobber(c);
}

struct Case {
    uint32_t instr, slot, attr, mask, params, begin, end, cur, ucode, ctxw_in_fifo;
};

static void setup(const Case& k, unsigned salt)
{
    rng = salt * 2654435761u;
    for (uint32_t i = 0; i < VM; i += 4) w32(i, next());
    w32(CTX, k.begin); w32(CTX + 4, k.end); w32(CTX + 8, k.cur); w32(CTX + 0xC, OPD);
    w32(OPD, CB); w32(OPD + 4, 0x0047DF98);
    const uint32_t info = 0x400;
    w32(PROG + 0x14, info);
    w32(PROG + info, k.instr); w32(PROG + info + 4, k.slot);
    w32(PROG + info + 8, k.attr); w32(PROG + info + 0xC, k.mask);
    w32(PROG + 0xC, k.params); w32(PROG + 0x10, 0x800);
    for (uint32_t p = 0; p < k.params; p++) {
        const uint32_t e = PROG + 0x800 + p * 0x30, t = next() % 4;
        w32(e + 8, t == 0 ? 0x1006 : t == 1 ? 0x1007 : 0x1005 + 3 * t);
        w32(e + 0x14, next() % 3 ? 0x1000 + p * 0x10 : 0);
    }
}

static unsigned ncases;
static void same(const Case& k, unsigned salt)
{
    static uint8_t want[VM];
    std::string lift_calls;
    ppu_context ref;
    memset(&ref, 0, sizeof ref);
    rng = salt;
    for (auto& r : ref.gpr) r = (uint64_t)next() << 32 ^ next();
    ref.cr = next(); ref.ctr = next(); ref.lr = 0x002D12EC;
    ref.gpr[1] = SP; ref.gpr[2] = 0x0047DF98;
    ref.gpr[3] = k.ctxw_in_fifo ? k.ctxw_in_fifo : CTX;
    ref.gpr[4] = PROG; ref.gpr[5] = k.ucode;
    if (salt & 1) ref.gpr[5] |= 0xABCD00000000ull;   /* callers pass 32-bit pointers */
    ppu_context got = ref;

    for (int pass = 0; pass < 2; pass++) {
        setup(k, salt);
        if (k.ctxw_in_fifo) {   /* context struct placed inside the FIFO it fills */
            const uint32_t c = k.ctxw_in_fifo;
            w32(c, k.begin); w32(c + 4, k.end); w32(c + 8, k.cur); w32(c + 0xC, OPD);
        }
        calls.clear();
        rng = salt ^ 0x5A5A;
        if (pass == 0) { d2_original_002FE4AC(&ref); memcpy(want, vm_base, VM); lift_calls = calls; }
        else func_002FE4AC(&got);
    }
    ncases++;
    if (!memcmp(want, vm_base, VM) && !memcmp(&ref, &got, sizeof ref) && lift_calls == calls) return;
    fprintf(stderr, "FAIL salt=%u instr=%u params=%u cur=0x%x end=0x%x ucode=0x%x\n", salt,
            k.instr, k.params, k.cur, k.end, k.ucode);
    for (uint32_t i = 0; i < VM; i++)
        if (want[i] != vm_base[i]) { fprintf(stderr, "  first byte diff at 0x%x\n", i); break; }
    for (int i = 0; i < 32; i++)
        if (ref.gpr[i] != got.gpr[i])
            fprintf(stderr, "  r%d lift=0x%llx native=0x%llx\n", i,
                    (unsigned long long)ref.gpr[i], (unsigned long long)got.gpr[i]);
    fprintf(stderr, "  cr 0x%x/0x%x ctr 0x%llx/0x%llx lr 0x%llx/0x%llx calls %s\n", ref.cr, got.cr,
            (unsigned long long)ref.ctr, (unsigned long long)got.ctr,
            (unsigned long long)ref.lr, (unsigned long long)got.lr,
            lift_calls == calls ? "same" : "DIFFER");
    if (lift_calls != calls) fprintf(stderr, "--lift\n%s--native\n%s", lift_calls.c_str(), calls.c_str());
    exit(1);
}

static double cpu_us()
{
    timespec t; clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &t);
    return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}

int main()
{
    vm_base = (uint8_t*)calloc(1, VM); assert(vm_base);
    ppu_vm_size = VM;
    ppu_register_function(CB, flush);
    unsigned salt = 1;
    const uint32_t instrs[] = {0, 1, 2, 7, 8, 9, 15, 16, 17, 31, 32, 63, 64, 100, 255, 512};
    for (uint32_t instr : instrs)
        for (uint32_t attr : {0x1Fu, 0x20u, 0x21u})
            for (uint32_t params : {0u, 1u, 5u}) {
                const uint32_t need = ((instr >> 3) * 33 + (instr & 7 ? (instr & 7) * 4 + 1 : 0)) * 4 + 0x1C;
                Case k = {instr, next() % 468, attr, next(), params, FIFO, FIFO + 0x40000, FIFO + 0x100, UCODE, 0};
                same(k, salt++);
                for (flush_mode = 0; flush_mode < 3; flush_mode++) {      /* FIFO near its end */
                    k.cur = k.end - need - 8 + 4 * (next() % 5); same(k, salt++);
                    k.cur = k.end - 4; same(k, salt++);
                }
                flush_mode = 0;
                k.cur = FIFO + 0x100;
                k.end = VM + 0x1000; k.cur = VM - need / 2 - 0x40; same(k, salt++);   /* runs off the VM */
                k.end = FIFO + 0x40000; k.cur = FIFO + 0x100;
                k.ucode = FIFO + 0x180; same(k, salt++);                            /* ucode aliases FIFO */
                k.ucode = FIFO + 0x100 - need / 2; same(k, salt++);
                k.ucode = UCODE;
                k.ctxw_in_fifo = FIFO + 0x100 + need / 3 & ~3u; k.cur = FIFO + 0x100; same(k, salt++);
                k.ctxw_in_fifo = 0;
                k.ucode = VM - 0x200; same(k, salt++);                              /* ucode off the VM */
                k.ucode = UCODE;
                g_barrier_sync_watch = 0x300000; same(k, salt++);                   /* store watch armed */
                g_barrier_sync_watch = 0;
            }
    /* Last: a null-page cursor leaves the runtime's null-sweep state behind. */
    same({64, 3, 0x20, 0xFFFF, 2, 0x800, 0x40000, 0x800, UCODE, 0}, salt++);
    printf("PASS: %u uploads match the lift (memory, GPR/CR/CTR/LR, call order and context)\n", ncases);

    /* Microbench: steady-state upload with no flush, no uniforms. */
    for (uint32_t instr : {16u, 64u, 256u}) {
        Case k = {instr, 0, 0x20, 0xFFFF, 0, FIFO, FIFO + 0x200000, FIFO, UCODE, 0};
        setup(k, 7);
        const unsigned reps = 20000;
        double t[2];
        for (int pass = 0; pass < 2; pass++) {
            const double t0 = cpu_us();
            for (unsigned i = 0; i < reps; i++) {
                w32(CTX + 8, FIFO);
                ppu_context c; memset(&c, 0, sizeof c);
                c.gpr[1] = SP; c.gpr[3] = CTX; c.gpr[4] = PROG; c.gpr[5] = UCODE;
                if (pass == 0) d2_original_002FE4AC(&c); else func_002FE4AC(&c);
            }
            t[pass] = (cpu_us() - t0) / reps;
        }
        printf("INFO: %u-instruction upload lift %.3f us, native %.3f us (%.1fx)\n", instr, t[0], t[1], t[0] / t[1]);
    }
    free(vm_base);
}
