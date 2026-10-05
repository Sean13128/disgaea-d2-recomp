# AI — battle lifetime crash and Metal harness

## Root causes

**Battle crash: a hub announcement sprite retains a freed animation pack.** This is a confirmed unsafe debug-warp transition, not evidence of a negative-index/sign-extension bug. The valid expanded animation at `45735280` is ID `232C` (9004). Its owning sprite was created by `00034100 → 001C5E44 → 001C7F5C → 001CB5A0` in the hub (`AI.owner4.log:1930`). Battle initialization frees the hub pack through `002E5898 → 000509C0 → 0021E320 → 002222DC` (`AI.free.log:2868`). The allocator fills it with `CC`; signed frame index `CCCC` is **−13108**. Its products explain the exact failures: `−13108*18+12 = FFFC6664`, `−13108*20 = FFFBFFF0`, `−13108*16 = FFFCCCC0`.

Inspected `func_002EF390` in `port/src/recomp-140/ppu_recomp_016.cpp:37231`: it is the downstream animation vertex/interpolation reader. Its NULL/1004 accesses follow the poisoned animation data; replacing its return value or masking guest addresses would hide the lifetime error. Opening the selector scene, clearing selector flags, and resetting hub/unit entities individually did not fix the crash. A standalone comparison of lifted `00335FE4` memcpy against native memcpy passed 262,144 non-overlapping length/alignment cases (`AI.memcpy-test.log:1`); no generic lifter/runtime change is justified by these findings.

**Metal abort: the test merges private globals from two translation units.** `AG.metal-test.m` includes both backend and overlay `.m` files. Their matching tentative `static` declarations (`s_queue`, `s_layer`, `s_inflight`) become the same variables. After four successful RESC passes, `rsx_metal_overlay_shutdown()` sets the backend queue to nil. The subsequent partial-copy test encodes nothing and reads transparent pixels, explaining `AH-metal.SZBZfm/metal-test.log:17–18`. Production builds separate these sources. AH's earlier different-size clear-batching fix remains necessary and unchanged; the pixel expectations remain intact.

## Changes

- `port/src/d2_debug_warp.cpp`: on 1.40, require the native hub scene and no active event. Request native message destruction (`00033CBC`, also called by hub interaction at `001C4C20`), return to the guest loop, and wait for `00033C48` to report all message queues empty before starting event 11. 1.00 message entry points mapped to `00033D6C` / `00033CF8`. Announcements may require more Cross presses/time; pending messages safely defer the warp.
- `codex/AG.metal-test.m`: namespace all three overlay globals around the include; assert overlay shutdown preserves the backend queue.
- `codex/AI.host-check.sh`: own version-140 build, private saves/cache/settings, PAD_FILE Continue/load → warp → Cross every ~0.5 seconds for 120 seconds. Requires at least 80 battle Cross presses, continued late flips, expected timeout, map 101, and no OOB/post-load null reads/Bus error. Rebuilds/runs AG2 Metal and AH overlay harnesses, retains real-Metal frames every 600 flips. Uses grep, no rm. `.gitignore` whitelists it.
- This report. Temporary SDK tracing was removed; no lasting AI SDK edits, dump edits, commits, pushes, or writes to other build directories.

## Verification

All logs below are under `port/runs/`.

- `AI.final-build.log`: version-140 runner built in `build-ai`; shell and embedded Python driver syntax pass.
- Final **120-second pure-Cross headless run**, expected alarm exit 142: `AI-host.rAaqm8/run.log:1726` slot 01 LOAD; `:2269` native message drain; `:3648` battle 101 confirmation; `:9032` frame **7020**. `driver.log:201`: **146 battle Cross presses**, late flips **6300..6960**, PASS. No OOB, post-load null read, Bus error, or runtime fault. Earlier identical 120-second run also passed (`AI-host.MDJe9r`); that earlier run additionally had one manual Triangle press.
- One pre-existing bootstrap NULL+4 read by `00010354` remains at final `run.log:18`, before CRT/save loading. The host check explicitly checks every post-load null read and all OOB faults; it does not silently waive a battle null read.
- `AI.engine-test.log:135–146`: original draw-engine suite and AG2 RESC/transfer/conversion checks pass. Final `AI-host.rAaqm8/overlay-test.log:1–2`: AH opaque panel and CoreText raster checks pass.
- GPU/overlay harness compilation passes. GPU execution returns **77 / SKIP: no Metal device** in this sandbox, so real-Metal pixel correctness is not claimed.

## Remaining / real Mac

Run `bash codex/AI.host-check.sh` (or `AI_SKIP_BUILD=1 bash codex/AI.host-check.sh` after building). Default mode requires real Metal and both GPU harnesses to pass. `AI_HEADLESS=1` is explicitly a guest-execution-only check and labels GPU verification skipped.

**Normal Dimension Guide navigation on 1.40 was not reproduced here.** The trace proves that the old warp starts a battle with live hub sprites, and the corrected precondition eliminates the reproduced crash. It does not prove this fault can never occur through normal navigation. Keep that exclusivity claim open until a real-Mac normal-selector run reaches deployment; do not add a speculative generic HLE/lifter fix. Existing operations record a human entering battle normally, but that is not equivalent to this slot-01/1.40 repeated-Cross regression.

The 40-second legacy warp checks can now end before battle because the debug hook waits for all native announcement queues to clear. Use the 120-second AI check for this regression. Only version 140 was built/run; mapped 1.00 message calls were inspected, not executed. Private host-check scratch/evidence is retained for review. Own tracing scratch was removed.
