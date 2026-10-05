# Task C report — 2026-10-04

Implemented the three boot handlers, writable HDD1 mapping and PSN-offline coverage. Built only `port/build-c`; no commits/pushes or game-dump modifications.

## Root causes and fixes

- `0xD1CA0503`: `cellRescVideoOutResolutionId2RescBufferMode`. Added the four standard resolution mappings with big-endian output and argument validation.
- `0x01220224`: `cellRescGcmSurface2RescSrc`. The unresolved handler claimed success without filling the source. Added conversion of the 60-byte guest GCM surface into the 16-byte RESC source: texture format, pitch, MSAA dimensions and color-buffer-0 offset. Corrected the SDK's RESC error constants.
- `0xE7FA820B`: `cellSaveDataEnableOverlay`. Added the void save-UI preference API.
- HDD1 previously fell through into the game directory. All three filesystem translators now share `PS3_HDD1_ROOT`, defaulting to `hdd1` beside `PS3_HDD0_ROOT` (otherwise `./hdd1`). Bare mount roots work; cache creation creates parent directories.
- Mapping alone was insufficient: FIOS passes `0x42` (`O_RDWR | O_CREAT`), but the PPU and syscall layers used incorrect flag values. Corrected the PS3 octal create/truncate/append/exclusive constants.
- POSIX free-space queries fabricated 1 GiB and FIOS disabled caching despite ample space. Added actual `statvfs` accounting for the translated mount.
- Added 61 D2 offline context handlers: 57 missing NP/lookup/score/TUS imports plus four existing TUS cloud/poll overrides. They return NP `OFFLINE` (`0x8002AA0C`), community `NO_LOGIN` (`0x8002A106`), or DRM `NO_LOGIN` (`0x80029516`). Five Poll/Wait APIs also fill the guest result. Existing local NP/score/TUS initialization remains available.
- Added SDK-library source dependencies to HLE table generation in the port and SDK template, so incremental builds register new handlers. Added the resolution-mapper/save-overlay names to `nid_database.py`. Regenerated build-c's table: 1117 handlers.

## Files changed by C

SDK:
- `libs/video/cellResc.c`, `libs/video/cellResc.h`
- `libs/system/cellSaveData.c`, `libs/system/cellSaveData.h`
- `libs/filesystem/cellFs.c`
- `runtime/ppu/ppu_fs.cpp`
- `runtime/syscalls/sys_fs.c`, `runtime/syscalls/sys_fs.h`
- `tools/nid_database.py`, `templates/project/CMakeLists.txt`

Port: `src/d2_psn.cpp` (new), `stubs.cpp`, `CMakeLists.txt`. Other workers' edits were preserved.

## Verification

Configured from `port/` with the OPERATIONS.md flags and `-B build-c`. `cmake --build port/build-c -j 3` and SDK `git diff --check` passed.

The required 40-second run, with `PS3RECOMP_METAL_HEADLESS=1`, reached its alarm timeout (exit 142), with **zero unresolved-NID lines**. Metal was unavailable in the sandbox; the runner used its software fallback.

Evidence in `port/runs/C-final.log`:
- line 6: `Registered 61 PSN-offline handlers`
- line 92: `open '/dev_hdd1/NPUB31321/cache.idx' -> fd 3`
- lines 94–95: `Creating new disk-based cache files`, `GetFreeSize(path='/dev_hdd1')`
- line 112: `VideoOutResolutionId2RescBufferMode(2) -> 0x4`
- lines 119–124: converter and SetSrc report `pitch=5120 1280x720 fmt=0xA5` (165 in SetSrc)
- line 164: `EnableOverlay(1)`

`C.validation.log` records four passing checks: RESC endian/output/error/MSAA behavior; HDD1 mapping/translator agreement/write-read; free-space parity with statvfs; all 61 negative offline errors and all five Poll/Wait result outputs. Fixtures: `C.validate.c`, `C.validate-psn.cpp`.

## Remaining

**36 handler gaps remain:** 10 P1 graphics/filesystem/module-loader, 20 P2 media/text/content/clock/UI, six P3 keyboard/socket/local-trophy. [C.missing-nids.md](C.missing-nids.md) lists every NID/function by priority and audits all 116 generic-table omissions (23 covered by SDK context handlers, 57 by new offline handlers).

The game still stalls beyond boot; title/menu rendering and online-flow behavior were not demonstrated. Both source offsets are zero as supplied by the guest; the converter faithfully copies them. A partial cache pair from the earlier fake-free-space run caused FIOS header retries on reuse. The final clean run verifies writable creation/open, not persistent-cache recovery. Task-created cache files were removed to leave other workers a clean cache directory.

## Prior art

Used `gh` to inspect RPCS3, Twisted Metal and ps3recomp PR #160 before implementation. NID hashes were checked with the SDK database against RPCS3 exports. RPCS3's RESC converter is itself a TODO stub; this implementation follows guest layouts/enums.

- [RESC exports](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellResc.cpp), [save-overlay API](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellSaveData.cpp)
- [PS3 open flags](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/lv2/sys_fs.h), [GCM surface layout](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/RSX/GCM.h)
- [NP errors](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/sceNp.h), [PSL1GHT RESC API](https://github.com/ps3dev/PSL1GHT/blob/master/ppu/include/rsx/resc.h)
