# Q — GCM FIFO drain latency

Q’s implementation was already present when this assignment arrived; this pass audited it, rebuilt it, reran synchronization checks, and measured the current binary. No additional runtime edits were needed.

Root causes: the frame clock drained on fixed 4/16 ms cadences despite an existing kick event; ring recycling slept twice per wrap; WaitFlip polled and fabricated completion after a timeout. RESC also completed flips/handlers prematurely.

Implementation files:
- `ps3recomp/libs/video/cellGcmSys.c/.h`: drain kicks, generation-based completion conditions, atomic flip state, get/ref/label notifications, and real semaphore-acquire dependencies. A put/label watcher bridges O’s existing notified memory wait API, with its bounded 100 µs fallback. Fence visibility ordering remains preserved.
- `ps3recomp/libs/video/cellResc.c`: waits for its submitted flip sequence; callbacks occur on completion.
- `port/main.cpp`, `ps3recomp/templates/project/main.cpp`: drain immediately on kicks; present at 60 Hz before further draining; publish completion after presentation. Missed refreshes are skipped rather than presented in bursts.
- `patches/Q-fifo.diff`, `codex/Q.host-check.sh`, `codex/Q.sync-test.c`, `codex/Q.sync-check.sh`: patch export, host measurement script, and synchronization regressions.

Verification:
- Prescribed Release configure/build in `port/build-q` passed (`codex/Q.current-configure.log`, `codex/Q.current-build.log`). Patch reverse-apply check and shell syntax check passed.
- All six regressions passed (`codex/Q.sync-test.log`): presentation gating, independent RESC sequence completion, lost wakes, both ring acknowledgments, ordered fence visibility, committed put wake, and CPU label release without another put write.
- Current 40-second headless FIFO-only run ended normally by alarm (142), without recycle-stall warnings. `port/runs/Q-current.log:2530,3666` records 1109→2010 guest presentations over approximately 15 s; lines 2573/2952/3331/3711 report 59.99/60.00/60.01/60.03 flips/s. Lines 2559/2937/3316/3695 report approximately 92% process CPU. Lines 36–39 confirm Metal unavailable and software drawing disabled.

Existing before/after measurements retained from the original Q work:

| Headless mode | Before | After |
|---|---:|---:|
| Title, FIFO timing only | 34.48 flips/s | 60.08 flips/s |
| Loaded map, FIFO timing only | 27.68 flips/s | 59.88 flips/s |
| Title, software drawing | 30.8 frames/s | 57.8 frames/s |

Map evidence: `port/runs/Q-logic-baseline-newgame.log:5046,6055` records 2838→3530 presentations/25 s; `Q-logic-final-newgame.log:7856,9775` records 5306→6803/25 s. Both loaded `MAP/mp300/map30003.lzs` from the existing save; they do not verify fresh New Game/story. Drawing-enabled evidence is in `Q-verified.log:1961,3060`. Software map drawing remained CPU-bound near 12 fps.

Remaining: visible real-Metal speed, fresh New Game/story progression, and audio need host validation. Run `bash codex/Q.host-check.sh`: 120 s at title plus 120 s with `75:0x0010,78:0x4000` then Cross every 4 s, `D2_MOVIE_SKIP=1`, ps CPU samples, guest frames/flips per second, and an 8-second process sample per scene. It clears inherited headless/FIFO-only settings and flags Metal failure or accidental Continue selection. Timing-only throughput does not prove visible game-logic speed.

Reviewed Twisted Metal’s runner and ps3recomp PR #160 as prior art. No commits/pushes; game dump, other build directories, O’s files, codec files, and overlay files were not edited.
