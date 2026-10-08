/* BLUS31313 opt-in battle transition probe. All calls run on the PPU main
 * thread, at its pad poll; no host thread writes live scene state. */
#include "ppu_recomp.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>

struct CellPadData;
extern "C" int32_t cellPadGetData(uint32_t, CellPadData*);

extern "C" void ps3_hle_register_ctx(uint32_t, const char*, void (*)(ppu_context*));
extern "C" uint64_t ppu_guest_call_ct(uint32_t, uint32_t, uint64_t, uint64_t,
    uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
extern "C" unsigned ppu_boot_frames_presented(void);

// Mapped by stage-record copy, event-start xrefs, and the same OPD ordering.
// Both executables retain the game/graphics/camera structure offsets below.
#if D2_GAME_VERSION == 140
static constexpr uint32_t D2_TOC = 0x47DF98;
static constexpr uint32_t GAME_TOC = 0x2DC0, GRAPHICS_TOC = 0x3820, CAMERA_TOC = 0x3794;
static constexpr uint32_t SELECT_STAGE = 0x0002E2E4, RESET_MAP = 0x001EB69C, START_EVENT = 0x0008F0FC;
static constexpr uint32_t MESSAGES_PENDING = 0x00033C48, DRAIN_MESSAGES = 0x00033CBC;
static constexpr uint32_t SET_HUB_CHARACTER = 0x0002EBC8, REFRESH_HUB_CHARACTER = 0x00295EF8;
#else
static constexpr uint32_t D2_TOC = 0x3FDE60;
static constexpr uint32_t GAME_TOC = 0x31D8, GRAPHICS_TOC = 0x3BE8, CAMERA_TOC = 0x3B54;
static constexpr uint32_t SELECT_STAGE = 0x0002E3C4, RESET_MAP = 0x001E1B80, START_EVENT = 0x0008D8A4;
static constexpr uint32_t MESSAGES_PENDING = 0x00033CF8, DRAIN_MESSAGES = 0x00033D6C;
#endif
static unsigned s_stage, s_hub_frame, s_hub_class, s_delay_seconds;
static std::chrono::steady_clock::time_point s_warp_at;
static auto warp_now()
{
#ifdef D2_WARP_TEST
    extern uint64_t d2_warp_test_milliseconds();
    return std::chrono::steady_clock::time_point{}+std::chrono::milliseconds(d2_warp_test_milliseconds());
#else
    return std::chrono::steady_clock::now();
#endif
}
static bool s_done, s_draining;

static uint64_t call(uint32_t code, uint64_t a = 0, uint64_t b = 0)
{
    return ppu_guest_call_ct(code, D2_TOC, a, b, 0, 0, 0, 0, 0, 0);
}

static void pad_probe(ppu_context* ctx)
{
    uint32_t port = (uint32_t)ctx->gpr[3];
    ctx->gpr[3] = (uint32_t)cellPadGetData(port,
        reinterpret_cast<CellPadData*>((uintptr_t)ctx->gpr[4]));
    if (port || ctx->thread_id != 1) return;
    const uint32_t toc = D2_TOC;
    uint32_t game = vm_read32(toc - GAME_TOC);
    if (!game) return;
    unsigned frame = ppu_boot_frames_presented();
    static auto next = warp_now();
    auto now = warp_now();
    if (now >= next) {
        std::fprintf(stderr, "[D2-warp] frame=%u selected=%u\n",
            frame, vm_read16(game + 0x1507F4));
        next = now + std::chrono::seconds(5);
        uint32_t graphics = vm_read32(toc - GRAPHICS_TOC);
        if (!graphics) return;
        float fade[4];
        for (unsigned i = 0; i < 4; ++i) {
            uint32_t bits = vm_read32(graphics + 0x23E72C + i * 4);
            std::memcpy(&fade[i], &bits, 4);
        }
        std::fprintf(stderr, "[D2-warp] stage=%u map_id=%u battle_flags=%u/%u fade=%g,%g,%g,%g fade_steps=%u\n",
            vm_read16(game + 0xD3BBE), vm_read16(game + 0xD3BBA),
            vm_read8(game + 0x15080B), vm_read8(game + 0x15080C),
            fade[0], fade[1], fade[2], fade[3], vm_read32(graphics + 0x23E74C));
    }
    if ((!s_stage && !s_hub_class) || s_done || vm_read16(game + 0xD3BBA) / 100 != 300) return;
    if (!s_hub_frame) s_hub_frame = frame;
    // Leave six seconds for the save-load dialogue to finish before starting
    // a new event. The host check dismisses that dialogue at wall time 14s.
    if (frame - s_hub_frame < 360) return;
    if (D2_GAME_VERSION == 140) {
        uint32_t scene = vm_read32(toc - 0x3FC4);
        uint32_t event = vm_read32(toc - 0x37C8);
        if (vm_read32(scene + 8) != 12 || vm_read32(event + 0x13314)) {
            if (frame % 300 == 0)
                std::fprintf(stderr, "[D2-warp] waiting: scene=%u event=%u\n", vm_read32(scene + 8), vm_read32(event + 0x13314));
            return;
        }
    }
#if D2_GAME_VERSION == 140
    if (s_hub_class) {
        // Use the game's leader setter and normal menu-exit actor rebuild,
        // on the PPU thread, after ordinary hub announcements finish.
        if (call(MESSAGES_PENDING)) return;
        unsigned count=vm_read16(game+0x1507EC),identity=0,matches=0;
        if (count<1 || count>128) return;
        for (unsigned i=0;i<count;++i) {
            uint32_t unit=game+0x598+i*0x1A60;
            if (vm_read16(unit+0x1158)!=s_hub_class) continue;
            identity=vm_read16(unit+0x1202);++matches;
        }
        s_done=true;
        if (matches!=1 || !identity || identity>=32768) {
            std::fprintf(stderr,"[D2-hub] character selection rejected: class=%u matches=%u identity=%u\n",s_hub_class,matches,identity);
            return;
        }
        call(SET_HUB_CHARACTER,identity);
        call(REFRESH_HUB_CHARACTER);
        std::fprintf(stderr,"[D2-hub] selected class=%u identity=%u map=%u through native setter/refresh; RAM only\n",
            s_hub_class,identity,vm_read16(game+0xD3BBA));
        if(s_stage) {s_hub_class=0;s_done=false;}
        return;
    }
#endif
    if(s_delay_seconds && now<s_warp_at) return;
    // Hub announcements own sprites in the hub animation pack. The normal
    // interaction path requests their destruction (140: 001C4C20); jumping straight
    // to event 11 leaves those sprites pointing into the freed pack. Let the
    // native message update unlink them before battle replaces that pack.
    if (!s_draining) {
        s_draining = true;
        call(DRAIN_MESSAGES);
        std::fprintf(stderr, "[D2-warp] draining hub messages before transition\n");
        return;
    }
    if (call(MESSAGES_PENDING)) return;
    s_done = true;
    // Replay the selector's stage-record copy, map reset, and event 11.
    unsigned index = 400;
    for (unsigned i = 0; i < 400; ++i) {
        uint32_t record = game + 0xD3BF0 + i * 0x5E;
        if (vm_read16(record + 0x28) == s_stage) { index = i; break; }
    }
    if (index == 400) {
        std::fprintf(stderr, "[D2-warp] stage %u absent from loaded stage table; ids:", s_stage);
        for (unsigned i = 0; i < 400; ++i)
            if (unsigned id = vm_read16(game + 0xD3BF0 + i * 0x5E + 0x28)) std::fprintf(stderr, " %u", id);
        std::fprintf(stderr, "\n");
        return;
    }
    call(SELECT_STAGE, game, index);
    vm_write8(game + 0x15080C, 0);
    uint32_t camera = vm_read32(toc - CAMERA_TOC);
    uint32_t record = game + 0xD3B98;
    float x = vm_read8(record) * 12.0f, z = vm_read8(record + 1) * 12.0f;
    uint32_t bits;
    std::memcpy(&bits, &x, 4); vm_write32(camera + 0x1F00, bits);
    std::memcpy(&bits, &z, 4); vm_write32(camera + 0x1F04, bits);
    call(RESET_MAP, 0);
    std::fprintf(stderr, "[D2-warp] confirm stage=%u table_index=%u event=11 map=%u camera=%g,%g\n",
        s_stage, index, vm_read16(record + 0x22), x, z);
    int32_t result = (int32_t)call(START_EVENT, 11, 0);
    std::fprintf(stderr, "[D2-warp] event start result=%d\n", result);
}

extern "C" void d2_register_debug_warp(void)
{
    const char* stage = std::getenv("D2_WARP_STAGE");
    const char* hub = std::getenv("D2_HUB_CHARACTER");
    const char* delay = std::getenv("D2_WARP_DELAY_SECONDS");
    if(delay) {
        char* end;unsigned long value=std::strtoul(delay,&end,10);
        if(D2_GAME_VERSION!=140 || !stage || !*delay || *end || value<1 || value>600) {
            std::fprintf(stderr,"[D2-warp] invalid delayed transition configuration\n");return;
        }
        s_delay_seconds=unsigned(value);s_warp_at=warp_now()+std::chrono::seconds(value);
    }
    if (!stage && !hub && !std::getenv("D2_WARP_TRACE")) return;
    if (hub) {
#if D2_GAME_VERSION == 140
        char* end;
        unsigned long value=std::strtoul(hub,&end,10);
        if ((stage && !s_delay_seconds) || !*hub || *end || !value || value>=32768) {
            std::fprintf(stderr,"[D2-hub] invalid or conflicting D2_HUB_CHARACTER\n");return;
        }
        s_hub_class=unsigned(value);
#else
        std::fprintf(stderr,"[D2-hub] character selection requires the1.40 research build\n");return;
#endif
    }
    if (stage) {
        char* end;
        unsigned long value = std::strtoul(stage, &end, 10);
        if (!*stage || *end || !value || value > 65535) {
            std::fprintf(stderr, "[D2-warp] invalid D2_WARP_STAGE: %s\n", stage);
            return;
        }
        s_stage = value < 100 ? 100 + (unsigned)value : (unsigned)value;
    }
    if(s_delay_seconds) std::fprintf(stderr,"[D2-warp] delayed transition after %u seconds; hub selection runs first\n",s_delay_seconds);
    ps3_hle_register_ctx(0x8B72CDA1, "cellPadGetData/D2 warp", pad_probe);
    std::fprintf(stderr, "[D2-warp] armed stage=%u (1=101; packed chapter*100+map)\n", s_stage);
}
