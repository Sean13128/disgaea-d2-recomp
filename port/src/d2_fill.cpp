/* BLUS31313 1.40 guest memset (func_0033D91C: r3 dst, r4 byte, r5 size).
 * The lifted loop is 18% of active PPU time in menus; one vm_fill replaces it.
 * Registers end exactly as the lifted body leaves them (tests/AQ.fill-test.cpp
 * compares the whole context), so callers that read a volatile still agree.
 * Ranges vm_fill declines (diagnostics, null page, MMIO, OOB) run the lift.
 * The 1.00 lift of this function ends in a tail trampoline; it stays lifted. */
#include "ppu_recomp.h"

extern "C" int vm_fill(uint32_t a, uint8_t v, uint32_t n);
void d2_original_0033D91C(ppu_context*);

static void set_cr0(ppu_context* ctx, uint32_t a, uint32_t b)
{
    ctx->cr = (ctx->cr & ~0xFu) | (a < b ? 8u : a > b ? 4u : 2u);
}

void func_0033D91C(ppu_context* ctx)
{
    const uint64_t a = ctx->gpr[3], n = ctx->gpr[5], e = a + n;
    const uint8_t b = (uint8_t)ctx->gpr[4];
    if ((a | n) >> 32 || e >> 32 || !vm_fill((uint32_t)a, b, (uint32_t)n)) {
        d2_original_0033D91C(ctx);
        return;
    }
    /* Final register state of the lifted body, from its loop bounds. */
    ctx->gpr[4] = b;
    ctx->gpr[5] = e;
    uint64_t r10 = a;
    if (n > 7) {
        const uint64_t h = (uint64_t)b << 8 | b, w = h << 16 | h;
        const uint64_t r12 = e & 0xFFFFFFF8u, r7 = r12 - 64;
        uint64_t r8 = (a + 1) & 0xFFFFFFFEu;
        uint64_t r6 = (((r8 + 2) & 0xFFFFFFFCu) + 4) & 0xFFFFFFF8u;
        uint64_t r0 = w;
        if (r6 <= r7) {
            const uint64_t blocks = (r7 - r6) / 64 + 1;
            r8 = r6 + (blocks - 1) * 64;
            r6 += blocks * 64;
        }
        if (r12 > r6) {
            r6 = r12;
            r0 = r6;
        }
        ctx->gpr[0] = r0;
        ctx->gpr[6] = r6;
        ctx->gpr[7] = r7;
        ctx->gpr[8] = r8;
        ctx->gpr[9] = w << 32 | w;
        ctx->gpr[11] = h;
        ctx->gpr[12] = r12;
        r10 = r6;
    }
    ctx->gpr[10] = r10;
    set_cr0(ctx, (uint32_t)e, (uint32_t)r10);
    if (e > r10) {
        ctx->gpr[9] = e - 1;
        ctx->gpr[11] = e - r10;
        ctx->ctr = 0;
    }
}
