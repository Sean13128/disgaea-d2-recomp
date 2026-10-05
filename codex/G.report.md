# G — post-loading black frames

**Fixed a shared address-resolution bug that turned MAIN-memory vertices into empty VRAM reads. GPU-free captures now contain valid late-scene geometry. Real Metal verification remains pending.**

## Root cause

`cellGcmResolveLocated(MAIN, offset)` called the ambiguous `cellGcmResolveOffset`, whose LOCAL-page heuristic overrides the IO table. D2's vertex ring uses MAIN IO offsets `01340000…`, mapped to `41440000…`. Once loading allocated VRAM on the same offset page, MAIN vertices incorrectly resolved to `C1340000…`.

- Original real-Metal capture: `F-metal.3NNE/run.log:7955–7967` (frame 420) and `:10902–10914` (frame 600) show zero positions/colors. This produces degenerate triangles before Metal rasterization.
- Reproduced in `G.trace.log:7356`: `loc=1 off=01340000 resolved=C1340000 io=41440000`. Here `loc=1` is the RSX MAIN enum; the resolver's boolean uses the opposite sense.
- Fix: explicit MAIN now resolves through `cellGcmResolveIO`; explicit LOCAL still resolves directly into VRAM. Unmapped MAIN returns invalid rather than guessing VRAM. The ambiguous legacy API is unchanged.

The captured textures are populated linear B8 indices and A8R8G8B8 palettes, not DXT/swizzled data. Draws and presentation use the same surface (handle 1). Depth/stencil clears are present, full viewport/scissor and color mask are correct, and the fragment programs sample textures/palettes then multiply by vertex color. Corrected frame 1200 has full-screen positions, color/alpha `0.501961`, multiplier `1.99219`, and NOTEQUAL-zero alpha test. No observed NV3089 copy or cellResc conversion explains these collapsed inputs. No speculative Metal/shader changes were needed.

## Files changed

- SDK: `ps3recomp/libs/video/cellGcmSys.c` (one functional line plus explanation). G-only patch: `patches/G-rendering.diff`.
- Port: `port/src/d2_draw_trace.cpp` adds `D2_DRAW_TRACE_MAX_FRAME`; default remains 600, zero captures throughout a run.
- Checks: `codex/G.validate.cpp`, `G.validate.py`, `G.metal-check.sh`. Replaced both `rg` uses in `F.metal-check.sh` with `grep`.

Temporary SDK vertex tracing was removed. Only `port/build-g` was configured/built. Game dump and other workers' build directories were untouched; no commits/pushes. Own disposable caches were removed; corrected raw draws retained in `port/runs/G-fixed-draws/`.

## Verification

- `G.final-build.log`: successful final native link.
- `G.test-final.log:2`: **PASS** for overlapping MAIN/LOCAL offset pages, vertex fetch from each memory space, and rejection of unmapped MAIN. The fixture uses the actual runtime IO map and resolver, not a mocked resolver.
- Two fresh-HDD1, 40-second runs: baseline reproduces bad addresses; corrected `G.fixed-trace.log:33746–33783` shows MAIN addresses and full-screen textured geometry at frame 1200. `:56329–56360` confirms correct addresses/nonzero textured geometry at frame 1860; `:57746` presents 28 draws.
- Shell syntax, pixel-summary fixture (`G.script-test.log`), and SDK whitespace checks pass. Prior art read through `gh`: PR #160, Twisted Metal first-pixels findings, Shadow of the Colossus README.

## Claude's real-Metal check

Run `bash codex/G.metal-check.sh` outside the sandbox. It builds only build-g, runs **90 seconds**, creates a fresh HDD1 under `/Volumes/Data/ai-tmp/claude/d2`, uses **grep**, contains **no rm**, and retains numbered frame dumps every **60 frames**, shaders and late draw buffers in `port/runs/G-metal.XXXX/`. `G_HEADLESS=1` optionally tests real Metal without a window.

Look for recognizable artwork and nonblack pixels after frame 360, especially around/after frame 1920; early fades and the black background draw are legitimate. Check `pixels.txt`, `summary.txt`, `draw-summary.txt`, and late `[F-vertex]` entries in `run.log`. Textured draws should have real quad positions and nonzero colors. Inspect any `command buffer failed`/validation errors. Capture retains the existing `[F-*]` tags.

This sandbox still reports **no Metal device** (`G.fixed-trace.log:92`), so restored GPU pixels/title-screen visibility cannot yet be claimed. If late frames remain black with valid vertices, use the newly extended late captures to isolate the next issue.
