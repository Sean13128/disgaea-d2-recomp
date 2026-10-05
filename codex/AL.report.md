# AL — lifecycle, diagnostics, packaging

Implemented R05/R07/R08/R09/R11, separate guest/display FPS, and debounced geometry persistence. No game-dump edits, shared-build edits, commits or pushes.

## Root causes and fixes

| Item | Root cause → fix |
|---|---|
| R05 | Close disabled rendering indefinitely; Quit terminated separately → one stop request, cancel system dialog, freeze savedata admission and await completion, stop/wait frame thread, cancel/join guest workers, tear down audio/Metal. Condition cancellation releases locks/removes stack-linked waiters; guest joins/detaches coordinate ownership. Thread/submission failures return failure. AJ's exit expression is preserved. |
| R07 | Capture always selected 1.00 and scripts masked errors → one version helper, directories before redirection, required saves/successful copy, preserved status. Expected diagnostic SIGALRM explicitly returns **142**. |
| R08 | Nil drawable retained guest records without submission → submit/reset guest work independently of host display; submission outcome gates one flip retirement. Injection: `PS3RECOMP_METAL_NIL_DRAWABLE=1`. |
| R09 | ALL packaging destructively shared one destination → explicit target, stage/fixup/sign/verify inside binary directory, locked atomic exchange, build/version/configuration-specific destinations. Failures preserve the previous app. Cross-filesystem publication fails safely. |
| R11 | Finder accepted arbitrary SFOs and empty Application Support content → validate BLUS31313, update 01.40/START_7.dat, NPUB31321 and exact 45 flags in the hdd0 actually used. Explicit bundled Install/Migrate copies external game content only; save import probes Python/PyCryptodome and explains missing dependencies. |

FPS counts actual drawable submissions separately from guest submissions. Geometry saves coalesce after 350 ms idle and flush at shutdown; persistence failure is visible.

## Files

Port: `.gitignore` (helper whitelist), `main.cpp`, `capture.sh`, `play.sh`, `run.sh`, new `script-common.sh`, `install-content.sh`; `src/d2_bundle.cmake`, `d2_package.cmake.in`, new `d2_publish.c`, `d2_launcher.m`, new `d2_content.h`, new `d2_install_content.py`, `d2_settings.m`; `port/tests/AL.*`.

SDK: `runtime/platform/guest_poll.c/.h`, new `thread_lifecycle.h`, `win32_compat.c`; `runtime/syscalls/{sys_ppu_thread,lv2_register,sys_cond,sys_event,sys_semaphore}.c`; `libs/system/sysPrxForUser.c`; `libs/video/{cellGcmSys.c,rsx_metal_backend.m/.h}`. AJ incorporated the tiny savedata admission API; AL did not edit commit/recovery logic. AL-only SDK export: `patches/AL-runtime.diff`, base `5b24f498c5e0bef82379cba3c418bb566bfb2806`; reverse-apply check passes. CTest/bootstrap registration remains AK-owned.

## Verification

- **Builds/bundles:** 140 in `port/build-al`, 100 in its owned `version100` subdirectory; both sign/verify. Distributions: `port/dist/build-al-v140-f532b04d/Disgaea D2.app`, `port/dist/version100-v100-fccaa747/Disgaea D2.app`. AK's override fix required `RECOMP_DIR=src/recomp-140` for AL's 140 build.
- **Live shutdown:** `port/runs/AL-final-stop.log:1337–1341` records request → savedata idle → workers/frame stopped, **exit 0**. Three `AL-repeat*.log` launches, 25-second movie-enabled `AL-movie-stop.log`, and relocated bundled runner `AL-relocated.log` also exit **0**. VideoToolbox itself reports unavailable in this sandbox.
- **Fixtures:** `bash port/tests/AL.check.sh port/build-al` passes scripts, cancelled guest join/detached-worker rendezvous, active-save payload preservation, active-dialog release, actual frame-clock exactly-once/no-premature retirement, close/Cmd+Q actions, wrong-title rejection, empty Application Support installation, relocated installer resources, actual installed content, and missing-DLC rejection. `AL-check.log` contains PASS evidence; Metal pixels/work/reset compile but **skip 77, no device**.
- **Real capture:** `AL-capture-tests/capture.OGnPWX/run.log` (100), `capture.FDjuYR/run.log` (140) reach guest frames and return **142**. Mismatch `capture.0CncH0/run.log:4` rejects the base ELF, **exit 1**. Fixtures also pass missing saves, failed copy/output/mktemp and runner failures.
- **Packaging/settings/sync:** `AL-package-test.log` verifies failed staging/publication preservation, atomic exchange and both signatures. `AL-settings.log` verifies dependency probes, debounce/flush and existing settings/gain tests. `AL-cond.log` passes owner/recursive/spurious conditions; `AL-sync.log` passes flip/recycle/label regressions.
- **CTest:** `AL-ctest.log`: **9 passed, 1 GPU skip**; updated join case separately passes `AL-join-ctest.log`. Both Git whitespace checks pass. Disposable AL content/fixture copies were removed; logs/builds/bundles/tests remain.

## Remaining

Real-Mac checks: injected nil-drawable GPU execution, 30-display/60-guest FPS, actual red/Cmd+Q during save/dialog, Finder/TCC first launch. Action/model/retirement/relocation paths have independent coverage above; real Finder UI was intercepted in fixtures.

Orchestrator integration: rebuild/publish the shared release, consolidate AJ/AL SDK changes and update SDK.lock together. `port/build` and default distribution were untouched.
