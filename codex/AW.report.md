# AW — bounded graphics poll backoff

Root cause: seven idle graphics workers repeatedly timed out after 100 us even when guest bytes stayed unchanged. Notification coverage is incomplete, so removing the timeout would risk missed work. Graphics polls now use TLS EA/size/snapshot state and 100 → 200 → 400 → 800 → 1000 us, growing only after ETIMEDOUT with unchanged bytes. Value/sequence changes reset it; bucket broadcasts do not. PS3_POLL_IDLE_CAP_US accepts 100..1000 (default 1000). PS3_POLL_STATS=1 prints per-thread name/host ID, timeout/notification counts, interval, current delay and cap approximately every 10 seconds.

Scope: explicit idle-graphics variant in mfc_poll and RSX PUT watcher. A weak SDK image-role hook defaults off; port/stubs.cpp opts in NisGraphics image 2 (both game versions), leaving synth2 image 1 short. PPU hot-read polls, cellSync, GCM label/equality waits including watcher label fallback, and audio all retain 100 us. Labels can represent transient values; audio has a small block deadline. Registration/recheck, DMA/caller rereads, cross-line yield fallback and PS3_POLL_BACKOFF=0 remain. Added unregister/unlock cleanup and a post-wait cancellation point (Darwin relative waits can defer cancellation).

Changed: SDK runtime/platform/guest_poll.{c,h}, runtime/platform/tests/test_guest_poll{,_filter}.c, runtime/spu/spu_dma.h, libs/video/cellGcmSys.c; port/stubs.cpp; codex/AW.host-check.sh; patches/AW-runtime.diff. Unrelated concurrent audio/overlay/Operations edits were excluded from the exported SDK diff. No commit/push, dump edits or other build-directory writes.

Verification: build-aw configured with the documented Release/Ninja/Homebrew flags, recomp-140, and the same .venv Python as port/build. Full CTest: 47 passed, 4 Metal-dependent skips, 0 failures (port/runs/AW-ctest.log, 20.23 s). LastTest.log lines 6099–6101: notified publication 0.017 ms with a deliberately enlarged 20 ms diagnostic wait; timeout ladder, reset, collision/spurious, cross-line and cancellation assertions PASS. Lines 6171–6172: 40 notified/unnotified production-cap publications within 1 ms + 5 ms host tolerance and 10,000 registration races PASS. Sanitized standalone SPU tests in build-aw/aw-spu-tests: PPU coherence 68/0, peer coherence/DMA PUT 51/0, MFC slots 817/0; generated existing DMA GET round-trip reads DEADBEEF through LS and mailbox.

Controlled measurements: `port/runs/AW-host.bhxpXX/{baseline,adaptive,cap100}/`, 90 s each, same v140 ELF/save/pad route, dummy audio/movie skip, fresh scratch HDD0/HDD1. All loaded the requested save and map30003; all exited at the expected alarm (142). No parallel builds/tests in these measurement runs. CPU is the runtime's existing getrusage self-accounting (last six ~5 s intervals), flips the final 30 s, poll rates the last three per-thread summaries (~30 s). `AW-metrics.json` holds raw derived rates.

| Headless result | Frozen baseline | Adaptive 1 ms | Same binary, cap 100 us |
|---|---:|---:|---:|
| CPU, % of one core | 125.45 | 113.53 | 125.02 |
| 7 graphics timeout returns/s | unavailable (uninstrumented) | 6,115 | 54,571 |
| 7 graphics notified returns/s | unavailable | 591 | 597 |
| Distinct flips/s | 12.000 | 12.000 | 12.000 |
| Worst flip interval, ms | 83.411 | 83.500 | 83.408 |
| csw/s / idlew/s | sandbox blocked | sandbox blocked | sandbox blocked |

The controlled timeout reduction is **88.8%**; total graphics wait returns fell ~87.8%, while notified-return rate stayed close. CPU fell 11.92 percentage points (~9.5%) versus frozen baseline, or 11.49 points versus same-binary cap100. PPU main still reports cap=100 and ~4,456 versus ~4,437 timeouts/s; audio mixer cap=100. These counts are poll returns, **not** interrupt wakeups or context switches.

Evidence: adaptive/game.log:13278–13328 shows graphics cap=1000 (e.g. RSX submit interval=10.110s, timeouts=9036, notified=4511); cap100/game.log:13463 shows PPU main cap=100, interval=10.022s, timeouts=44638, notified=1186. Save-load line numbers are in AW-metrics.json. No FAULT/HOST CORRUPTION/SIGNAL lines in any final game log. `aw-spu-tests/poll-env.log` independently verifies cap100 and PS3_POLL_BACKOFF=0 (no wait registrations).

`top` cannot execute in this sandbox (Operation not permitted); csw/s and idlew/s require the provided real-host script. The supplied older real-Metal top3 baseline parses correctly with the script (57.95% CPU, 100,074.8 csw/s, 12,277.5 idlew/s); it is not a controlled after-comparison. Metal has no device here; headless uses the software renderer, so 12 flips/s does not validate real Metal 60 Hz pacing. Scratch save copies were removed.

Remaining: run `bash codex/AW.host-check.sh` outside the sandbox (optionally AW_CONTROL=1 for the 100 us same-binary control). Script compares retained baseline vs build-aw for 90 s each, samples top after 45 s, derives cumulative csw/idlew deltas over timestamps, and reports distinct retire-sequence flip rate/worst interval. Each run uses a fresh scratch HDD0/HDD1; scratch copies are removed on exit. Real Metal hub/hallway/battle/movie-fence latency and real audio/power checks remain before integration.
