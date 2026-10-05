# X — battle speed

The current FIFO-only battle runs at **60 distinct guest flips/s**. I did not reproduce an extra-vblank retirement bug in that path. Real-Metal battle speed remains unverified: this sandbox reports `no Metal device available`.

## Findings / change

- D2 calls `func_002C0C44` once per frame: Finish → RESC ConvertAndFlip → WaitFlip → Finish. There is no two-vblank divider in that path. Both baseline and final stage-101 runs request/complete approximately 60 distinct flips/s, so the guest supports the requested 60-flip battle cadence.
- All measured D2 RESC submissions used the direct GCM queue, with `put == get`: the preceding guest Finish had already drained the frame. No undrained FIFO was held behind those flips. The trace’s `reach` for this path denotes queue readiness, not GPU completion. Imported FIFO flips additionally log their command EA at submission and map that EA to the decoded flip sequence.
- The texture cache already hashes **once per cached texture per frame**, not every draw. Its full-span FNV loop nevertheless has a multiply dependency through every eight bytes, matching the supplied Metal sample’s hashing hotspot. Replaced it with four independent streams; full-span mutation checks and per-frame invalidation remain enabled. Benchmark: **70.232 → 17.700 ms per 512 MiB (3.97×)**. This reduces renderer work; it does **not** establish that the reported visible slowdown is fixed.
- No scheduling/retirement rules changed. T’s one-flip-per-vblank cap remains intact.

## Files changed by X

- `ps3recomp/libs/video/cellGcmSys.c`: opt-in `GCM_FLIP_TRACE` submission, ready, selection, retirement, wait/wake timestamps and FIFO EA/sequence correlation.
- `ps3recomp/libs/video/rsx_draw_engine.c`: four-stream texture mutation hash; preserved V’s existing changes.
- `codex/Q.sync-test.c`: select HSYNC for completion-order tests. The standalone Q check was stale after T: it otherwise attempted immediate VSYNC retirement in clock slot zero. T separately tests real VSYNC pacing.
- `codex/X.host-check.sh`, `codex/X.hash-test.c`, `.gitignore`, `patches/X-battle-speed.diff`, this report. SDK patch contains only X’s hunks and passes reverse-apply checking.

Only `port/build-x` was configured/built. Q/T checks used their existing sources and commands with outputs redirected into build-x; their scripts/build directories were not changed. No dump edits, commits or pushes.

## Verification

- Prescribed Release build passed: `codex/X.configure.log`, `X.final-build.log`.
- Q: **6 checks**, T: **11 checks** pass (`X.Q-sync-test.log`, `X.T-sync-test.log`). Existing draw-engine suite: **77 checks** pass (`X.draw-test.log`), including same-frame cache reuse and changed/unchanged textures across frames.
- `X.hash-test.log`: 67,080 individual byte mutations covering every alignment/tail through 129 bytes, stability and unreadable inputs pass. ASan/UBSan pass in `X.hash-sanitized.log`; its instrumented timing is not a performance result.
- Final 40-second run: `port/runs/X-host.GDE0JF/run.log`. Warp confirmation at **11101**; battle mission 5011/map 101 at **13237**. Steady rate records at **15236 / 17727** report **60.000797 / 60.001096 flips/s**. Submission/selection/retirement/wake examples at **19319–19326**.
- `codex/X.headless-final.log`: **437 distinct flip intervals / 437 vblanks in 7.282 s (60.010/s)**. All **438 matched submissions** retire exactly one tick later. Mean submit→ready **0.003 ms**, ready→selection **11.557 ms**, selection→retire **0.010 ms**, retire→wake **0.008 ms** (maximum **0.040 ms**), wake→next submission **5.086 ms**. Zero submissions with undrained FIFO; no recycle-stall/fence-overflow warnings.
- Baseline before hash optimization also sustained 60 flips/s with drawing bypassed (`port/runs/X-baseline.log:11687,13556`); this is not a measured battle-fps improvement.
- Default Metal attempt: `port/runs/X-host.pcYFaX/run.log:96–97` confirms unavailable Metal and software fallback. Software drawing slows the hub enough that the 40-second warp does not occur; that result does not predict real Metal.

## Remaining / host check

Run **`bash codex/X.host-check.sh` on the real Mac**. It builds only build-x, copies the save, warps to stage 101, advances dialogue, and measures individual sequences after settling. Uses grep and no rm; avoids frame dumps that would distort timing. `X_SECONDS=60` extends the window; `X_PAD_SCRIPT` adjusts cold-start input timing; `D2_WARP_STAGE` selects another stage. Headless timing-only reproduction: `X_HEADLESS=1 X_FIFO_ONLY=1 bash codex/X.host-check.sh`.

The summary separates late retirement from late next-frame preparation and backend presentation cost. If real Metal remains below 60, that trace is needed to establish the remaining root cause. A host visual check is also needed to confirm actual simulation/animation speed; 60 flip requests alone do not prove it.
