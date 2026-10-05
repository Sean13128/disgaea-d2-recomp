# AD — Disgaea D2 1.40 and DLC

Implemented and verified headless on October 5, 2026. `D2_GAME_VERSION=140` is now the default; `100` remains supported. Own build: `port/build-ad`. No dump writes, commits, pushes, or changes to `port/build` or video/menu implementations.

## Root causes and changes

1. **The update is a different executable.** Lifted `work/v140/EBOOT.elf` into `port/src/recomp-140` and `port/out-140` using the existing loader/lifter with `PS3RECOMP_CHUNK_LINES=50000`: 10,315 functions, 21 chunks. Re-extracted both SPU images into `port/spu-140`; synth2 is unchanged, NisGraphics changed. CMake selects the recompilation, loader metadata, SPU registration, movie overrides, and launcher ELF by version. The runner rejects a mismatched ELF before running guest code.
2. **SPU CRT entry addresses collide.** Both graphics/audio images contain the graphics entry `0xD0`; with extraction order reversed, the SDK selected synth2 for graphics and boot stopped after three frames. The runtime now identifies the imported ELF by its workload fingerprint. An unknown imported ELF cannot accidentally select another image's CRT.
3. **Installed content needs the correct mounts.** `port/install-content.sh` installs update `PARAM.SFO`/`USRDIR` under `hdd0/game/BLUS31313`, DLC under `hdd0/game/NPUB31321`. Default installation uses a fresh copy of `port/hdd0`; `--into <hdd0>` installs into an explicit destination. Update files overlay disc USRDIR reads through a shared SDK helper; missing update files fall back to disc. Version 140 selects `PS3_GAME_UPDATE_ID=BLUS31313`. Direct hdd0 paths also resolve correctly. Installed into `port/hdd0`; application-support hdd0 was not modified.
4. **Offline NPDRM stubs rejected legitimate local content.** Replaced those two port stubs with SDK filesystem handlers that validate the supplied klicensee, title/header hashes, and payload before exposing plaintext. Fixed full 20-byte HMAC checking and plaintext-mode handling. Failed decryption returns an error instead of ciphertext or success without an fd. Decrypted caches live in writable hdd0/cache/edat, never beside dump files. `cellFsOpen`, syscall open, and `cellFsSdataOpen` share this resolver. Crypto behavior was checked against [RPCS3's EDAT implementation](https://raw.githubusercontent.com/RPCS3/rpcs3/master/rpcs3/Crypto/unedat.cpp); its [NPDRM handler](https://raw.githubusercontent.com/RPCS3/rpcs3/master/rpcs3/Emu/Cell/Modules/sceNp.cpp) also permits local checks without PSN login.

## Address mapping

Matched OPD ordering, instruction signatures, call patterns, and TOC data references; verified the movie facade and stage transition in both builds.

| Hook/data | 1.00 | 1.40 |
|---|---:|---:|
| NisMovie Open | `0015FD14` | `001686AC` |
| NisMovie Play | `0015F9F4` | `00168304` |
| NisMovie Close | `0015F680` | `00167FC8` |
| Movie state TOC displacement | `-487C` | `-4584` |
| Stage-record selection | `0002E3C4` | `0002E2E4` |
| Map reset | `001E1B80` | `001EB69C` |
| Start event | `0008D8A4` | `0008F0FC` |
| TOC | `003FDE60` | `0047DF98` |
| Game/graphics/camera TOC displacements | `-31D8/-3BE8/-3B54` | `-2DC0/-3820/-3794` |
| Save load/save | `00164C3C/00164D74` | `0016D700/0016D7FC` |
| Secure-ID pointer source | `*(TOC-46C0)+40 = 396C98` | `*(TOC-43A8)+40 = 400780` |

Stage table stride `0x5E`, record fields, camera fields, and game-state offsets are unchanged. Secure ID remains sixteen `0F` bytes; the importer documentation now records both sources. Draw/shader tracing has no guest address hooks needing remapping.

## DLC findings

The prepared pack contains **45** EDATs: `flag00010001–00010018`, `flag00040001–00040022`, and `flag00050001–00050005`. All declare license type **3**, version 3: 36 use flags `0x0C`, nine use `0x3C`. They are encrypted, not debug/plaintext files. The game supplies the matching klicensee; **none requires a per-user RAP**. Every installed flag is authenticated and read as plaintext during boot. D2's DRM-open caller is `003311D4` in 1.40 (`00321200` in 1.00).

The game also probes `flag00020000.edat` and `flag00030000.edat`, which are absent from this pack; they correctly return `0x80010006` (missing file), rather than a license failure. No installed flags were rejected. Recognition is verified at the game's flag-open/read path; a visual inventory of every DLC character/item remains a playtest.

## Verification evidence

Final normal build uses AF/AG's real callbacks, without temporary link placeholders. Each guest run lasts 40 seconds on a copied hdd0; timeout status 142 is expected. Movies are skipped for automation.

- `port/runs/AD-final-check.log:10,20,30`: title, Continue slot 01, and Continue slot 00 **PASS**, each with 45 accepted and 45 read flags, update data opened, and continuing guest frames. No OOB/FAULT/Bus-error lines in these final runs.
- `port/runs/AD-host.nXKVlw/title/run.log:157`: NisGraphics runs as image 2; line 211: synth2 runs as image 1. Lines 1015/1019 show the first flag accepted (`result=0`) and read (12 plaintext bytes).
- `port/runs/AD-host.nXKVlw/slot01/run.log:497,945`: installed update `START_7.dat` opened. Line 2093: `LOAD complete for 'NPUB31321_NORMAL_01'`; line 2545: stage 101 confirmation, table index 83; lines 2830/3505: battle stage 5011/map 101 continues.
- `port/runs/AD-host.nXKVlw/slot00/run.log:2099,2549,3509`: user save loaded, stage confirmed, battle active.
- `port/runs/AD-100-continue.log:2056,2504,3495`: version 100 still loads slot 00, confirms the same stage, and remains in battle. `build-ad` was then rebuilt as **140**.
- `port/runs/AD-version-guard.log:4`: version 140 rejects the 1.00 ELF with the expected version error.
- `port/runs/AD-edat-test.log:217`: **84 EDAT checks pass**, covering versions 3/4, CMAC/HMAC16/HMAC20, CBC/plaintext, wrong keys, and title/dev/header/metadata/payload corruption. Independent PyCryptodome fixtures: `codex/AD.edat-test.py`.
- `port/runs/AD-spu-test.log`: **101 passed, 0 failed**, including overlapping CRT addresses and unknown imported images.
- `port/runs/AD-fs-test.log:1`: overlay precedence, disc fallback, version-100 isolation, explicit DLC/bare hdd0 translation pass. Source: `codex/AD.fs-test.c`.
- `port/runs/AD-build-140-final.log` and `AD-app-build.log`: runner and launcher compile/link successfully. The shared distribution bundle was not rebuilt.

## Files changed

Port: `port/CMakeLists.txt`, `main.cpp`, `stubs.cpp`, `run.sh`, `play.sh`, `install-content.sh`; `port/src/d2_movie.cpp`, `d2_debug_warp.cpp`, `d2_psn.cpp`, `d2_launcher.m`, `d2_launcher_paths.h.in`; generated `src/recomp-140`, `out-140`, `spu-140`. Importer documentation: `tools/d2_save_import.py`. Added test/host scripts, this report, ignore exceptions, and an OPERATIONS entry. Concurrent AF/AG edits in shared port files were preserved.

SDK: `libs/filesystem/{cellFs.c,edat.c,edat.h}`, `runtime/ppu/ppu_fs.cpp`, `runtime/syscalls/{sys_fs.c,lv2_register.c}`, `runtime/spu/{spu_lifted_thread.c,spu_lifted_thread.h,tests/test_spu_lifted_start.c}`. Exported only these changes as `patches/AD-runtime.diff`.

## Host check and remaining work

Run `bash codex/AD.host-check.sh` for real Metal: title, then Continue slot 01 → hub → battle; logs and frame captures are retained under a unique `port/runs/AD-host.*`. Uses copies of hdd0, `grep`, and no `rm`. Add `AD_CHECK_SLOT00=1` to check both saves. `AD_HEADLESS=1 AD_SKIP_BUILD=1 AD_CHECK_SLOT00=1 bash codex/AD.host-check.sh` reproduces the completed guest-flow checks. Inspect the captured title/battle images; real-Metal visual verification remains pending.

Configure either version with the existing Homebrew flags and `-DD2_GAME_VERSION=100` or `140`; use `work/EBOOT.elf` for 100 and `work/v140/EBOOT.elf` for 140. `run.sh`/`play.sh` and the launcher now choose the matching ELF. Rebuilding the distributed app and installing content into its actual application-support hdd0 remain host-side integration steps.

One earlier run with additional blind Cross pulses *after battle entry* produced guest OOB accesses and a Bus error (`port/runs/AD-host.UsTk9h/slot01/run.log:3224+`). The final checks send only the two inputs needed for Continue/dialog dismissal and finish without faults. That input-dependent failure remains unresolved; a full interactive battle turn and longer DLC playtest are still needed.

Generic EDAT compressed/debug modes remain unsupported and fail explicitly. Other license types retain the SDK's operator-supplied RIF-key route; RAP-file conversion was not added because all supplied content is free-license type 3.
