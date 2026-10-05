# AK — R04 / R10 / R12

Root causes: the SDK export had no verifiable pin or generation recipe; required regression fixtures were ignored and some depended on pruned builds/profile 0; CMake overwrote explicit paths and the editor bypassed the selected SDK headers.

Changes:
- `patches/SDK.lock`: full base/revision/tree and combined patch SHA256. `tools/bootstrap_sdk.sh` clones the exact base, applies the patch, verifies the resulting tree, and rejects altered patches/existing destinations without making commits.
- `patches/LIFTS.json`, `tools/generate_lifts.{sh,py}`, `tools/requirements-lifts.txt`: verified ELF hashes, pinned Python dependencies, PPU loader/lifter commands, 50,000-line chunks, SPU extraction/lifting/constructor registration, and generation receipts. Supports external SDK/input/output directories.
- `port/tests/`: promoted asset-free Q/T/Y/AA/AB/X/AG2/Z, filesystem/EDAT/import/editor/overlay/Metal fixtures; independent SDK/schema test headers; both editor profiles; CTest plus standalone `run.sh`. GPU absence is exit 77/Skipped. Newer SDK AJ fixtures and self-contained AL fixtures register conditionally. `codex/{AB,AF}.check.sh` now forward to the supported suite.
- `port/CMakeLists.txt`: project SDK default, preserved RECOMP_DIR/D2_OUT_DIR/SPU_DIR overrides, configured system header include path and CTest registration. `port/src/d2_cheats.cpp`: selected SDK headers. `.gitignore`, `README.md`, and the operations configure line document/retain the workflow.

Verification (logs retained under `port/runs/`):

| Check | Evidence |
|---|---|
| Clean project clone + fresh upstream SDK | `AK.bootstrap-clean.log:3`: audited tree/patch PASS. Clone HEAD `3d545f7`; only AK source changes overlaid, no commit. |
| Both ELFs regenerated | `AK.lift-100.log:138`, `AK.lift-140.log:138`: SHA256 matches; 10,374/10,315 PPU functions and two SPU images each. |
| External SDK/lift paths, both builds | `AK.configure-clean-140.log:13–17`, `AK.configure-clean-100.log:1–5`; `AK.build-clean-140.log:407`, `AK.build-clean-100.log:92`: native runner linked. |
| Fresh bootstrap CTest | `AK.ctest-list.log:31`: 28 tests; `AK.ctest-clean.log:59`: all passed, comprising 26 passes and two explicit Metal skips. Fresh Python venv dependencies installed from the pinned requirements. |
| Fail-loud guards | `AK.guards.log:16–18`: altered patch, existing SDK destination, wrong ELF hash all rejected. |
| Timed pinned runners | `AK.clean-100.log:2769`, `AK.clean-140.log:2773`: guest frame 2280; both 40-second alarms exited 142, no OOB/FAULT/Bus error. |
| Current SDK additions | `AK.ctest-current.log:59–65`: AJ save/EDAT/loader tests pass (29 passes + two GPU skips). `AK.runner-failures.log:4`: synthetic runner failures pass. `AK.ctest-AL.log`: three AL CPU passes + one GPU skip. Current inventory: 36 tests. |
| SDK/version defaults + latest local run | `AK.configure-current-defaults.log:1–5`: project SDK and 140 defaults. Latest corrected 100 run `AK.log:2782`: frame 2280, alarm 142. `build-ak` is finally configured/built for 140. |

Shell/Python syntax, Git whitespace, and whitelist checks passed. No SDK runtime source, launcher/packaging source, dump, shared build, other workers' build directories, commits or pushes were changed by AK. Disposable clone/SDK/lifts and the temporary standalone test build were removed; `port/build-ak` and logs remain.

Remaining: the lock deliberately pins the supplied audited `5b24f49` patch. Concurrent AJ/AL runtime changes are newer and current main now uses APIs absent from that export. Integration must re-export the consolidated SDK, update lock checksum/tree/revision together, and repeat bootstrap for that integrated source state. AL's launcher fixture still needs self-contained synthetic content setup for CTest; real Metal checks require a host GPU. Captured replay/real-save raster diagnostics remain outside the asset-free suite.
