# T — VSYNC pacing

The reported **69.90 flips/s was a measurement artifact**, not demonstrated D2 overspeed. S paired its shell sampling time with the latest asynchronously written frame count: `S-host-20261005-033746/map.samples` jumps from 6070 to 6670 between labels 110 and 115, skipping the 6370 record. Its own game log reports 59.38–60.04 flips/s on the map (`map.log:8411–11095`). T measures completed flips and their monotonic timestamps together.

D2 pacing: its lifted frame path `func_002C0C44` calls `func_002D2664` (RESC ConvertAndFlip), then `func_002D2634` (RESC WaitFlip). The 50,000-call boot trace records 35 of each (`port/runs/T-baseline.log`). D2 imports neither GCM SetFlipMode/WaitFlip/ResetFlipStatus/GetFlipStatus/GetVBlankCount nor RESC flip/vblank handlers; GCM initializes in VSYNC mode. No game override is needed. Q's RESC sequence wait already works.

Generic firmware defects fixed:
- Flip mode was stored but ignored; pending requests could be merged, and FIFO backlog could consume several flips before presentation. Each VSYNC flip now retires separately on a subsequent tick of one monotonic **60 Hz** phase, at most once per vblank. HSYNC can present immediately. A bounded queue supplies backpressure without dropping flips.
- Vblank queries manufactured ticks; counters were tied to tick calls. The 64-bit counter now derives from elapsed monotonic time, including missed refreshes, without presentation or read side effects.
- Submission could invoke a flip handler early. Status, completion semaphore, microsecond last-flip time, completion notification and deferred handlers now publish after the gated present. FIFO batches remain held through presentation; Q's event-driven drain resumes immediately afterward.
- Driver flip methods could bypass the clock through the draw engine. They now use the same gate. Metal receives the selected completed buffer and explicitly synchronizes its CAMetalLayer for VSYNC, retaining asynchronous submission and existing in-flight bounds.

Files changed: `ps3recomp/libs/video/cellGcmSys.c/.h`, `rsx_metal_backend.m/.h`, `ps3recomp/templates/project/main.cpp`, `port/main.cpp`; added `patches/T-vsync.diff`, `codex/T.sync-test.c`, `T.sync-check.sh`, `T.host-check.sh`, and this report. `cellResc.c` required no change. No dump, other build directory, commit, or push was touched.

Verification:
- Prescribed Release build in **port/build-t** passed (`codex/T.configure.log`, `T.final-build.log`). Shell syntax, diff whitespace and SDK patch reverse-apply checks passed.
- All **11 synchronization checks** passed (`codex/T.sync-test.log:1–11`): Q's six checks plus clock independence, separate queued flips with completion-time status/labels/timestamps/GCM+RESC notifications, skipped refreshes, HSYNC, and full-queue wakeup.
- Final 140-second FIFO-only headless run: **title 59.9052**, **loaded map 59.9673 completed flips/s**, no interval completing more flips than elapsed vblanks. `port/runs/T-final-headless-20261005-035816/game.log:3134,5773` records 1651→3751 title flips; `:8793,11094` records 6102→7905 map flips. `:6570` confirms the requested save load; `:6596` loads `MAP/mp300/map30003.lzs`. Exit 142 was the expected alarm; no recycle stalls/overflow/unimplemented warnings.
- Earlier 140-second check also passed: title 60.0008, map 59.9351 (`port/runs/T-headless-20261005-035300/summary.txt`). A separate software-drawing title run is CPU-bound at about **30 flips/s** (`port/runs/T-software-title.log:1776–2172`); FIFO-only results verify timing, not renderer throughput. Small wall-time rate deviations above 60 reflect tick delivery jitter; the completion gate enforces one flip per clock slot.

Remaining: **real Metal/window validation**. Run `bash codex/T.host-check.sh` outside the sandbox; it builds only build-t, clones the save, skips movies, selects Continue at 75 seconds, presses Cross every four seconds, reports both steady windows, and checks the one-flip-per-vblank bound. `T_HEADLESS=1 T_FIFO_ONLY=1` selects timing-only diagnostics. The script uses grep and no rm. Research checked Twisted Metal's runner, ps3recomp PR #160, and RPCS3's GCM/RSX timing implementation as prior art.
