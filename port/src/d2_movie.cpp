/* BLUS31313 optional movie skip. Playback uses the SDK by default.
 * D2_MOVIE_SKIP=1 keeps the clean completion path for troubleshooting. */
#include "ppu_recomp.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

void d2_original_0015FD14(ppu_context*);
void d2_original_0015F9F4(ppu_context*);
void d2_original_0015F680(ppu_context*);

static bool native_movie()
{
    static const bool enabled = [] {
        const char* value = std::getenv("D2_MOVIE_SKIP");
        return !value || std::strcmp(value, "1") != 0;
    }();
    return enabled;
}

static uint32_t movie_state(ppu_context* ctx)
{
    return vm_read32(ctx->gpr[2] - 0x487C);
}

/* _NisMovie_Open: the original transitions idle (1) -> ready (2). */
void func_0015FD14(ppu_context* ctx)
{
    if (native_movie()) { d2_original_0015FD14(ctx); return; }
    uint32_t state = movie_state(ctx);
    if (vm_read8(state) != 1) { ctx->gpr[3] = 1; return; }
    vm_write8(state, 2);
    ctx->gpr[3] = 0;
    std::printf("[D2 movie] opened; D2_MOVIE_SKIP=1, using clean completion\n");
}

/* NisMovie_Play: success, followed by idle. NisMovie_IsPlaying (0015EFB0)
 * tests state == 3 || state == 4; callers therefore take their finished path.
 * No codec workers/resources were created, so Update remains a no-op. */
void func_0015F9F4(ppu_context* ctx)
{
    if (native_movie()) { d2_original_0015F9F4(ctx); return; }
    uint32_t state = movie_state(ctx);
    if (vm_read8(state) != 2) { ctx->gpr[3] = 1; return; }
    vm_write8(state, 1);
    ctx->gpr[3] = 0;
    std::printf("[D2 movie] finished cleanly (no decoded frames)\n");
}

/* NisMovie_Close: do not close codecs that the fallback never opened. */
void func_0015F680(ppu_context* ctx)
{
    if (native_movie()) { d2_original_0015F680(ctx); return; }
    vm_write8(movie_state(ctx), 1);
    ctx->gpr[3] = 0;
}
