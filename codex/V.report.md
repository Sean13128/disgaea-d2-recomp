# V — battle HUD portrait transparency

Fixed the generic SDK stencil reset state. Real-Metal visual confirmation remains pending.

## Root cause and evidence

The white rectangle is the portrait's backing quad, clipped with stencil rather than texture alpha alone. NV40 front/back stencil write masks (`032C`, `034C`) reset to `FF`; the SDK's zero-initialized register file left both at `00`. D2 never overrides these masks. This suppressed the clip pass's stencil writes.

Baseline `port/runs/V-stencil.log`:
- Line 77491: `front=00/FF/FF back=00/FF/FF` (write mask / reference / read mask).
- Lines 77494–77512: frame 2170, draw 314 covers exactly `(40,28)..(212,200)`, matching the user's white rectangle. Depth is NEVER (`0200`), stencil ALWAYS (`0207`), REPLACE (`1E01`), reference 255. The inverse-circle texture has zero alpha inside and nonzero alpha outside; NOTEQUAL-zero alpha test discards the inside. The surviving outside pixels should write stencil 255 without drawing color.
- Lines 77514–77536: backing and portrait draws use stencil GREATER (`0204`), reference 1, KEEP. They should pass only inside, where `1 > 0`, and fail outside, where `1 > 255` is false. With the broken write mask, stencil remains zero everywhere and the backing becomes a white rectangle.

The decoded mask is linear A8R8G8B8 (`A5`), identity remap `AAE4`, 256×256, with 50,464 nonzero-alpha pixels. Palette/sprite decoding is populated, blend factors are ordinary SRC_ALPHA / ONE_MINUS_SRC_ALPHA, alpha reference is zero, and the sequence uses the display surface directly. No offscreen target, unusual alpha format, or missing blend factor explains this draw. Front/back stencil values match in D2's captured sequence.

Reset-value reference: RPCS3's [RSX register reset image](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/RSX/rsx_methods.cpp) seeds both stencil write masks to `0xFF`; [method enums](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/RSX/gcm_enums.h) identify the registers. Read PR #160 and the supplied reference ports through `gh` before implementing.

## Changes

- `ps3recomp/libs/video/rsx_dispatch.c`: seed both stencil write-mask registers to `FF`. Explicit guest writes of zero still disable writes.
- `ps3recomp/libs/video/tests/test_rsx_draw_engine.c`: regression checks for reset masks, explicit zeros, the depth-fail REPLACE pass, and pipeline changes when writes are disabled.
- `port/src/d2_draw_trace.cpp`: opt-in texture limits, capture interval/start and first-use pipeline capture; log alpha/separate blend, stencil and surface state. Ordinary runs are unaffected. Temporary SDK tracing was removed.
- `codex/V.host-check.sh`, `.gitignore`: real-Metal check using only build-v, private saves/cache, retained frame/draw captures, `grep`, no `rm`.
- `patches/V-stencil-reset.diff`: V-only SDK fix and regression tests, excluding other workers' changes.

## Verification

- Final native build passed: `port/runs/V.build-final.log:8`, successful link of `DisgaeaD2Recomp`.
- Actual draw-engine test suite: `port/runs/V.engine-test.log:77–80` four stencil checks PASS; line 134 `all checks passed`. Compiling the same suite with only the new reset assignments removed produces three expected failures (`V.engine-before.log:74–77`). Existing texture-layout tests also passed (`V.texture-test.log`).
- Two 40-second headless battle runs reached the portrait via U's stage warp and ended with the expected alarm status 142. Corrected `V-fixed.log:82295–82320` now has `front=FF/FF/FF back=FF/FF/FF`, the exact mask quad, and GREATER backing draws with `masks=FF/FF`. This verifies the actual guest path and corrected backend inputs, not GPU pixels.
- Shell syntax and targeted diff whitespace checks passed. Only build-v was configured/built; no dump edits, commits or pushes.

## Host check / remaining

Run `bash codex/V.host-check.sh`. Choose Continue, load the copied save, then U's warp enters the first battle. Press Triangle twice to skip the dialogue, deploy Laharl, move next to an enemy, and queue an Attack. The map should show through the rectangular corners around ATTACK ENTRY; other HUD elements should remain correct. Captures and filtered summaries are retained in the printed `port/runs/V-host.*` directory. The script checks that real Metal and the portrait's `FF` stencil mask were captured, but cannot decide visual correctness automatically.

Metal reports no device in this sandbox (`V-stencil.log:96`), so Claude/user must confirm the final appearance on real Metal. Baseline/corrected raw inputs remain in `V-stencil-draws` and `V-fixed-draws`; redundant V captures and disposable scratch were removed.
