# AA — Castle Hallway RSX throughput

Recorded hallway drain time improved **8.274 → 4.882 ms/frame (41%)**. **The real-Metal ≥59.5 flips/s target remains unverified.** This sandbox returns `[RSX metal] no Metal device available`; the GPU-free draw-engine run still misses the target at 49.161 flips/s.

## Findings and changes

- The drain decoded 3D registers twice through the legacy processor and register-file engine. Engine-only mode now avoids redundant legacy decoding, while retaining fence/label effects and diagnostic fallback.
- Vertex conversion repeatedly entered per-element readers/decoders. Added attribute-major bulk fetch with arm64 NEON BE conversion for float4, half, u8 and s16 layouts; scalar/fallback paths preserve other formats and mapping checks.
- Added a bounded converted-vertex cache (32 MiB, 1024 entries). Keys include the complete fetch plan and references; **every hit compares all source bytes**, including interleaved spans. Misses decode the validated snapshot. Vertex-program input analysis/hash also reuses results after full code comparison.
- Metal now admits repeated identical converted vertices to immutable MTLBuffers, retaining buffers through recorded draws. Added redundant state/texture/sampler bind suppression within each encoder. These changes compile but need GPU validation.
- All committed coherent PPU stores now notify relevant put/label ranges; the watcher remains available for HLE/DMA writes. Drain slices publish real get and self-kick after approximately 1 ms between complete packets. Ring recycling retains both tail and jump acknowledgments; no speculative consumption past guest put.
- Release reads skip diagnostic watch calls/TLS bookkeeping behind cached gates. POSIX frame waits use the existing waitable timer instead of rounding the phase deadline to milliseconds. Standalone timer tests still show OS scheduling lateness; this is not a measured precision guarantee.

Ordinary non-full puts already support concurrent consumption; tests do not support a claim that the consumer waits for ring-full/vblank. The final separate-consumer test measured **3.690 µs mean / 34 µs max** put-to-drain/get publication (`AA.AA-sync-test.log:10`). Unflushed guest words cannot safely be consumed.

## Measurements

| Path | Result | Evidence |
|---|---:|---|
| Actual GCM walker + engine replay, pre-AA | 8.274 ms/frame | `AA.live-replay-comparison.log:118` |
| Same replay, final | 4.882 ms/frame | `AA.live-replay-comparison.log:142` |
| Second matched replay | 8.377 → 4.954 ms/frame | `AA.live-metal-replay.log:118,142` |
| Prescribed 40-second headless/FIFO-only hallway run | 59.999 flips/s; 399 flips / 399 vblanks | `AA.prescribed-check.log:1` |
| Headless FIFO-only recycle | mean 0.575 ms; p95 0.691 ms | `AA.prescribed-check.log:7` |
| GPU-free draw-engine hallway | 49.161 flips/s; mean recycle 0.809 ms | `AA.engine-final-check.log:5,11` |
| Metal-null | unavailable; exit 2, no GPU result | `AA.metal-null-final.log:1–2` |

Capture: `port/runs/AA-host.eeTuah/hallway.fifo`, four settled map30001 frames, **836 draws/frame**. Each timed replay processes 400 frames, 334400 draws and 15521200 raw packets. Both warmups produce checksum `9257d6f1afd5e328`, with zero missing reads. Replay uses the actual `cellGcm_rsx_process_fifo`, including packet parsing, transfers and engine work. Jump/call control flow is flattened into consumed packets; guest-memory restoration, scheduling waits and vblank pacing are excluded. This is a throughput benchmark, not an FPS prediction.

## Verification and files

Release build passes in **port/build-aa**, configured exactly as OPERATIONS.md. Q/T/Y/AA sync checks pass (6/11/9/11), including ring tail/jump ordering, flip boundaries, semaphore wake and non-full put consumption. Fixed Q's fixture to clear stale kick events before its recycle test; five repeats passed. Draw suite: 81 checks. X hash suite: 67080 byte mutations. Vertex differential/guard-page suite: 17024 comparisons across all seven formats; vertex/cache tests pass ASan/UBSan. Synthetic bulk conversion: 25.972 → 16.458 ms (1.58×). SDK diff whitespace and isolated patch reverse-apply checks pass.

SDK files changed: `libs/video/{cellGcmSys.c,rsx_draw_engine.c,rsx_draw_engine.h,rsx_vertex_compact.c,rsx_vertex_compact.h,rsx_metal_backend.m}` and `runtime/ppu/ppu_loader.cpp`. AA-only SDK patch: `patches/AA-runtime.diff`. Added AA host/replay scripts, replay drain adapter and vertex/cache/sync tests; updated `.gitignore` allowlist and `codex/Q.sync-test.c`. Existing concurrent-worker changes were retained. No game-dump edits, other build-dir edits, commits or pushes.

## Host follow-up

Run `bash codex/AA.host-check.sh` on the real Mac. It reuses Y's route, copies the save, measures 60 seconds, then takes an eight-second `sample`; it reports distinct flips/recycle stats and fails below 59.5 flips/s. Logs and profile remain under `port/runs/AA-host.*`.

For a new recording: `AA_RECORD=1 bash codex/AA.host-check.sh`. Replay with `bash codex/AA.replay-check.sh <hallway.fifo> --metal-null`. Pre-AA CPU sources are retained in `port/build-aa/baseline`; captures are SDK-ABI-specific. Cache fallbacks: `RSX_VERTEX_CACHE_OFF=1`, `RSX_METAL_VERTEX_CACHE_OFF=1`; full legacy diagnostics: `GCM_LEGACY_STATE=1`.

Remaining: real GPU correctness/throughput, the ≥59.5 target, and the post-measurement host profile. Residual draw-engine deadline misses mean the replay improvement alone does not establish 60 FPS. `agent-usage`: Codex 66% remaining at 08:39 CT.
