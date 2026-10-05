# U — automated stage warp and battle investigation

Implemented `D2_WARP_STAGE=1` (map 101, first battle), verified from the user's Continue save. The current build does **not** reproduce the old frozen 218-draw state. Real Metal is unavailable in this sandbox; visual verification of this hook remains for Claude. OPERATIONS.md independently records that the user can now enter battle on real Metal after the intervening runtime fixes. The specific historical black-screen root cause is not isolated; no speculative SDK change was made.

## Changes

- `port/src/d2_debug_warp.cpp`: opt-in context HLE wrapper for `cellPadGetData` (NID `8B72CDA1`). Calls the original pad handler, then runs the warp once on PPU main thread 1. Waits 360 presented frames after the loaded record becomes a castle map (`300xx`). No registration or behavior change without `D2_WARP_STAGE`/`D2_WARP_TRACE`.
- `port/CMakeLists.txt`, `port/stubs.cpp`: compile/register the hook.
- `codex/U.host-check.sh`: builds only `port/build-u`, Continue → warp, 40-second run, real Metal frame dumps every 120 frames, draw captures and filtered metrics. Uses `grep`, no removal commands. `.gitignore`: whitelist this script.

`D2_WARP_STAGE=1..99` aliases chapter 1 maps 101..199; larger values are packed `chapter*100+map`, found in the loaded 400-entry stage table. Absent/invalid entries log an error instead of calling the event. `D2_WARP_TRACE=1` alone logs state without warping.

## Guest path recovered

- Preview creator `00242D3C` uses "storyselect mapload thread", entry `00242E60`; stage UI `001B36D8` calls it. Map format is `Data/MAP/mp%03d/map%03d%02d.lzs`, splitting packed map ID by 100.
- Normal confirmation in `001B2A64` (`001B2ED4` onward, event calls at `001B2F7C` / `001B3530`) calls `0002E3C4(game,index)`, clears `game+15080C`, sets camera X/Z from the copied stage record's first bytes ×12, calls `001E1B80(0)`, then `0008D8A4(11,0)`.
- The hook reproduces these operations through SDK `ppu_guest_call_ct` with TOC `003FDE60`, preserving the guest event/scene transition. Event 11 ultimately reaches the stage-load VM command (`000C4738`, map loader `001F1EE4`). It does not merely open preview assets or force a rendered scene.
- First battle: table index 83, packed map 101, mission ID 5011, camera `(84,12)`, event task result 6665. `0002E3C4` copies 94 bytes from `game+D3BF0+index*94+6` to `game+D3B98`.

## Verification and diagnosis

Release build passed (`port/runs/U-build-final.log`); shell syntax and whitespace checks passed. Both 40-second headless script runs passed, ending with expected alarm status 142:

- `port/runs/U-host.S4io1s/run.log`: save LOAD line 8216; hub map 8246; stage confirmation 23308; event result 23309; battle map open 23342; mission/map state 27704.
- With no extra battle input: frame 1140 has 218 draws (line 31559), frame 1200 still 218 (35454), frame 1260 becomes 255 (39976), remaining 255 through frame 2160 (107916). Among matching frame-1140/1200 binary captures, 81 changed and 602 matched. This is not the old identical frozen sequence.
- With Cross advances: `port/runs/U-host.Bsn25W/run.log` confirms stage at 23445; frame 1140 is 218 (31692); frame 1260 is 255 (40064); later counts vary 222–313 with input. D2_BOOT_TRACE shows changing main-thread PCs and advancing flips, e.g. frame 1078 / LR `002C3284` at 27807–27808.

The 218-draw frame consists of pipeline 32: 1 background quad; pipeline 25: 25 world-mesh draws; pipeline 63: 164 additional mesh draws; pipeline 27: 3 quads; pipeline 31: 25 textured quads including the final black overlay. It is not 218 fullscreen fades. All draw/present targets are surface 1, a single 1280×720 color surface at offset zero; depth target 2. The gated NV3089 trace logged no scaled-image blits. No missing offscreen resolve is evident in this capture.

World matrices and vertices are finite and project into the view. Color writes are enabled, depth is LEQUAL with clear depth 1, and alpha tests are NOTEQUAL zero. Shader translations reported success. The final black quad has alpha 0.258824 at frame 1140, multiplied by FP constant 1.99219 (~0.516), with SRC_ALPHA / ONE_MINUS_SRC_ALPHA blending: a partial overlay, not an opaque black output. Global fade remains `(1,1,1,1)` with zero remaining fade steps. This trace does not prove Metal rasterization or every stencil operation correct.

`port/runs/U-trace1.log` traced NisGraphics image 1 with `SPU_DMATRACE_ALL=1 YDKJ_DMA_IMG=1`. Hub work includes 224-byte PUTs to `01FF8980`/`01FF1900`; steady battle increases to 736 bytes at both destinations, plus 16-byte completion PUTs. Between lines 1000668–1265651: 284 of each, 852 PUTs total. Example battle payload PUTs are at 920387–920388. The workers continue doing battle work; missing NisGraphics execution is not supported. Repeated small GETs are queue polling, not proof of a stalled job.

Compact original 218-draw binaries/shaders retained in `port/runs/U-evidence/draws`; complete final captures reside in the two U-host directories above. U's disposable scratch was removed. No dump, other build directory, SDK source, commit, or push was changed by U.

## Claude host check

```sh
codex/U.host-check.sh
```

Inspect `port/runs/U-host.*/frames/f*.ppm` after the `[D2-warp] confirm` line. Default Cross pulses at 22/26/30/34/38 seconds advance battle text. `U_ADVANCE=0` omits those; `U_HEADLESS=1` records GPU-free evidence; `U_SKIP_BUILD=1` reuses build-u; `U_TEXTURE_LIMIT=2048` captures more textures for V. `U_PAD_SCRIPT` overrides timing if cold Metal startup misses Continue. The script verifies entry and frame availability, not visual correctness. Remaining: real-Metal hook/frame review and V's independently assigned portrait-alpha investigation.
