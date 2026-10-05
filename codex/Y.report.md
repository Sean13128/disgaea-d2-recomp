# Y — Castle Hallway slowdown

**A generic flip-ordering defect is fixed; the real-Metal slowdown is not yet established as fixed.** The supplied hypothesis does not match D2's measured heavy-room path: every direct flip has `put == get`; ring-full callbacks already kick the drain, and none of their drains was held for presentation.

The reproduced main room is **Castle Hallway, map30001**, reached with Continue, Cross at 10/14/18 seconds, then Down → Left → Left → Down. D-pad input works; my initial longer route failed to reach the exit. Hallway produces about **7.1 ring wraps/frame**. On the final timing-only run, each recycle averages **0.593 ms**, kick→drain **0.027 ms**, and wake→next submission **14.577 ms**. About 4.2 ms/frame is serialized recycle work. Frame preparation is close to the 16.667 ms deadline; missing it costs a refresh. This is not evidence of a drain parked until vblank.

The generic defect: a direct HLE flip with unread submitted commands immediately set the global hold and could be presented before those commands executed. It now snapshots the FIFO boundary, drains/records the preceding commands, and becomes presentable only on reaching that boundary. Decoded FIFO flips remain ready immediately; subsequent commands remain held to prevent mixing frames. VSYNC still retires at most one flip per vblank. Both recycle acknowledgments and fence ordering remain intact. `GCM_RECYCLE_TRACE=1` adds count, positions, condition waits, duration, explicit tail/jump kick times, and correlated drain times/hold state.

Changes: `ps3recomp/libs/video/cellGcmSys.c`; four cleanup lines in `codex/Q.sync-test.c` so its dummy watcher submission leaves an empty FIFO for T; `.gitignore` artifact entries; `codex/Y.host-check.sh`, `Y.analyze.py`, `Y.sync-test.c`, and `patches/Y-fifo-boundary.diff`. No Metal implementation, game override, dump, other build directory, commit or push was changed by Y.

Verification:
- Release build in **port/build-y** passed (`codex/Y.final-build.log`). Patch reverse-apply, shell syntax, Python syntax and whitespace checks passed.
- Q **6**, T **11**, Y **3 additional FIFO checks** pass (`Y.Q-sync-test.log:1–6`, `Y.T-sync-test.log:1–11`, `Y.sync-test.log:7–9`). Y's unread-command check fails against the old implementation at line 61 (`Y.sync-baseline-test.log:1`).
- X draw suite **81 checks** and **67,080 texture mutations** pass (`Y.draw-test.log`, `Y.hash-test.log`). X's existing host analyzer, using only build-y, verifies battle **60.017 distinct flips/s**, **470/470 matched flips retiring one tick after submission** (`Y.X-headless-check.log:4`).
- Controlled hallway comparison uses the same linked runtime objects except cellGcmSys, copied saves, identical input and tracing, two 40-second runs:

| Timing-only run | Distinct flips/s | Flips / vblanks | Steady window |
|---|---:|---:|---:|
| Before | 56.332 | 353 / 376 | 6.266 s |
| After | 59.842 | 378 / 379 | 6.317 s |

Logs: `port/runs/Y-host.clAGiA/run.log:20910` and `Y-host.VAr22b/run.log:20903` load map30001. Their summaries and `codex/Y.controlled-{baseline,final}.log` contain the individual-sequence measurements. Final log **46308–46314** shows tail kick, drain starting 4 µs later, tail consumed, jump kick, head consumed, and a 315 µs recycle. Both runs have **zero unread-FIFO flip submissions, zero held recycle drains, zero missing kicks**. Consequently the rate difference is **not a demonstrated causal gain from the ordering fix**. Earlier uncontrolled rates ranged 33.439–56.722, further illustrating sensitivity near the deadline. No recycle-stall/corruption warnings; alarm exits were 142.

Remaining: real Metal is unavailable in the sandbox. Run `bash codex/Y.host-check.sh` on the Mac and remain in Castle Hallway. It builds only build-y, clones saves, attempts the measured route and reports distinct flips plus recycle/flip latency; no frame dumps, `rg`, or deletion. Use `Y_MANUAL=1 Y_SECONDS=90` for keyboard navigation. For a matched pre-fix host run, use `Y_SKIP_BUILD=1 Y_BINARY=./port/build-y/Y-baseline`; that binary is retained in build-y. Headless reproduction: `Y_HEADLESS=1 Y_FIFO_ONLY=1 Y_SECONDS=40`. Compare real-Metal frame preparation/render cost before further scheduling changes. Prior art reviewed: Twisted Metal's independent drain/present loop and ps3recomp PR #160's FIFO-positioned flips.
