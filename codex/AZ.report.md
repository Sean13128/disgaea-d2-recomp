# AZ — remaining wakeups, heat round 2

SDK base `d2-macos ee70875`; project base `3414a79`. No commit/push, game-dump writes, personal-save changes or writes to other build directories. `build-az` uses the documented Release/Ninja/Homebrew configure flags, `src/recomp-140`, matching `.venv` Python and v1.40 ELF (`work/v140/EBOOT.elf`, as AY's scripts use).

## Part 1 — graphics

Measured before extending: two 40-second instrumented runs, `port/runs/AZ-headless.tUyAAJ/{baseline,atrac-object}.log`. Across 36 graphics-SPU summaries: **312,431 timeout returns, zero timeout-discovered changes**, 14,439 notified returns / 1,132 notified-discovered changes. RSX totals: 56,497 timeouts / 21 changed rechecks versus 10,061 notified changed rechecks; later stats distinguish PUT polls from short label waits. Counts describe condition returns, not interrupt wakeups.

Opted-in idle graphics now grow **100 → 200 → 400 → 800 → 1600 → 3200 → 6400 → 8000 us**. Every timeout recheck finding changed bytes forces that thread's idle cap to **100 us for one second**, including across EA/snapshot/sequence resets. Notifications remain immediate; unchanged collision/spurious notifications neither grow nor reset the ladder. `PS3_POLL_IDLE_CAP_US=100..8000` is retained; `PS3_POLL_IDLE_TUNE=0` restores the old default 1ms ladder. PPU hotreads, audio and RSX label/equality waits retain 100us. Stats add changed-value counts, idle-only counts and cooldowns.

The PUT watcher is a render-kick fallback; lifted stores already kick directly. **SDK HLE PUT writes in flush/recycle/syscall FIFO setup lacked memory-poll notification.** Added notification after those five stores. An early extension-only experiment repeatedly penalized RSX into short waits; its final preliminary RSX interval exceeded 4,800 timeouts/s. The corrected final measurements supersede those experiments.

Final combined versus same-binary control: SPU timeouts **5,173.3 → 701.0/s (-86.4%)**; all seven graphics workers **6,049.5 → 1,866.4/s (-69.1%)**. **RSX itself increases 876.2 → 1,165.4/s**: four timeout-discovered PUT changes in the last three summaries trigger cooldowns (0.130/s), versus ~127.7 notified changes/s. Protection works, but residual misses/timeout-notification races remain; this is not a complete RSX wakeup fix. Full log lines 9366, 10396, 11427 show those returns; line 11356 confirms PPU main cap=100. The first missed idle notification can still cost up to 8ms plus host scheduling before the penalty starts. Real Metal tail latency remains to be measured.

## Part 2 — host audio

Root causes: repeated sub-period 1ms/200us deadline sleeps and SDL QueueAudio room polling. POSIX now uses one absolute `mach_wait_until` (Darwin) / `clock_nanosleep(TIMER_ABSTIME)` (Linux) per deadline, retrying only interruptions. **CLOCK_MONOTONIC remains the clock for guest timestamps and ATRAC diagnostics**; only the remaining wait interval is converted to Mach ticks. A preliminary Mach-clock variant logged watchdog warnings and was discarded. Final rollback and all enabled modes have zero warnings.

SDL callback mode owns a bounded four-block stereo PCM ring. Device consumption copies PCM, zero-fills starvation and signals room under the same small mutex used by submit/register/recheck. Room waits use a condition with a 100ms removed-device watchdog and explicit shutdown wake. Device consumption never advances guest audio; existing prime, deadline-debt discard, >3-period resync, 4.333ms producer reserve and 187.5Hz period remain. Windows WASAPI timing is unchanged. `PS3_AUDIO_CLOCK_POLL=1` and `PS3_AUDIO_ROOM_POLL=1` independently restore old POSIX clock / SDL queue-room behavior. AUDIO_RATE adds host-wait and callback/underrun counters.

Combined host wait returns **1,143.4 → 231.0/s (-79.8%)**. Clock-only deadline returns **363.5 → 69.3/s**; callback-only room returns **779.9 → 186.5/s**. Full final six intervals report **0.000% silent guest blocks and 0 callback-underrun frames**, at 185.97 blocks/s. Dummy device pacing remains below nominal (control 186.67/s); real CoreAudio 187.5Hz/listening/full-loop/focus recovery is unverified. Full log 11279–11281 and 11780–11782 contain final rate/wait/device evidence.

## Part 3 — guest sleeps: findings only

- **Main LR 0x002FC970:** lift `ppu_recomp_017.cpp:2539`, `func_002FC938`, emits SET_REFERENCE through `002FC9B8`, flushes through `002FC8E0`, and waits for equality of `control.ref` at **0x20002008** to r31, sleeping 30us. `baseline.log:181,251` dumps r30=0x20002000 and the changing expected reference. SDK `gcm_ref_publish_one` publishes ordered transient values at a 200us minimum interval and notifies; lifted `vm_read32` also invokes `cellGcm_ref_on_poll`. A raw-memory waiter would omit that progress side effect. A safe override must retain read-driven publication and equality visibility with a 30us fallback; that bound offers no established wakeup reduction. No override.
- **NisAt3Line LR 0x00161438:** lift `ppu_recomp_007.cpp:35914`, `func_0016059C`, unlocks its object mutex at +0x2F8, loops to a 1ms sleep at `loc_001605E4`, reacquires, then switches on command/state byte +8. It services multiple codec, ring and control flags rather than one condition. `atrac-object.log:253–255` identifies objects 0x01258130 / 0x01258430 / 0x01258730 and their mutexes. LR names the preceding unlock, not the awaited value. At **0x0015F890**, `func_0015F814` sleeps 5ms after unlocking when ring capacity minus occupancy (+0x20 minus +0x1C) is insufficient. A command-byte-only override would miss consumption/refill/stop work; retaining 1ms/5ms fallback ceilings gives no demonstrated gain. No global sleep rounding or guest override.

Final headless POLLTOP: main ~7,743 calls/s, NisAt3Line ~1,748/s plus 167.5/s at the 5ms site. These are unlocked estimates in a 12fps software-renderer run, not the supplied real-Metal rates. The host script prints the same summary for hardware runs.

## Verification and measurements

Full CTest: **54 passed, four Metal skips, zero failures**, 58 registered / 81.01s (`port/runs/AZ-ctest.log`). `build-az/Testing/Temporary/LastTest.log:114` proves the 8ms ladder, persistent 100us missed-notify cooldown, expiry, notified and short paths; :6297 proves HLE flush wakes the watcher before the 8ms fallback; :6315–6318 proves one deadline wait, callback order/wrap/room/shutdown and two-block consumption with 2-second/30ms stalls. Audio fixture: 1,014 blocks, **0% silent**, minimum producer gap **4.358ms**. Existing W/Z/AP, AQ/AR, synchronization, SPU/cache and lifecycle checks pass.

`port/runs/AZ-headless.VRergS`: three final 40s routes all exit 142. Hub LOAD/map30003: hub.log:4703,4780; streaming call 401:6532. Install-only HDD0 without saves/settings reaches title music: firstboot.log:3856,10061. Battle stage101/map00101: battle.log:9179,10117; streaming call401:18101. All final audio intervals report 0% silent; no ATRAC stall/WARNING, FAULT or HOST CORRUPTION.

`port/runs/AZ-host.PgCQ1o`: six sequential 90s comparisons, frozen build-ay and the same final build-az binary, fresh scratch saves/settings, identical hub route, no own build/test load. All exit 142 and pass assertions. `binaries.sha256`, `summary.txt`, `AZ-metrics.json` retain evidence. CPU/audio use final six ~5s intervals; polls final three per-thread summaries; flips final 30s. Control retains the HLE notification repair while disabling the three scheduling changes.

| Mode | CPU % | Graphics timeouts/s | Clock / room waits/s | Blocks/s / silent | Flips/s / worst ms |
|---|---:|---:|---:|---:|---:|
| ay | 109.35 | 6049.4 | nan / nan | 186.50 / 0.000% | 11.987 / 100.037 |
| control | 109.07 | 6049.5 | 363.5 / 779.9 | 186.67 / 0.000% | 11.980 / 102.232 |
| graphics | 107.52 | 2006.4 | 705.7 / 609.4 | 186.60 / 0.000% | 11.980 / 100.226 |
| clock | 108.87 | 6046.7 | 69.3 / 826.1 | 186.53 / 0.000% | 11.993 / 101.497 |
| room | 108.70 | 6054.2 | 147.1 / 186.5 | 186.48 / 0.000% | 11.993 / 102.663 |
| full | 106.90 | 1866.4 | 97.7 / 133.3 | 185.97 / 0.000% | 12.001 / 85.485 |

Headless CPU improves **109.07 → 106.90%** versus control (2.17 points), or 109.35 → 106.90 versus frozen AY. Software-renderer frame pacing does not establish native 60Hz behavior or power savings. `top` is denied in this sandbox; csw/s and idlew/s are unavailable. The final analyzer reproduces AV's historical top3 numbers (57.95% CPU, 100,074.8 csw/s, 12,277.5 idlew/s; `AZ-top-parser-check.log`); those are parser validation, not AZ performance.

Hardware preflight (`port/runs/AZ-host.vLdrjz/full/game.log`) confirms the limitation: :172–175 has no Metal device/software fallback; :220 has CoreAudio device error 560947818. The wrapper exits 1 with `CoreAudio unavailable`; no hardware/power result is claimed.

## Files and remaining work

SDK: `runtime/platform/guest_poll.{c,h}`, `runtime/platform/tests/test_guest_poll{,_filter}.c`, `libs/video/cellGcmSys.c`, `libs/audio/cellAudio.c`, new `libs/audio/tests/test_audio_wait.c`. Port: `tests/CMakeLists.txt`, `tests/run.py`, new `tests/AZ.gcm-put-test.c`. Deliverables: `codex/AZ.{headless,host}-check.sh`, this report, **`patches/AZ-runtime.diff`**. SDK export excludes the pre-existing Windows AUDIO_WAV timestamp edit and concurrent Metal overlay edits. Forward apply against clean ee70875 and reverse apply against the shared tree both pass; scoped diff checks and bash syntax pass.

Reviewed existing SDK audio/synchronization fixtures and reference ports/PR160 through gh. SDL's [callback API](https://wiki.libsdl.org/SDL2/SDL_AudioSpec) supplies the consumption event missing from QueueAudio; no port-specific audio timing fork was needed.

Run **`AZ_AUDIO=1 bash codex/AZ.host-check.sh`** outside the sandbox. It defaults to real Metal, compares AY/control/graphics/clock/room/full, checks hardware availability and prints CPU, cumulative top csw/idlew deltas, flips/tail, audio and poll counters plus POLLTOP. `AZ_RUNS='ay graphics full'` selects modes; `AZ_SECONDS=230` enables a longer music-loop check. Measure real 60Hz/tails, CoreAudio 187.5Hz/0% silence, focus/stall recovery and package power/wakeups before claiming a native heat improvement. Guest sleeps and residual RSX cooldowns remain.
