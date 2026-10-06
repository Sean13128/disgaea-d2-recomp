/* BLUS31313 1.40 vertex-program upload (func_002FE4AC: r3 gcm context, r4 Cg
 * program, r5 ucode). It reserves FIFO space (flush callback when short),
 * emits TRANSFORM_PROGRAM_LOAD, the ucode as 0x0B80 packets of 32 words plus a
 * remainder, the output mask and timeout, then calls func_002FF1A0 per
 * uniform. That is ~10% of active menu PPU time, nearly all of it the scalar
 * word copies. Here the copies go through one vm_copy per packet; every other
 * access, call and register keeps the lift's order, and registers end exactly
 * as the lift leaves them (tests/AR.shader-test.cpp compares the whole
 * context). Copies vm_copy declines, or with aliasing or 32-bit wrap, run the
 * scalar accesses in the lift's order. The FIFO put pointer is only written by
 * the flush callback, which still runs before any command word. The 1.00 lift
 * stays lifted. */
#include "ppu_recomp.h"
#include <string.h>

extern "C" {
extern uint8_t* vm_base;
extern uint32_t ppu_vm_size;
extern uint32_t ppu_hle_inject_base;
extern PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*);
void ps3_indirect_call(ppu_context*);
int vm_copy(uint32_t dst, uint32_t src, uint32_t n);
}

static inline void drain(ppu_context* ctx)
{
    while (g_trampoline_fn) {
        void (*f)(void*) = g_trampoline_fn;
        g_trampoline_fn = 0;
        f(ctx);
    }
}
static inline uint32_t cmps(int32_t a, int32_t b) { return a < b ? 8u : a > b ? 4u : 2u; }
static inline uint32_t cmpu(uint32_t a, uint32_t b) { return a < b ? 8u : a > b ? 4u : 2u; }
static inline void setcr(ppu_context* c, int sh, uint32_t v) { c->cr = (c->cr & ~(0xFu << sh)) | v << sh; }
static inline uint64_t be32(uint32_t a)
{
    uint32_t v;
    memcpy(&v, vm_base + a, 4);
    return __builtin_bswap32(v);
}
static inline uint64_t u32(uint64_t x) { return (uint32_t)x; }

/* [a, a+n) lies in 32-bit space and misses the context's current word. */
static bool clear_of(uint64_t a, uint64_t n, uint32_t w)
{
    return a + n <= 0x100000000ull && (w + 4ull <= a || w >= a + n);
}

/* The context's current word reads back what was just stored there, so the
 * lift's per-packet reload of it is the running cursor. */
static bool cursor_ok(uint32_t w, uint64_t cur)
{
    const uint32_t gcm = ppu_hle_inject_base;
    return cur >> 32 == 0 && w >= 0x10000u && (!ppu_vm_size || w + 4ull <= ppu_vm_size) &&
           !(w < gcm + 0x8000u && w + 4ull > gcm) && w + 4ull <= 0xE0000000u && be32(w) == cur;
}

