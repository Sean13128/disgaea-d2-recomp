
# Task AZ — heat round 2: the remaining ~12k wakeups/s (yourname = AZ, build dir port/build-az)

Read codex/AV.report.md, AW/AX/AY reports. AW+AX+AY are committed (SDK d2-macos ee70875, project 3414a79). Real Metal hub now: CPU package 2.41 W (was 4.27), game ~12.2k interrupt wakeups/s (was 71.9k), csw ~21.5k/s, 60 fps. Remaining wakeup sources (real Metal hub, port/runs/AY-host.QQ66sB/full/game.log + PS3_POLLTOP data in codex/AV.report.md):
- graphics idle polls at the 1 ms cap: 6 NisGraphicsSpu ~800-950 timeouts/s each + RSX submit ~1.3k/s  => ~6k/s (largest)
- guest PPU main usleep(30 us) at lr 0x002FC970: ~2,000/s
- guest NisAt3Line usleep(1 ms) at lr 0x00161438 (~1,850/s total, 3 threads) and 5 ms at 0x0015F890
- host cellAudio clock loop polling with 1 ms / 200 us sleeps (libs/audio/cellAudio.c ~605-614) + SDL room polling (audio_backend_wait ~258)

## Part 1 — graphics poll: self-tuning cap (SDK)
Measure first (PS3_POLL_STATS): for the idle-graphics role, count value changes discovered by a TIMEOUT recheck vs by a notified wake. If timeouts essentially never discover changes at these sites, extend the idle-graphics ladder beyond 1 ms (e.g. up to 8 ms) BUT make it self-protecting: whenever a timeout recheck discovers a changed value (= a missed notification), drop that thread's cap back to 100 us for a cooldown period and count it. Keep PS3_POLL_IDLE_CAP_US override (allow up to the new max). Also look at why RSX submit (gcm_put_watch) timeouts stay high: AV noted PUT kicks are already notified by lifted stores (ppu_loader.cpp ~1509-1532); if the watcher is a pure fallback, apply the same self-tuning. Tests: missed-notify path falls back to short cap; notified path unaffected.

## Part 2 — host audio clock (SDK)
Make the cellAudio mix thread sleep until its deadline precisely (one absolute wait, e.g. mach_wait_until / clock_nanosleep TIMER_ABSTIME equivalent, or a condvar timed to the deadline that the backend can signal) instead of 1 ms/200 us polling, and make the SDL/CoreAudio "room" wait event-driven if the backend can signal it. Must preserve W/Z/AP behaviour: deadline-debt recovery, 4.33 ms producer reserve, resync after stalls, 187.5 blocks/s, no alternating silent blocks. Add AUDIO_RATE-style stats if missing.

## Part 3 — guest usleep polls (investigate, implement only if clean)
Identify what PPU main 0x002FC970 and NisAt3Line 0x00161438 are waiting for (PS3_WAIT_OBJ=<lr hex> dumps registers/object; read the lifted code in port/src/recomp-140). If the awaited condition is a guest-memory value or a known HLE event, propose a port-specific override (port/stubs.cpp or port/src/d2_*.cpp, like the AQ/AR native overrides) that waits on a notified condition with a bounded timeout equal to the original sleep cadence ceiling. Do NOT change guest-visible timing semantics blindly (no global usleep rounding). If not clean/safe, report findings only.

## Verify
- Full ctest in build-az passes; new tests for Part 1 self-tuning and any Part 3 override (compare against the lift like d2.AQ-fill / d2.AR-shader do).
- Headless routes as in codex/AY.headless-check.sh: hub, title from install-only hdd0, battle; music streams, no ATRAC stalls, dummy audio 0% silent.
- Write codex/AZ.host-check.sh (real Metal; AZ_AUDIO=1 real CoreAudio), comparing port/build-ay/DisgaeaD2Recomp vs port/build-az with each part toggleable by env (so Claude can measure each part alone): report CPU, csw/s, idlew/s from top deltas, flips/s, worst interval, audio blocks/s + silent %, POLL_STATS, and a PS3_POLLTOP summary.
- Export only your SDK changes to patches/AZ-runtime.diff. Do not commit.

Report per part: measured before/after counters, what changed, risks left.
