
# Task AX — heat fix B: real blocking sys_lwcond (yourname = AX, build dir port/build-ax)

Read codex/AV.report.md first (finding 2, finding 3, and "Recommended order" step 2). AW (fix A, adaptive graphics poll cap) is applied in the shared SDK tree and verified on real Metal: hub csw 96k/s -> 46k/s, idlew 14.4k -> 4.4k, 60 fps. Keep AW's changes; build on top of them. Report: codex/AW.report.md, data port/runs/AW-host.yNgFTy.

## Problem
ps3recomp/runtime/ppu/ppu_sysprx.cpp ~338-359: sys_lwcond_wait releases the lwmutex semaphore, Sleep(1), reacquires, returns success; sys_lwcond_signal/_all/_to are no-ops; timeout ignored. In the hub 12 FIOS threads loop on it (~1k wakeups/s each) and each ReleaseSemaphore also broadcasts the global multi-wait condition in runtime/platform/win32_compat.c ~170 (waking RSX render's WaitForMultipleObjects).

## Do
1. Implement real blocking lwcond in the active context-handler path (ppu_sysprx.cpp), keeping the existing semaphore-based lwmutex (cross-thread release is intentional; do not replace with a pthread mutex). Follow AV's design rules exactly:
   - host wait queue per guest lwcond (keyed by its EA + queue id); enqueue the waiter under the queue lock BEFORE releasing the lwmutex semaphore, then block; per-waiter "selected" flag (no shared generation/credit that leaks to future waiters).
   - never hold the queue lock while reacquiring the guest lwmutex semaphore.
   - signal = one current waiter, signal_all = all current waiters, signal_to = guest thread id (ctx->thread_id); return the PS3 error codes RPCS3 returns (e.g. ESRCH/EPERM cases) — compare with RPCS3 rpcs3/Emu/Cell/Modules/sys_lwcond_.cpp and lv2 sys_lwcond.cpp (use gh / web).
   - timeout r4 in microseconds, 0 = infinite; on timeout dequeue under the queue lock (no stale signal_to), reacquire the lwmutex, return ETIMEDOUT.
   - restore owner/recursion correctly on reacquire (validate; don't resurrect a stale owner).
   - destroy: refuse/handle with waiters as RPCS3 does.
   Note libs/system/sysPrxForUser.c:660-777 has a separate, inactive model — don't route to it.
2. Env escape hatch PS3_LWCOND_POLL=1 restores the old Sleep(1) behaviour (for A/B and rollback).
3. Counters behind PS3_LWCOND_STATS=1: waits, signals, wakes-by-signal, timeouts per ~10 s.
4. Tests (new SDK test or port test, added to CTest): signal between release and park, signal with and without holding the lwmutex, signal-before-enqueue leaves no credit, N waiters signal/signal_all/signal_to, recursion count preserved, timeout racing signal, destroy/recreate, cross-thread lwmutex release. Full ctest in build-ax must pass.
5. Headless game runs (PS3RECOMP_METAL_HEADLESS=1 if needed, SDL_AUDIODRIVER=dummy, scratch copies of port/hdd0 under /Volumes/Data/ai-tmp/codex/): (a) boot -> title -> Continue slot 00 -> hub (same env as codex/AW.host-check.sh), (b) the 1.40 boot path from a fresh empty hdd0 to title (CRT/static init), (c) a map change / battle load if a pad route exists in codex/*host-check.sh (e.g. hub -> map30005 -> hub as in AP), and confirm music keeps streaming (PS3RECOMP_ATRAC_TRACE=1, no [cellAtrac] stall lines). Compare PS3_LWCOND_STATS and fps with PS3_LWCOND_POLL=1 on the same binary.
6. Write codex/AX.host-check.sh modelled on codex/AW.host-check.sh: real Metal, binaries = port/build-aw/DisgaeaD2Recomp (AW-only) vs port/build-ax/DisgaeaD2Recomp, same hub route, top csw/idlew, flips, lwcond stats. Add AX_AUDIO=1 mode that leaves SDL_AUDIODRIVER unset (real CoreAudio) for Claude's audio check.
7. Export SDK diff of ONLY your changes to patches/AX-runtime.diff (AW is in patches/AW-runtime.diff). Do not commit.

Report: design summary, test list + results, headless before/after (lwcond waits/wakes, CPU, fps), anything risky left.
