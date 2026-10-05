# Task A — macOS frame clock and graphics boot

## Root causes and changes

- The runner starts Metal on its frame-clock thread. `create_window()` and `rsx_metal_backend_pump_messages()` synchronously dispatch to the macOS main queue, while that thread is busy inside `ppu_run()`. The queue cannot execute, backend init never returns, and the clock never drains the FIFO. `host_posix.c` does not have this problem: its graphics harness initializes/pumps on main. PR #160's Yakuza adapter explicitly keeps a repeated CFRunLoop loop on main while running the guest on a worker; inspected with `gh`, along with Twisted Metal's runner.
- Fixed this generically inside SDK `ppu_run()`: a call on macOS main starts a guest pthread with a 16 MB native stack and services the main CFRunLoop until completion. Calls already on a worker keep their existing behavior. An atomic completion flag handles early/nested run-loop returns; join occurs only after completion. Added CoreFoundation linkage.
- Metal triangle MISMATCH: configuration has no spirv-cross/guest shader translator, but Metal unconditionally selected the register-file draw engine. Even that engine's fixed shaders are HLSL and require translation, so pipeline creation drops the triangle while clears succeed. Select the existing built-in MSL/vtable path when translation is unavailable or fixed-function is forced. Cheap SDK fix; actual Metal pixel readback is still unverified here.
- The sandbox exposes no Metal device, even headless. Added an explicitly logged software backend fallback to the port runner and SDK template so FIFO/fence progress remains testable. Added first-three-guest-present diagnostics.
- Draining the first fences exposed a SIGSEGV in `sceNpManagerGetNpId`: `sceNpGetNpId` omitted `GUEST_PTR`, unlike adjacent identity getters. Added the missing translation in the shared implementation. macOS crash report identified the exact function and raw guest address `0x00FAB690`.

## Files changed by A

- `ps3recomp/runtime/ppu/ppu_loader.cpp`
- `ps3recomp/CMakeLists.txt` — only the CoreFoundation framework addition is A's change.
- `ps3recomp/libs/video/rsx_metal_backend.m`
- `ps3recomp/libs/network/sceNp.c`
- `port/main.cpp`
- `ps3recomp/templates/project/main.cpp`

## Verification

- Configured from `port/` with the OPERATIONS.md CMake line, changing only `-B` to `build-a`. Native executable and `ps3recomp_host` linked successfully; latest build log: `port/runs/A-build-final.log`.
- A standalone regression harness linked the actual port/runtime objects with a test entry function. It asserts guest execution is off main, two synchronous main-queue dispatches execute on main despite explicitly stopping the run loop, missing-entry errors propagate, and NP ID bytes are written in guest memory. `port/runs/A-main-queue-test.log:13`: `[A-test] worker guest, repeated main-queue dispatch after run-loop stop, return status and NP guest pointer: PASS` (exit 0).
- `port/runs/A-fifo2.log:160–168`: drain consumes the initial ring and fence 1; `GetNpId(user=0) -> "PS3Player"` replaces the crash. Lines 340/366: `CLEAR_SURFACE`; line 353: `SetConvertAndFlip ... -> flip`; lines 370–394: START/ANM archives open/read. At line 408 and through the 40-second timeout, `getoff=00001A44 put=00001A44 ref=00000005`: FIFO is caught up, rather than stuck at get 0. Guest subsequently prints `NisFiosIsIdle 188 : -2147416313 ...START_1.dat`; the underlying loading issue is not established.
- The latest combined-worker build/run (`port/runs/A-final.log`, timeout exit 142) also drains the initial FIFO: line 365 and thereafter `getoff=0000019C put=0000019C ref=00000001`. It now starts lifted synth2 (lines 190–214), has an unavailable CoreAudio device (215–216), and remains in audio/loading waits (`NisAt3Line*` at LR `0x00157E60`, mixer queue 3) before further drawing. This differs from the earlier farther graphics run because other workers' shared changes were incorporated; the exact guest blocker still needs tracing.
- `git -C ps3recomp diff --check` passes. Existing/concurrent worker changes retained. No game dump modifications, other build-directory writes, commits or pushes.

## Remaining / host verification

- **No visible Metal window or Metal presentation verified:** sandbox `MTLCreateSystemDefaultDevice()` returns nil (`port/runs/A-metal-draw.log:1`, `A-final.log:35`). Software fallback is clearly identified in logs and is not evidence of Metal rendering. The main-queue regression verifies the actual deadlock fix independently of GPU access.
- Missing shader translation still limits actual game rendering; the fixed MSL path can render the harness triangle but cannot reproduce arbitrary guest shaders.
- Run outside the sandbox to verify the triangle and window:

```sh
cd '/Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE'
PS3RECOMP_METAL_HEADLESS=1 ./port/build-a/ps3recomp_sdk/ps3recomp_host --draw > port/runs/A-host-draw.log 2>&1
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" PS3_HDD0_ROOT="$PWD/port/hdd0" GCM_DRAINDBG=1 perl -e 'alarm shift; exec @ARGV' 40 ./port/build-a/DisgaeaD2Recomp work/EBOOT.elf > port/runs/A-window.log 2>&1
```

Expected graphics startup: `[ppu] guest worker started; main thread servicing macOS events`, `[RSX metal] windowed ... vtable`, `[rsx] Metal backend init OK -- window open`. A completed guest flip logs `[rsx] presented guest frame 1`. Host `--draw` should report pixel `0xFFFF0000 ... OK`; this expectation awaits a Metal-capable run.
