
# Task AY — heat fixes 3+4: multi-wait fan-out + FIOS QoS (yourname = AY, build dir port/build-ay)

Read codex/AV.report.md (findings 3 and 4, recommended order steps 3-4), codex/AW.report.md, codex/AX.report.md. AW + AX are applied in the shared SDK tree; keep them. Real Metal + CoreAudio hub after AW+AX (port/runs/AX-host.PlA9Sj): CPU 42%, csw 25k/s, idlew 1.16k/s, 60 fps (original baseline 57% / 96k / 14.4k).

## Part 1 — multi-wait fan-out (runtime/platform/win32_compat.c ~170)
1. First add counters (PS3_MULTIWAIT_STATS=1, ~10 s summaries): object-change broadcasts, multi-waiter wakes, and how many of those wakes found a signaled object of interest vs went back to sleep (useless), per waiting thread name if cheap. Measure headless hub with AW+AX.
2. If useless wakes are material (say >1k/s or a visible share of csw), route notifications only to multi-waiters subscribed to the changed object (registration + state checks under s_lock), preserving kick events, waitable-timer rearm, auto-reset semantics, wait-all, timeouts and close/lifetime. Env PS3_MULTIWAIT_BROADCAST=1 restores the old global broadcast. If not material, make no behaviour change and say so.
3. Tests in the existing compat test suite: unrelated semaphore storm causes no false progress/wakes; real kick wakes; timer rearm; auto-reset; wait-all; timeout; close while waiting.

## Part 2 — FIOS thread QoS
Every guest PPU thread gets QOS_CLASS_USER_INTERACTIVE (runtime/syscalls/sys_ppu_thread.c:114 -> guest_poll.c ps3_poll_thread_start). Add a weak SDK hook for a per-thread QoS role (default = current behaviour) and in the port (port/stubs.cpp or a port/src/d2_*.cpp) opt FIOS threads ("fios mediathread*", "fios scheduler*") to QOS_CLASS_DEFAULT. Keep PPU main, RSX, audio/mixer/synth2/NisAt3Line at current QoS. Env PS3_D2_FIOS_QOS=interactive restores. No other demotions.

## Verify
- Full ctest in build-ay passes.
- Headless hub/battle/title routes as in codex/AX.headless-check.sh: no faults, music streams, no ATRAC stalls.
- Write codex/AY.host-check.sh modelled on codex/AX.host-check.sh (real Metal, AY_AUDIO=1 = real CoreAudio). Runs, same binary port/build-ay unless stated: (1) port/build-ax binary (AW+AX), (2) AY with PS3_MULTIWAIT_BROADCAST=1 PS3_D2_FIOS_QOS=interactive (should match 1), (3) AY fan-out only (PS3_D2_FIOS_QOS=interactive), (4) AY full. Report CPU, csw/s, idlew/s, flips/s, worst interval, multiwait stats per run.
- Export only your SDK changes to patches/AY-runtime.diff. Do not commit.

Report: counter findings (was fan-out material?), changes, tests, headless results.