/* loc_002FE5C4: ctr packets of header + 32 words, cursor word at r31+8. */
static void packets(ppu_context* ctx)
{
    uint64_t* r = ctx->gpr;
    const uint64_t n = (uint32_t)ctx->ctr, src = (uint32_t)r[5], cur = r[7];
    const uint32_t w = (uint32_t)(r[31] + 8);
    if (cursor_ok(w, cur) && clear_of(cur, n * 0x84, w) && clear_of(src, n * 0x80, w) &&
        (cur + n * 0x84 <= src || src + n * 0x80 <= cur)) {
        uint64_t i = 0;
        /* Body before header: both lie past the put pointer, unseen by RSX. */
        while (i < n && vm_copy((uint32_t)(cur + i * 0x84 + 4), (uint32_t)(src + i * 0x80), 0x80)) {
            vm_write32(cur + i * 0x84, (uint32_t)r[4]);
            i++;
        }
        if (i == n) {
            const uint64_t last = cur + (n - 1) * 0x84, s = src + (n - 1) * 0x80;
            r[0] = be32((uint32_t)(s + 0x7C));
            r[6] = be32((uint32_t)(s + 0x38));
            r[8] = be32((uint32_t)(s + 0x74));
            r[11] = be32((uint32_t)(s + 0x70));
            r[9] = u32(last + 0x44);
            /* r10 is recomputed by the caller right after. */
            r[5] += n * 0x80;
            r[7] = last + 0x84;
            vm_write32(w, (uint32_t)r[7]);
            ctx->ctr = 0;
            return;
        }
        /* vm_copy declined packet i (a range it leaves to the accessors):
         * the lift's cursor after packet i-1, then the rest word by word. */
        if (i) vm_write32(w, (uint32_t)(cur + i * 0x84));
        r[5] += i * 0x80;
        r[7] = cur + i * 0x84;
        ctx->ctr = (uint32_t)(n - i);
    }
    do {    /* the lift's accesses, in its order */
        r[8] = u32(r[7]);
        r[9] = u32(r[5]);
        r[11] = u32(r[7] + 4);
        r[10] = u32(r[5] + 0x40);
        vm_write32(r[8], (uint32_t)r[4]);
        r[5] += 0x80;
        for (int o = 0; o < 0x30; o += 0x10) {
            r[0] = vm_read32(r[9] + o); r[8] = vm_read32(r[9] + o + 4);
            r[7] = vm_read32(r[9] + o + 8); r[6] = vm_read32(r[9] + o + 0xC);
            vm_write32(r[11] + o, (uint32_t)r[0]); vm_write32(r[11] + o + 4, (uint32_t)r[8]);
            vm_write32(r[11] + o + 8, (uint32_t)r[7]); vm_write32(r[11] + o + 0xC, (uint32_t)r[6]);
        }
        r[0] = vm_read32(r[9] + 0x3C); r[8] = vm_read32(r[9] + 0x30);
        r[7] = vm_read32(r[9] + 0x34); r[6] = vm_read32(r[9] + 0x38);
        vm_write32(r[11] + 0x3C, (uint32_t)r[0]); vm_write32(r[11] + 0x30, (uint32_t)r[8]);
        vm_write32(r[11] + 0x34, (uint32_t)r[7]); vm_write32(r[11] + 0x38, (uint32_t)r[6]);
        r[9] = vm_read32(r[31] + 8);
        r[7] = vm_read32(r[10] + 4);
        r[9] = r[9] + 0x44;
        r[8] = vm_read32(r[10] + 8);
        r[11] = vm_read32(r[10] + 0xC);
        r[9] = u32(r[9]);
        r[0] = vm_read32(r[10]);
        vm_write32(r[9], (uint32_t)r[0]); vm_write32(r[9] + 4, (uint32_t)r[7]);
        vm_write32(r[9] + 8, (uint32_t)r[8]); vm_write32(r[9] + 0xC, (uint32_t)r[11]);
        for (int o = 0x10; o < 0x30; o += 0x10) {
            r[0] = vm_read32(r[10] + o); r[11] = vm_read32(r[10] + o + 4);
            r[8] = vm_read32(r[10] + o + 8); r[7] = vm_read32(r[10] + o + 0xC);
            vm_write32(r[9] + o, (uint32_t)r[0]); vm_write32(r[9] + o + 4, (uint32_t)r[11]);
            vm_write32(r[9] + o + 8, (uint32_t)r[8]); vm_write32(r[9] + o + 0xC, (uint32_t)r[7]);
        }
        r[7] = vm_read32(r[10] + 0x38); r[0] = vm_read32(r[10] + 0x3C);
        r[11] = vm_read32(r[10] + 0x30); r[8] = vm_read32(r[10] + 0x34);
        vm_write32(r[9] + 0x3C, (uint32_t)r[0]); vm_write32(r[9] + 0x30, (uint32_t)r[11]);
        vm_write32(r[9] + 0x34, (uint32_t)r[8]); vm_write32(r[9] + 0x38, (uint32_t)r[7]);
        r[7] = vm_read32(r[31] + 8);
        r[7] = r[7] + 0x84;
        vm_write32(r[31] + 8, (uint32_t)r[7]);
    } while ((ctx->ctr = (uint32_t)(ctx->ctr - 1)) != 0);
}

