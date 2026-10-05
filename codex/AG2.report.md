# AG2 — render scale through presentation

Implemented and built only in `port/build-ag`. No commits/pushes, dump changes, other build-directory writes, or cheat-overlay edits.

## Root causes

- The failed 2× capture was produced by **`rsx_metal_overlay.m`**, not `eng_dump_frame`: AG-host.EYtDTx/2x/run.log:14146 says `[sys overlay/metal] captured frame 1200 overlay=0`. The shared compositor always copied into 1280×720 textures, including its capture image. D2's actual Metal color target was already scaled; a native-size dump did not establish that its inactive-overlay screen presentation had lost supersampled detail.
- Display registration was conditional on an initialized engine. D2 registers buffer 0 before Metal initializes (old host log:140 vs :194), so the draw engine lost scanout metadata and fell back to the current target.
- RESC omitted conversion and declared the wrong ABI: it accepted only `index`, receiving D2's context address as the index (`src=260046848`). Correct signature is `(context, index)`, also confirmed in RPCS3's `rpcs3/Emu/Cell/Modules/cellResc.cpp`.
- NV3089/NV308A transfers updated guest memory/the legacy renderer but did not update Metal engine targets.

## Changes

- Retain display registrations before backend init; allocate scanout through the existing scaled color-target allocator when consumed.
- Queue RESC conversion in FIFO order before its normal flip marker. Track the submitted sequence before the walker counts it. The SDK's blocking WaitFlip publishes the context tail first, preventing a wait-before-flush deadlock.
- Add a backend transfer record using native rectangles. Convert source/destination edges once, including rounded 1.5× extents. Exact transfers use Metal blits; scaled transfers use the guest nearest/linear filter. Overlapping target transfers snapshot on GPU. D2's same-address RESC copy is a no-op.
- Route linear A8R8G8B8/X8R8G8B8 NV3089 copies and packet-sized NV308A color uploads into scaled targets. Transfers to ordinary guest textures first resolve the rendered source at native size and restore guest channel order. CPU readback stays native; presentation/capture retains the scaled texture.
- Shared system compositor buffers/captures match the guest texture dimensions; inactive captures read the scaled source directly. UI text coordinates remain native. AF's cheat files were untouched.

SDK files: `libs/video/{cellGcmSys.c,cellGcmSys.h,cellResc.c,cellResc.h,rsx_draw_engine.c,rsx_draw_engine.h,rsx_metal_backend.m,rsx_metal_overlay.m}`. AG2-only delta against the pre-task working tree: `patches/AG2-render-scale.diff`.

Checks: extended `codex/AG.metal-test.m`, updated `codex/AG.host-check.sh`, new `codex/AG2.engine-test.c` and `codex/AG2.fifo-test.c`.

## Verification

- `port/runs/AG2-build-final.log:7` — linked `DisgaeaD2Recomp`; configured with the OPERATIONS.md line, changing only the build directory.
- `AG2-engine-test.log:135` — existing engine checks passed. `:136–146` — early display registration, RESC destination selection, native rectangles, scaled partial transfers, same-address no-op, overlapping transfers, native RTT/channel order, and NV308A uploads passed.
- `AG2-fifo-test.log:12` — actual RESC HLE plus FIFO walker: context/index ABI, conversion before flip, WaitFlip blocks until retirement. Existing Q synchronization checks also passed (`:1–6`).
- Requested 40-second run: `AG2-final.log:270` correctly logs `src=0`; `:2290` reaches frame 1200. Exit **142**, expected alarm. No assertion/corruption crash. `:52/:83` explicitly show no Metal/software fallback; this is boot/FIFO verification, not GPU evidence.
- GPU harness compiles without warnings (`AG2-metal-build.log` empty). `AG2-metal-test.log:1` — **SKIP: no Metal device**, exit 77. Harness exercises actual transfers, presenter and shared compositor at 1×/1.5×/2×/3×, physical-pixel stripes, native readback, partial rectangles, native uploads and overlapping-copy resource lifetime.
- Shell/embedded Python syntax, relevant diff whitespace and SDK patch reverse-apply checks passed. Engine-test compiler warnings are existing FP-decompiler comment warnings.

## Remaining real-host verification

Run **`bash codex/AG.host-check.sh`** (optionally `AG_SKIP_BUILD=1`). It asserts GPU capture dimensions/detail, game frames **1280×720 at 1× / 2560×1440 at 2×**, and hallway throughput **≥58.5 distinct flips/s**. It saves matching settled hallway crops as `port/runs/AG-host.*/hallway-f<frame>-{1,2}x-crop.png`; 1× is enlarged with nearest sampling for an equal-size comparison. The existing live-scale/cap check remains.

**Actual new GPU frames/crops and maintained 2× hallway 60 fps remain unverified/unproduced here because this sandbox exposes no Metal device.** Existing native-size 2× captures cannot establish the fixed result; no synthetic images are presented as evidence.
