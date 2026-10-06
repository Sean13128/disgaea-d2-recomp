
# Task AV — REVIEW ONLY: CPU heat / wakeup analysis (yourname = AV)

THIS IS A READ-ONLY REVIEW. Do not edit source, do not build, do not run the game. The only file you write is codex/AV.report.md. This overrides the build/fix rules above.

## Context
User report: Disgaea D2 (native port) runs the Mac at ~70 C vs ~40 C idle. Machine: Mac mini M4 (Mac16,10), 4 P + 6 E cores.
Claude measured it (real Metal, copied save slot 00, castle hub, 60.0 fps, SDL_AUDIODRIVER=dummy, binary port/build/DisgaeaD2Recomp, ELF work/v140/EBOOT.elf). Raw data (read it, verify the numbers yourself):
DATA=/Volumes/Data/ai-tmp/claude/d2-heat
- $DATA/power.txt — powermetrics cpu_power,gpu_power,thermal, 2 s intervals; idle 15:36:11-15:36:31, game 15:36:31-15:39:01 (timeline.txt)
- $DATA/tasks.txt — powermetrics tasks sampler (second run; game 15:42:57-15:44:47)
- $DATA/hub-sample.txt — `sample` 5 s of the game in the hub; $DATA/top.txt CPU%
- $DATA/game3.log + top3.txt — third run with PS3_POLLTOP=10 (usleep histogram) and top csw/idlew counters
- $DATA/paths.py — helper: python3 paths.py hub-sample.txt "<thread regex>" "<leaf regex>" [n]

## Claude's findings (verify or refute each)
Measured: CPU package ~3.7 W in game vs 0.3-0.5 W idle; GPU only ~0.15 W. All 4 P-cores at 4.46 GHz (max), ~60% active residency each, P-cluster 93% active. Game itself only ~0.58 cores CPU time (top ~57%). powermetrics: DisgaeaD2Recomp ~71,000 wakeups/s (WindowServer ~480). top: ~100k context switches/s.
Conclusion: heat is wakeup-driven (cores never idle and DVFS pins max clock), not compute-driven.

Contributors identified:
0. ps3recomp/runtime/platform/guest_poll.c:146 ps3_poll_backoff — fixed 100 us pthread_cond_timedwait_relative_np safety timeout. 7 threads sit in it permanently in the hub: 6 NisGraphicsSpu_Group (mfc_poll, runtime/spu/spu_dma.h) + "RSX submit" gcm_put_watch (libs/video/cellGcmSys.c:~1770). ~10k wakeups/s each.
1. ps3recomp/runtime/ppu/ppu_sysprx.cpp:345 sys_lwcond_wait — polls: release lwmutex semaphore, Sleep(1), reacquire; sys_lwcond_signal/_all/_to are no-ops. 12 FIOS threads loop on it (~1k/s each) and contend on the semaphore (mutexwait/cvbroad in their busy stacks, ~1.3% CPU each).
2. Guest PPU main usleep(30us) at lr 0x002FC970: ~2,000/s.
3. NisAt3Line threads usleep(1ms) at lr 0x00161438 (~1,850/s) and 5 ms at 0x0015F890 (~180/s).
4. RSX render frame_clock: cellGcm_fifo_kick_wait woken by every put change seen by the RSX submit poll; timed waits cost ~2.3% of a core in gettimeofday.
5. QoS: ps3_poll_thread_start (guest_poll.c:~267) gives QOS_CLASS_USER_INTERACTIVE to every guest PPU thread (sys_ppu_thread.c:114 passes 1) incl. 12 FIOS, At3 decoders, mixers; also RSX copy/submit; cellAudio mix thread (cellAudio.c:741). Hypothesis: interactive QoS + constant wakeups keep the P-cluster at max frequency.

## Proposed fixes (review these)
A. ps3_poll_backoff: per-thread exponential timeout 100 us -> cap ~2-4 ms on consecutive no-change timeouts, reset on change. Rationale: notify (ps3_poll_notify_slow) already wakes waiters; the timeout only covers the registration race.
B. sys_lwcond_wait: real blocking wait with working signal / signal_all / signal_to (and timeout arg), preserving lwmutex ownership handoff semantics (recursion count, owner stamp).
C. QoS: keep PPU main, RSX render/submit, synth2 at USER_INTERACTIVE; drop FIOS / At3 / mixer / other guest threads to UTILITY or DEFAULT.
D. Leave guest-side usleep loops (#2, #3) alone for now.

## What I want from you
1. Check the data: are the attributions right? Does 7 x 10k + 12 x 1k + ~4k account for ~71k wakeups / ~100k csw, or is something missed (e.g. RSX render kicks, SDL audio threads, Metal/dispatch workqueue threads, fios semaphore handoff storms)? Point out anything Claude missed or got wrong.
2. Review fixes A-C for correctness risk: lost-wakeup races in A (relaxed global guard in ps3_poll_notify paths, stores not going through notify, SPU DMA PUT/reservation paths); semantics/deadlock risk in B (FIOS, cellSpurs/CRT one-shot uses noted in the comment above sys_lwcond_create, lwmutex being a semaphore released from any thread); audio underrun / frame-pacing risk in C (60 Hz flip, synth2, ATRAC music which previously had dropouts — see OPERATIONS.md AP/W/Z).
3. Better or simpler alternatives, and a recommended order + how to verify each (non-sudo: `top -l N -s 2 -pid <pid> -stats pid,cpu,csw,idlew,th`; sudo powermetrics only at the end).
Be concrete: file:line, specific failure scenarios. Rank findings by severity. Keep the report under ~150 lines.
