#include <cassert>
#include <cstdlib>
#include <cstdio>
extern "C" int ps3_ppu_thread_interactive(const char*);
extern "C" void d2_register_psn_offline() {}
extern "C" void d2_register_audio() {}
extern "C" void d2_register_debug_warp() {}
extern "C" void d2_register_cheats() {}
int main()
{
    const char* fios[] = {"fios mediathread0", "fios mediathread 11", "fios scheduler0"};
    const char* keep[] = {"PPU main", "RSX render", "RSX submit", "cellAudio",
        "_cellsurMixerMain", "synth2_generate", "NisAt3Line", "fios worker cond", "other"};
    unsetenv("PS3_D2_FIOS_QOS");
    for (auto name : fios) assert(ps3_ppu_thread_interactive(name) == 0);
    for (auto name : keep) assert(ps3_ppu_thread_interactive(name) == 1);
    assert(ps3_ppu_thread_interactive(nullptr) == 1);
    setenv("PS3_D2_FIOS_QOS", "interactive", 1);
    for (auto name : fios) assert(ps3_ppu_thread_interactive(name) == 1);
    for (auto name : keep) assert(ps3_ppu_thread_interactive(name) == 1);
    std::puts("FIOS default / interactive rollback; main, RSX, audio roles unchanged PASS");
}
