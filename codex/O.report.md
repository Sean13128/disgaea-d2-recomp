# Task O — CPU efficiency

Generic SDK backoff reduces headless process CPU **684.4% → 116.5%** (83% reduction). Completed-frame throughput improves **13.88 → 20.88 fps** in the same 40-second boot/input sequence. **60 fps gameplay and audible crackle resolution remain unverified on real Metal/CoreAudio.**

Root causes: six idle NisGraphics SPUs repeatedly DMA-read unchanged command descriptors; PPU HOTREAD detection only logged spinning. Width-specific HOTREAD64 also misidentifies repeated return-address stack reads as waits, so scheduling uses a shared unchanged-read sequence across widths and resets on intervening stores. The POSIX SPU coherence lock additionally used an unrestricted atomic-exchange spin loop.

Files changed (SDK paths are under `ps3recomp/`):
- `runtime/platform/guest_poll.{c,h}`: spin/yield, then cache-line notification waits bounded to 100 µs. Register/check under the notification lock prevents missed wakeups; uninstrumented HLE writes remain covered by timed rechecks. `PS3_POLL_BACKOFF=0` disables backoff/QoS; `PS3_HOST_CPU=1` enables interval process and named per-thread CPU measurements.
- `runtime/spu/spu_dma.h`, `runtime/spu/spu_coherency.c`: private unchanged-GET snapshots, PPU/SPU write notifications, existing coherent DMA transfers retained. POSIX coherence locking now follows the existing Windows test-and-test-and-set pattern, with CPU relax and periodic scheduler yields. Guest reservation/event behavior is unchanged.
- `runtime/ppu/ppu_loader.cpp`, `runtime/syscalls/{sys_ppu_thread.c,lv2_register.c}`, `libs/sync/cellSync.c`: PPU read backoff, successful store/unlock notifications, guest thread names/QoS. PPU and synth2 threads use interactive QoS; graphics SPUs use default QoS.
- `runtime/platform/tests/test_guest_poll.c`: bounded waits and concurrent notified/unnotified writes.
- `port/main.cpp`: only O’s two-line addition naming/prioritizing the render thread through the SDK helper. Subsequent frame-pacing edits belong to another worker.
- `codex/O.host-check.sh`: 120s title plus 120s New Game; prescribed Up/Cross sequence, then Cross every 3s. Saves CPU, `ps -M`, frames/s and audio metrics; uses grep and no rm. Defaults `D2_MOVIE_SKIP=1` to avoid measuring movie playback; override with `D2_MOVIE_SKIP=0`.

Audit: macOS short timer sleeps already use nanosleep; lwmutex blocks on a host semaphore. Event queue receive timeout=0 means **infinite blocking**, not a nonblocking poll. Windowed Metal already limits in-flight frames with a completion semaphore; `waitUntilCompleted` is restricted to synchronization/readback. These paths required no O edits.

Verification: poll tests PASS; SPU peer coherence **51 passed / 0 failed**; PPU-to-SPU coherence **68 passed / 0 failed** (`codex/O.current-{poll,coherence,ppu-coherence}.log`). SDK and runner patches pass reverse-apply validation (`patches/O-runtime.diff`, `patches/O-runner.diff`). Host script passes `bash -n`. Read PR #160 and Twisted Metal’s SDK patch via `gh`.

Two sequential 40s headless runs, means over intervals ending at 10–35s:

| Metric | Backoff disabled | Final O enabled |
|---|---:|---:|
| Process CPU | 684.4% | 116.5% |
| Each graphics SPU, final sample | 88.5–90.5% | 3.4–3.5% |
| Completed frames, ~10–35s | 270 → 617 | 276 → 798 |
| Completed frames/s | 13.88 | 20.88 |

Evidence: `port/runs/O-current-baseline.log:1664` process 659.7%, `:1667–1672` SPU threads, `:1680` frames 617. `port/runs/O-final.log:1851` process 105.1%, `:1854–1859` SPUs, `:1866` frames 798, `:1895` audio **187.5 blocks/s**, non-silent mixed output. Both ended by alarm (142), with no SPU fault or host corruption. Metal is unavailable (`O-final.log:35`), so these are software-rendered boot/logo/title sequences; scripted input delivery does not prove visual map progression or audible output.

Build status: build-o configured with the OPERATIONS flags and built before concurrent overlay edits. Final O objects were compiled/linked using that build’s recorded Release commands (`codex/O.isolated-link.log`). A fresh full CMake rebuild currently hits another worker’s not-yet-created `libs/video/rsx_metal_overlay.m` (`codex/O.final-build.log`). O’s measured binary precedes the subsequent shared frame-pacing changes.

Remaining: after overlay/pacing integration completes, run `bash codex/O.host-check.sh` on the real host, then repeat with `PS3_POLL_BACKOFF=0` for comparison. Verify actual title/map speed, 60 fps and crackle; the headless results meet the CPU target but cannot establish those outcomes.
