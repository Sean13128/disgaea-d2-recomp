/*
 * ps3recomp game project -- game-specific hooks and overrides.
 *
 * main.cpp is the runner and is game-agnostic. This file is where a port puts
 * everything that is not: the PRX loading hook it must answer, overrides for
 * firmware functions the HLE library gets wrong for this title, and patches
 * over recompiled code.
 *
 * It starts out as the empty version of all of that, which is what a game with
 * no lifted PRX and no overrides needs.
 */

#include <cstdio>
#include <cstring>
#include <cstdlib>

#include "ps3emu/ps3types.h"
#include "ps3emu/error_codes.h"

/* ---------------------------------------------------------------------------
 * PRX loading
 *
 * main.cpp calls this once, after the lifted function table is registered and
 * vm_base is live, before the game runs. A title that lifts a real system PRX
 * -- libsre, which is cellSpurs and cellSync -- loads its image into guest RAM
 * here and registers its exports. Most ports never need to: the HLE library
 * answers those modules instead.
 * -----------------------------------------------------------------------*/

extern "C" void d2_register_psn_offline(void);
extern "C" void d2_register_audio(void);
extern "C" void d2_register_debug_warp(void);
extern "C" void d2_register_cheats(void);

extern "C" void ps3_load_prx_modules(void)
{
#if D2_GAME_VERSION == 140
    setenv("PS3_GAME_UPDATE_ID", "BLUS31313", 0);
#endif
    d2_register_psn_offline();
    d2_register_audio();
    d2_register_debug_warp();
    d2_register_cheats();
}

/* ---------------------------------------------------------------------------
 * Example: Override a specific NID
 *
 * The module system resolves function imports by NID.  To replace a default
 * HLE stub with custom logic, register your function at init time.
 * -----------------------------------------------------------------------*/

/*
 * Example: override cellGcmSetFlipMode (NID 0xA53D12AE) to force vsync.
 *
 *   static void my_cellGcmSetFlipMode(u32 mode)
 *   {
 *       printf("[hook] cellGcmSetFlipMode: forcing VSYNC (was %u)\n", mode);
 *       // Force vsync regardless of what the game requested
 *       cellGcmSetFlipMode(CELL_GCM_DISPLAY_VSYNC);
 *   }
 *
 * Then in your init code:
 *
 *   ps3::modules::override_nid(0xA53D12AE,
 *       reinterpret_cast<void*>(my_cellGcmSetFlipMode));
 */

/* ---------------------------------------------------------------------------
 * Example: Hook into module loading
 *
 * You can intercept cellSysmoduleLoadModule to perform custom actions
 * when a particular module is loaded.
 * -----------------------------------------------------------------------*/

/*
 *   static s32 my_loadmodule_hook(u16 id)
 *   {
 *       printf("[hook] Module 0x%04X loaded\n", id);
 *
 *       if (id == CELL_SYSMODULE_AUDIO) {
 *           // Perform custom audio backend initialization
 *           init_my_audio_backend();
 *       }
 *
 *       // Call the original implementation
 *       return cellSysmoduleLoadModule(id);
 *   }
 */

/* ---------------------------------------------------------------------------
 * Game-specific patches
 *
 * Sometimes you need to patch recompiled code at specific addresses.
 * Use the patch system to modify behavior without editing generated code.
 * -----------------------------------------------------------------------*/

/*
 *   // Skip an integrity check at guest address 0x00812FA0
 *   ps3::patches::nop_range(0x00812FA0, 0x00812FB0);
 *
 *   // Replace a function call with a direct return
 *   ps3::patches::force_return(0x009A1000, 0);  // return 0
 */

/* The generated workload registry assigns NisGraphics image 2; synth2 is 1. */
extern "C" int ps3_spu_poll_idle_graphics(int image_id)
{
    return image_id == 2;
}

/* FIOS serves foreground I/O; leave rendering and the audio chain interactive. */
extern "C" int ps3_ppu_thread_interactive(const char* name)
{
    const char* policy = std::getenv("PS3_D2_FIOS_QOS");
    bool fios = name && (!std::strncmp(name, "fios mediathread", 16) ||
                         !std::strncmp(name, "fios scheduler", 14));
    int interactive = !fios || (policy && !std::strcmp(policy, "interactive"));
    if (fios && std::getenv("PS3_MULTIWAIT_STATS"))
        std::fprintf(stderr, "[d2-qos] thread=\"%s\" role=%s\n", name,
                     interactive ? "interactive" : "default");
    return interactive;
}
