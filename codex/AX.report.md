# AX — blocking sys_lwcond

Root cause: active sysPrxForUser context handlers ignored signals/timeout and returned success after Sleep(1). Twelve idle FIOS workers repeatedly released/reacquired lwmutex semaphores, also broadcasting the global multi-object condition used by RSX. AW remains intact; multi-wait fan-out and audio policy were not changed.

Design: queues are keyed by guest EA + queue ID. Enqueue precedes semaphore release; selection/removal uses the queue lock and a per-waiter selected flag/guest thread ID. No saved signal credit; no queue lock during semaphore reacquisition. Wait validates calling ownership, preserves recursion, honors r4 microseconds (0=infinite), removes timed-out targets under the queue lock, reacquires, and restores the validated caller/count. Missing queue/thread returns ESRCH; nonowner wait/nonwaiting existing target returns EPERM; empty ordinary signal/all returns OK. Targeted UINT32_MAX preserves owner/busy/free no-waiter results. Destroy returns EBUSY through relock and retires the identity when empty. This is conservative: RPCS3 waits out relockers instead of returning busy.

The semaphore lwmutex/cross-thread release remains. Cancellation cleanup removes the waiter and releases queue/any acquired semaphore; cancellation-masked 10 ms relock attempts keep compatibility references balanced. PS3_LWCOND_POLL=1 uses a direct legacy release/Sleep(1)/reacquire path, with ignored timeout/no-op signals and no queue/CV overhead. PS3_LWCOND_STATS=1 logs interval waits/signals/signal completions/timeouts/poll returns about every 10 s when activity occurs, without an idle stats timer.

Read inactive C HLE/prior ports/PR #160 with gh; compared [RPCS3's context-facing behavior](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/sys_lwcond_.cpp) and [LV2 errors/destruction](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/lv2/sys_lwcond.cpp). The strict ppu_thread_exists helper avoids the priority-query fallback that accepts unknown IDs.

Changed: SDK runtime/ppu/ppu_sysprx.cpp, runtime/syscalls/sys_ppu_thread.{c,h}, runtime/ppu/tests/test_lwcond.cpp; port/tests/CMakeLists.txt; codex/AX.{host,headless}-check.sh; patches/AX-runtime.diff. SDK export contains only AX's four SDK files; reverse apply --check passes. No commit/push, dump edits, personal-save writes or other build-directory writes.

Build-ax uses the documented Release/Ninja/recomp-140/Homebrew flags and matching .venv Python. Final full CTest: **49 passed, four Metal skips, zero failures**, 53 registered / 68.07 s (port/runs/AX-ctest.log). LastTest.log:6207–6214 contains lwcond PASS evidence; :6230 verifies rollback. Tests use the actual active TU and real compatibility semaphores: release/park signals with/without ownership, no pre-enqueue credit, six waiters with one/all/to, recursion=3, timeout/relock, 100 timeout/signal races, cancellation while parked/relocking, busy destroy/recreate/stale IDs, cross-thread release and error cases. bash -n and scoped diff --check pass.

Six 40 s functional runs in port/runs/AX-headless.gbD4JB all exited 142. Continue slot 00 reached map30003 in both modes. Raw empty HDD0 lacks v1.40 START_7.dat in both modes, so cannot reach title; starting empty and installing only update/DLC content, without saves/settings, reached title BGM (firstboot.log:3970 SetData, :10218 Decode=601). U's existing FIFO-only debug route reached battle (battle.log:9139 stage=101, :9390 map00101, :10241 battle music, :17965 Decode=401). No ATRAC stall/WARNING or fault diagnostics; settled audio had zero silent blocks. The wrapper hit a post-run parse error because I edited it during execution; all six logs passed independent assertion replay, and the delivered wrapper passes syntax checking.

Final controlled comparison: port/runs/AX-host.WMlH0T, three sequential 90 s runs, same ELF/save/scene/settings and no build/test load. Host script completed successfully. CPU uses final six ~5 s intervals, flips final 30 s, lwcond final three summaries; AX-metrics.json retains evidence. Earlier q1rJyI polling numbers included queue/CV overhead and are superseded.

| Settled headless hub | AW-only | AX blocking | Same binary, polling |
|---|---:|---:|---:|
| CPU (% of one core) | 111.98 | 108.22 | 112.68 |
| lwcond waits/s | uninstrumented | 0.508 | 9,587.1 |
| signal completions/s | uninstrumented | 0.508 | 0 |
| forced poll returns/s | uninstrumented | 0 | 9,587.1 |
| timeout returns/s | uninstrumented | 0 | 0 |
| distinct flips/s | 12.000 | 12.000 | 12.000 |
| worst flip interval, ms | 83.697 | 85.026 | 83.602 |

Wait traffic fell **99.995%**; CPU fell **4.46 points (~4%)** versus same-binary polling, or 3.76 versus AW-only. Twelve waits remain outstanding after boot; later balanced summaries confirm idle workers stay parked. blocking/game.log:11597 has 6 waits/wakes in 11.750 s; poll/game.log:12037 has 95,882 poll returns in 10 s. All three loaded the hub, streamed music and exited 142. Long-run dummy audio pacing was below nominal in all controls (~171 blocks/s AW-only/poll, ~173 blocking), with zero silent blocks; actual CoreAudio pacing remains unverified.

Remaining: real Metal 60 Hz/tail pacing, csw/idlew/power (Metal has no sandbox device; top/ps denied), CoreAudio listening/full music loop, map30005 round trip and interactive save/load repetition. Actual SPURS-title startup is unverified; D2 uses raw SPU groups. Run bash codex/AX.host-check.sh; AX_POLL_CONTROL=1 adds same-binary rollback, AX_AUDIO=1 leaves SDL_AUDIODRIVER unset, AX_SECONDS=230 permits longer audio checks. Scripts use/remove their own scratch HDD0/HDD1/settings.
