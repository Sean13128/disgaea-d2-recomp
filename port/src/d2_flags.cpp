/* Read-only scene snapshot; the runner rejects mismatched executables. */
#include "ppu_recomp.h"
#include "d2_flags.h"
extern "C" uint8_t* vm_base;
extern "C" int d2_flags_guest_location(unsigned* map, unsigned* stage)
{
#if D2_GAME_VERSION == 140
    constexpr uint32_t toc = 0x47DF98, game_toc = 0x2DC0, entry = 0x461000;
#elif D2_GAME_VERSION == 100
    constexpr uint32_t toc = 0x3FDE60, game_toc = 0x31D8, entry = 0x3E0EE8;
#else
    return 0;
#endif
#if D2_GAME_VERSION == 140 || D2_GAME_VERSION == 100
    if (!vm_base || vm_read32(entry + 4) != toc) return 0;
    uint32_t game = vm_read32(toc - game_toc);
    if (game < 0x10000 || game > 0x10000000 - 0xD3BC0) return 0;
    *map = vm_read16(game + 0xD3BBA);
    *stage = vm_read16(game + 0xD3BBE);
    return 1;
#endif
}