void func_002FE4AC(ppu_context* ctx)
{
    uint64_t* r = ctx->gpr;
    uint64_t cs[8];
    memcpy(cs, r + 24, sizeof cs);
    r[12] = ctx->cr;
    vm_write64(r[1] - 0xC0, r[1]);
    r[1] -= 0xC0;
    vm_write64(r[1] + 0x98, r[27]);
    vm_write64(r[1] + 0x90, r[26]);
    vm_write64(r[1] + 0xB0, r[30]);
    vm_write64(r[1] + 0x80, r[24]);
    vm_write64(r[1] + 0x88, r[25]);
    vm_write64(r[1] + 0xA0, r[28]);
    vm_write64(r[1] + 0xA8, r[29]);
    vm_write64(r[1] + 0xB8, r[31]);
    r[28] = r[4]; r[31] = r[3]; r[24] = r[5]; r[25] = r[3];
    vm_write32(r[1] + 0xC8, (uint32_t)r[12]);
    r[0] = ctx->lr;
    vm_write64(r[1] + 0xD0, r[0]);
    r[0] = vm_read32(r[4] + 0x14);
    r[7] = vm_read32(r[3] + 0x8);
    r[0] = r[4] + r[0];
    r[27] = u32(r[0]);
    r[9] = vm_read32(r[27]);
    r[29] = vm_read32(r[27] + 4);
    r[26] = ((uint32_t)r[9] << 2) & 0x1C;     /* remainder words */
    r[30] = (uint32_t)r[9] >> 3;              /* full 32-word packets */
    setcr(ctx, 12, cmps((int32_t)r[26], 0));
    const bool no_rem = r[26] == 0;
    r[0] = (uint32_t)r[30] << 5;
    r[4] = r[0] + r[30];
    r[9] = no_rem ? 0 : r[26] + 1;
    /* loc_002FE524: reserve space */
    r[9] = r[9] + r[4];
    r[0] = vm_read32(r[31] + 4);
    r[9] = (uint32_t)r[9] << 2;
    r[9] = r[7] + r[9] + 0x1C;
    setcr(ctx, 0, cmpu((uint32_t)r[9], (uint32_t)r[0]));
    if ((uint32_t)r[9] > (uint32_t)r[0]) {
        r[9] = vm_read32(r[31] + 0xC);
        r[0] = no_rem ? 0 : r[26] + 1;
        r[9] = u32(r[9]);
        r[4] += 7;
        r[3] = u32(r[25]);
        r[4] = u32(r[0] + r[4]);
        r[0] = vm_read32(r[9]);
        vm_write64(r[1] + 0x28, r[2]);
        ctx->ctr = (uint32_t)r[0];
        r[2] = vm_read32(r[9] + 4);
        ps3_indirect_call(ctx);
        drain(ctx);
        r[2] = 0x0047DF98ULL;
        setcr(ctx, 0, cmps((int32_t)r[3], 0));
        if ((int32_t)r[3] != 0) goto out;
        r[7] = vm_read32(r[31] + 8);
    }
    /* loc_002FE584: TRANSFORM_PROGRAM_LOAD */
    r[9] = u32(r[7]);
    r[0] = 0x00081E9C;
    setcr(ctx, 0, cmps((int32_t)r[30], 0));
    r[7] += 0xC;
    vm_write32(r[9] + 8, (uint32_t)r[29]);
    vm_write32(r[9], (uint32_t)r[0]);
    vm_write32(r[9] + 4, (uint32_t)r[29]);
    vm_write32(r[31] + 8, (uint32_t)r[7]);
    r[10] = r[24];
    if ((int32_t)r[30] != 0) {
        r[4] = 0x00800B80;
        r[0] = u32(r[30]);
        r[5] = r[24];
        ctx->ctr = (uint32_t)r[0];
        packets(ctx);
        r[0] = (uint32_t)r[30] << 7;
        r[10] = r[24] + r[0];
    }
    /* loc_002FE708: remainder packet (cr4 may come back from the callback) */
    if (!((ctx->cr >> 12) & 2)) {
        r[9] = u32(r[7]);
        r[0] = ((uint32_t)r[26] << 18) | 0xB80;
        r[11] = u32(r[26]);
        r[8] = r[7] + 4;
        ctx->ctr = (uint32_t)r[11];
        vm_write32(r[9], (uint32_t)r[0]);
        const uint64_t n = (uint32_t)r[26] * 4ull;   /* the loop touches no cursor */
        if (u32(r[8]) + n <= 0x100000000ull && u32(r[10]) + n <= 0x100000000ull &&
            vm_copy((uint32_t)r[8], (uint32_t)r[10], (uint32_t)n)) {
            r[11] = u32(r[8] + n - 4);         /* r9 is recomputed below */
            r[0] = be32((uint32_t)(r[10] + n - 4));
            r[10] += n;
            r[8] += n;
            ctx->ctr = 0;
        } else {
            do {
                r[9] = u32(r[10]);
                r[11] = u32(r[8]);
                r[10] += 4;
                r[8] += 4;
                r[0] = vm_read32(r[9]);
                vm_write32(r[11], (uint32_t)r[0]);
            } while ((ctx->ctr = (uint32_t)(ctx->ctr - 1)) != 0);
        }
        r[9] = r[7] + ((uint32_t)r[26] << 2);
        r[7] = r[9] + 4;
        vm_write32(r[31] + 8, (uint32_t)r[7]);
    }
    /* loc_002FE754: output mask, timeout */
    r[11] = u32(r[7]);
    r[0] = 0x00041FF0;
    r[7] += 8;
    vm_write32(r[31] + 8, (uint32_t)r[7]);
    vm_write32(r[11], (uint32_t)r[0]);
    r[9] = vm_read32(r[27] + 0xC);
    vm_write32(r[11] + 4, (uint32_t)r[9]);
    r[0] = vm_read32(r[27] + 8);
    setcr(ctx, 0, cmpu((uint32_t)r[0], 0x20));
    if ((uint32_t)r[0] > 0x20) {
        r[10] = u32(r[7]);
        r[9] = 0x00041EF8;
        r[0] = 0x0030FFFF;
        r[11] = r[7] + 8;
        vm_write32(r[10] + 4, (uint32_t)r[0]);
        vm_write32(r[31] + 8, (uint32_t)r[11]);
        vm_write32(r[10], (uint32_t)r[9]);
    } else {
        r[11] = u32(r[7]);
        r[9] = 0x00041EF8;
        r[0] = 0x0020FFFF;
        r[7] += 8;
        vm_write32(r[11] + 4, (uint32_t)r[0]);
        vm_write32(r[31] + 8, (uint32_t)r[7]);
        vm_write32(r[11], (uint32_t)r[9]);
    }
    /* loc_002FE7A4: uniforms of type 0x1006/0x1007 with a default value */
    r[29] = vm_read32(r[28] + 0xC);
    r[0] = vm_read32(r[28] + 0x10);
    setcr(ctx, 0, cmps((int32_t)r[29], 0));
    if ((int32_t)r[29] != 0) {
        r[31] = r[0] + r[28];
        r[30] = 0;
        r[27] = r[1] + 0x70;
        do {
            r[4] = u32(r[31]);
            r[30] += 1;
            r[31] += 0x30;
            r[0] = vm_read32(r[4] + 0x14);
            setcr(ctx, 0, cmps((int32_t)r[0], 0));
            if ((int32_t)r[0] != 0) {
                r[9] = vm_read32(r[4] + 8);
                r[0] = r[28] + r[0];
                r[3] = u32(r[25]);
                r[9] += -4102;
                r[7] = u32(r[0]);
                setcr(ctx, 0, cmpu((uint32_t)r[9], 1));
                r[5] = u32(r[27]);
                if ((uint32_t)r[9] <= 1) {
                    /* loc_002FE870: 16-byte default value to the stack */
                    const uint32_t sp = (uint32_t)(r[1] + 0x70);
                    if (r[1] + 0x70 == sp && r[7] + 16 <= 0x100000000ull &&
                        sp + 16ull <= 0x100000000ull && vm_copy(sp, (uint32_t)r[7], 16)) {
                        const uint8_t* b = vm_base + sp;
                        r[10] = b[0xB]; r[0] = b[0xC]; r[9] = b[0xD]; r[11] = b[0xE]; r[8] = b[0xF];
                    } else {
                        for (int g = 0; g < 12; g += 4) {
                            r[0] = vm_read8(r[7] + g);
                            r[9] = vm_read8(r[7] + g + 1);
                            r[11] = vm_read8(r[7] + g + 2);
                            r[10] = vm_read8(r[7] + g + 3);
                            vm_write8(r[1] + 0x70 + g, (uint8_t)r[0]);
                            vm_write8(r[1] + 0x71 + g, (uint8_t)r[9]);
                            vm_write8(r[1] + 0x72 + g, (uint8_t)r[11]);
                            vm_write8(r[1] + 0x73 + g, (uint8_t)r[10]);
                        }
                        r[8] = vm_read8(r[7] + 0xF);
                        r[0] = vm_read8(r[7] + 0xC);
                        r[9] = vm_read8(r[7] + 0xD);
                        r[11] = vm_read8(r[7] + 0xE);
                        vm_write8(r[1] + 0x7C, (uint8_t)r[0]);
                        vm_write8(r[1] + 0x7D, (uint8_t)r[9]);
                        vm_write8(r[1] + 0x7E, (uint8_t)r[11]);
                        vm_write8(r[1] + 0x7F, (uint8_t)r[8]);
                    }
                    ctx->lr = 0x002FE8F4;
                    func_002FF1A0(ctx);
                    drain(ctx);
                }
            }
            setcr(ctx, 0, cmps((int32_t)r[29], (int32_t)r[30]));
        } while ((int32_t)r[29] != (int32_t)r[30]);
    }
out:
    r[0] = vm_read64(r[1] + 0xD0);
    r[12] = vm_read32(r[1] + 0xC8);
    ctx->lr = r[0];
    ctx->cr = (ctx->cr & 0xFFFF0FFFu) | ((uint32_t)r[12] & 0x0000F000u);
    memcpy(r + 24, cs, sizeof cs);
    r[1] += 0xC0;
}
