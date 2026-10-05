/* D2's static SurMixer assumes its priority-0 worker has published the event
 * key before Start runs. Host pthread priorities do not guarantee that order. */
#include "ppu_recomp.h"
#include "ps3emu/error_codes.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>

extern "C" int32_t cellAudioSetNotifyEventQueue(uint64_t);
extern "C" uint32_t sys_event_find_queue_by_key(uint64_t);
extern "C" void ps3_hle_register_ctx(uint32_t, const char*, void (*)(ppu_context*));

static void notify_queue(ppu_context* ctx)
{
    uint64_t key = ctx->gpr[3];
#if D2_GAME_VERSION == 140
    // 00306474: r30 = static SurMixer state; +500 is the worker's queue key.
    if (!key && ctx->lr == 0x00306514 && ctx->gpr[30]) {
        const uint32_t address = (uint32_t)ctx->gpr[30] + 0x500;
        const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        do {
            key = vm_read64(address);
            if (key && sys_event_find_queue_by_key(key)) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        } while (std::chrono::steady_clock::now() < until);
        std::fprintf(stderr, "[D2 audio] waited for SurMixer queue publication: key=0x%llX\n",
            (unsigned long long)key);
        if (!key || !sys_event_find_queue_by_key(key)) {
            ctx->gpr[3] = (uint32_t)CELL_AUDIO_ERROR_EVENT_QUEUE;
            return;
        }
    }
#endif
    ctx->gpr[3] = (uint32_t)cellAudioSetNotifyEventQueue(key);
}

#if D2_GAME_VERSION == 140
void func_00308234(ppu_context*);
extern "C" void ppu_register_function(uint64_t, void (*)(ppu_context*));
static void delayed_mixer(ppu_context* ctx)
{
    const unsigned ms = (unsigned)std::strtoul(std::getenv("D2_AUDIO_INIT_DELAY_MS"), nullptr, 10);
    std::this_thread::sleep_for(std::chrono::milliseconds(ms > 1000 ? 1000 : ms));
    func_00308234(ctx);
}
#endif

extern "C" void d2_register_audio(void)
{
    ps3_hle_register_ctx(0x377E0CD9, "cellAudioSetNotifyEventQueue", notify_queue);
#if D2_GAME_VERSION == 140
    // Deterministically expose the priority-scheduling race in host checks.
    if (std::getenv("D2_AUDIO_INIT_DELAY_MS"))
        ppu_register_function(0x00308234, delayed_mixer);
#endif
}
