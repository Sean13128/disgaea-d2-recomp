# Current build code review — 2026-10-05

The core rendering, FIFO, audio timing, and editor work has useful regression coverage. The main weaknesses are failure handling, recovery of persistent data, and reproduction of the build outside this working directory. Fix R01–R04 first; retain the existing synchronization and cache correctness checks while doing so.

This review documents findings and recommendations only. No implementation, build configuration, game dump, installed content, or personal saves were changed by this review.

**Reviewed build.** Project HEAD `270982a` plus the current uncommitted port changes; SDK HEAD `f1d2b5c` plus its local changes, based on upstream `a679051`. `port/build` is Release, game version `140`, host sanitizers disabled. The tested runner and bundled runner were built at 15:18 CDT. A source snapshot was taken at 16:00:45 CDT to keep regression checks consistent during concurrent development. The completed AI investigation and later warp, Metal fixture, and loader diagnostic changes were also inspected; the prioritized findings below remain applicable. References name functions where concurrent edits may move line numbers.

**Coverage.** Reviewed all handwritten port entry points, game overrides, cheats/editor, settings, launcher, scripts, CMake and packaging files, and the save importer. Reviewed local SDK changes and the relevant memory/ELF, filesystem/save, FIFO/RESC, draw engine/Metal/overlay, audio, input, polling, and SPU paths. Checked generated-code hook matching and both version profiles. The thousands of lifted game functions and unrelated upstream SDK modules received targeted inspection, rather than a complete semantic revalidation.

Priority meanings: **P1** = address first because it can strand data, crash startup, or prevent reproduction of this build; **P2** = functional/reliability defect with a specific trigger. Findings marked “reproduced” were exercised during this review. Static findings have an identified code path but lack a fresh UI/GPU reproduction.

| ID | Priority | Finding | Evidence |
|---|---|---|---|
| R01 | P1 | Malformed ELF segments bypass VM bounds | Reproduced SIGBUS in current runner |
| R02 | P1 | Interrupted overwrite hides the existing save | Reproduced with production commit function |
| R03 | P1 | Empty/incomplete EDAT caches can be accepted | Reproduced cache and output-error cases |
| R04 | P1 | Documented SDK patch cannot reproduce current port | Patch/API comparison |
| R05 | P2 | Closing the game window stops rendering without stopping the game | Static control-flow review |
| R06 | P2 | Runner reports success after an entry dispatch failure | Reproduced exit status 0 |
| R07 | P2 | Capture script selects the wrong executable and masks failures | Script review + runner mismatch check |
| R08 | P2 | Drawable failure retains commands while retiring the guest flip | Static presenter/FIFO review |
| R09 | P2 | Ordinary builds replace a shared distribution bundle | CMake/package review |
| R10 | P2 | Required regression fixtures are absent from clean checkouts | Git ignore checks; CTest inventory |
| R11 | P2 | Finder startup does not validate/install matching update content | Launcher/content-path review |
| R12 | P2 | Build directory overrides do not mean what their documentation says | CMake/include-path review |

**R01 — Reject malformed ELF segments before copying.** In [ppu_loader.cpp](../ps3recomp/runtime/ppu/ppu_loader.cpp), `ppu_load_elf` bounds-checks the destination using `p_memsz`, then copies `p_filesz` bytes. It never requires `p_filesz <= p_memsz`. A segment can therefore pass the check and write beyond the backed guest arena. Program-header offset addition also needs overflow-safe validation; malformed segments are currently skipped while the loader may still return a usable entry.

A synthetic ELF with a valid 1.40 entry/TOC and a second load segment at `0xDFFFFFE0`, `p_memsz=16`, `p_filesz=65536` passed `d2_elf_matches` and killed the existing runner with signal 10. This happens during loading, before game execution. The launcher checks only the entry-containing segment, so Finder selection does not prevent it.

Recommended change: validate the complete ELF before writing guest memory. Require valid machine/header/table fields, checked offset arithmetic, `filesz <= memsz`, and bounds for the actual copied range and TLS template; reject the whole file on structural errors. Validate the entry OPD/code against this lift. Add the reproduced case to the ELF suite and require a clean nonzero error instead of a signal.

**R02 — Recover interrupted save commits.** In [cellSaveData.c](../ps3recomp/libs/system/cellSaveData.c), `commit_save` moves the current slot to `.savedata-*/previous`, then moves the staged slot into place. Between those renames the visible slot is absent. Startup has no recovery pass, and enumeration skips hidden directories. Staging protects against ordinary callback failures, but an interrupted commit strands a previously good save until someone manually restores it. The save files/directories also lack durability barriers before the previous copy is deleted.

Using the actual production function through the existing savedata test fixture, killing the disposable process immediately after the first successful rename left the visible slot missing and the original payload intact only in the hidden backup. Personal saves were not involved.

Recommended change: record a recoverable transaction and restore/complete it on startup; retain the previous save until the replacement is durable. On macOS, evaluate an atomic directory exchange for existing slots, with a portable recovery path for other hosts. Test termination at both rename boundaries and after data writes, plus disk-full/restore failures. Coordinate quit requests with an active save.

**R03 — Publish EDAT caches only after successful completion.** In [edat.c](../ps3recomp/libs/filesystem/edat.c), `edat_decrypt_file_key` writes directly to the final `.dec` path and ignores `fclose(out)` failure. `edat_resolve_key` accepts any existing cache when no klicensee is supplied, without checking its decoded length or completion. A buffered write can appear successful, fail on close, and leave an empty cache that later reads trust. Concurrent keyed validation also truncates the same path that another reader may be using.

Two synthetic cases reproduced this: replacing a valid cache with zero bytes still made the unkeyed resolver return it; imposing a zero file-size limit during output made decryption return `0` and log “decrypted 12 bytes” although the output contained zero bytes. The existing 84 crypto checks still passed, because they do not cover output failure or cache publication.

Recommended change: write to a unique sibling temporary file, check all write/flush/close results and decoded length, then atomically publish it. Serialize publication per cache key and ensure readers see a completed entry. Test corrupt/truncated caches, concurrent validation/open, allocation failure, and buffered close failure.

**R04 — Export and pin the SDK state required by this port.** [README.md](../README.md) instructs applying `patches/ps3recomp-d2-macos.diff` to `a679051`. That combined patch predates the current FIFO snapshot, host settings, and editor integration. It contains none of `cellGcm_fifo_enable_snapshot`, `rsx_metal_backend_configure`, `cellAudioHostSetGain`, or `ps3_guest_frame_hook`, which the current port requires. The SDK directory is ignored by the project and is not a pinned submodule. The incremental patches have no maintained application-order manifest.

Recommended change: provide one audited combined patch for the exact reviewed SDK state, or pin a maintained SDK revision. Record base/revision and patch checksum, then test the documented bootstrap in a disposable clean checkout. Keep game data and generated lifts outside the source repository, with a reproducible generation manifest. This was already pending in OPERATIONS.md; it remains essential to reproducing the current code.

**R05 — Give window close a complete shutdown path.** In [port/main.cpp](../port/main.cpp), `frame_clock` sets `rsx_ok=0` when the message pump reports closure, but continues its infinite loop. Subsequent iterations stop draining FIFO and retiring flips. [rsx_metal_backend.m](../ps3recomp/libs/video/rsx_metal_backend.m), `pump_messages_impl`, reports the closed/hidden window through that path. The guest can remain blocked in WaitFlip or ring recycling, and the Finder supervisor waits for the child to exit. Cmd+Q uses process termination, which is a different path.

Recommended change: route window close and Quit through a shared stop request, finish or preserve any active save, wake blocking waits, and shut down/join the owned workers. Handle failure to create the frame thread and release its handle. Verify the red close button, Cmd+Q, close during a dialog/save, and repeated launch/quit.

**R06 — Propagate guest runner failure to the process.** `main` in [port/main.cpp](../port/main.cpp) prints the result of `ppu_run` but returns zero whenever the guest has not called `sys_process_exit`. The [launcher](../port/src/d2_launcher.m) displays failures only for nonzero termination status. A failed entry dispatch is therefore silently treated as a successful run.

A valid entry/TOC descriptor pointing at unregistered code produced `entry code 0x07777770 not registered` and `ppu_run returned -1`, but the process exited `0`. The launcher validator also accepted this file.

Recommended change: preserve the explicit guest exit status when present; otherwise translate a failed `ppu_run` result into a nonzero host status. Extend the launcher test with an actual runner dispatch failure so the visible error path is exercised.

**R07 — Make capture select the build's version and preserve failures.** [capture.sh](../port/capture.sh) always runs `work/EBOOT.elf`; the current build requires `work/v140/EBOOT.elf`. Running the 1.00 ELF against the current runner returned `1` with the expected version error. The script then prints “Done” and returns success. It also continues after failed temporary-directory or save-copy operations. [run.sh](../port/run.sh) similarly turns a failed runner exit into a successful `echo` result.

Recommended change: share version selection with play/run, create diagnostic directories before log redirection, require a completed save copy, and preserve the runner status. Treat an expected diagnostic timeout explicitly. Verify capture for both 100 and 140, version mismatch, missing saves, and failed output/copy creation.

**R08 — Keep guest command submission independent of drawable availability.** In [rsx_metal_backend.m](../ps3recomp/libs/video/rsx_metal_backend.m), `eng_encode_and_commit` returns early when `nextDrawable` returns nil. That return leaves `s_eng_rec_count` and staging data intact and submits no guest commands. Its caller returns through `present_guest_frame`; the frame clock then calls `cellGcmTickFlip` and releases the guest as though that batch had been submitted. Later commands can accumulate with the retained frame, exhausting record capacity or changing frame-boundary behavior.

Recommended change: submit recorded guest work even if the compositor cannot provide a drawable, and independently skip host display. Return a submission outcome to the frame clock where necessary. Add an injected nil-drawable test that checks command execution, record/staging reset, and exactly one guest retirement. A fresh GPU reproduction was unavailable in this sandbox.

**R09 — Isolate build products before replacing the distribution.** [d2_bundle.cmake](../port/src/d2_bundle.cmake) makes `DisgaeaD2Dist` an `ALL` target. [d2_package.cmake.in](../port/src/d2_package.cmake.in) sends every build directory to the same `port/dist/Disgaea D2.app`, deleting the existing bundle before copying its replacement. An ordinary default build from a diagnostic/version-100 directory can replace the shared release bundle; concurrent builds can race at that destination. A failed copy also leaves a partial distribution.

Recommended change: keep packaging an explicit target, stage within the selected binary directory, validate/sign that complete bundle, then replace the distribution as one coordinated operation. Configure distinct destinations for diagnostic builds. Test failure during packaging and two builds with different game versions.

**R10 — Make the regression suite available and runnable from a clean checkout.** `ctest --test-dir port/build -N` reported **Total Tests: 0**. Git confirms that `codex/T.sync-test.c`, `codex/AG2.fifo-test.c`, `codex/AG2.engine-test.c`, and `codex/Z.audio-clock.c` are ignored; the first is a direct input to `AB.check.sh`. `AF.check.sh` reads the version and generated header from an already-configured `port/build-af`, which has been pruned and is not created/configured by that script. Its editor fixture also hardcodes profile 0, so compiling it for 140 does not itself validate the 140 data profile.

Recommended change: track the required asset-free fixtures, put them under a maintained test directory, and register them with CTest or one supported test command. Generate test headers independently of an old worker build. Parameterize editor fixtures by game version and report GPU skips distinctly. Both editor profiles passed when explicitly selected in this review's disposable fixtures. Verify the supported test command immediately after a fresh bootstrap.

**R11 — Validate the content set used by Finder launches.** [d2_launcher.m](../port/src/d2_launcher.m) selects a matching ELF but accepts the game root merely because `PS3_GAME/PARAM.SFO` exists. It always uses Application Support's hdd0, whereas play uses `port/hdd0` and [install-content.sh](../port/install-content.sh) installs there or at an explicitly chosen destination. A fresh Finder launch therefore has no installed 1.40 update/DLC even when the project-local play setup does. The runtime overlay falls back to disc files when the update is absent, permitting a 1.40 executable with base assets. OPERATIONS.md also records that app-support content installation remained pending.

Recommended change: check the dump's title ID and the selected build's required update assets, then offer an explicit user-owned content installation/migration path into the actual hdd0. Keep game data external to the app. Add a first-launch test with an empty Application Support directory and a second test after moving the bundle away from the project. Include save-import dependency detection: the copied helper currently still requires an external Python with PyCryptodome.

**R12 — Honor build overrides consistently.** [port/CMakeLists.txt](../port/CMakeLists.txt) defaults the SDK to `port/../../`, which is the parent of this project rather than its `ps3recomp` directory. It unconditionally replaces an explicitly supplied `RECOMP_DIR` with its version-specific path even though comments, errors, and documentation advertise that override. [d2_cheats.cpp](../port/src/d2_cheats.cpp) includes SDK headers through `../../ps3recomp`, bypassing a configured external `PS3RECOMP_DIR`. This can compile against one checkout's structures and link another checkout's implementation.

Recommended change: define one consistent set of version-specific defaults, preserve supported explicit cache overrides, and resolve every SDK header through the selected SDK include paths. Otherwise remove unsupported overrides from the documented interface. Test configuration against an SDK outside the project and a lifted-source directory outside `port/src`.

**Follow-up validation after the concurrent AI investigation.** The completed [AI.report.md](AI.report.md) now explains the two earlier failures. Its source changes and retained regression logs were checked while finalizing this review; these results are separate from this review's fresh tests.

- **Battle input crash:** the old debug warp retained hub announcement sprites after their animation pack was freed. The corrected warp drains native messages before starting battle. `port/runs/AI-host.rAaqm8/driver.log` records 146 battle Cross presses over a 120-second headless run; `run.log` reaches frame 7020 without post-load null reads or OOB faults. This resolves the reproduced warp regression. Normal 1.40 stage-selector navigation and a full turn through deployment, attack, end turn, and enemy turn remain to be validated on the host. Do not infer normal-path behavior from the warp alone.
- **Metal partial-copy failure:** the test included backend and overlay implementation files in one translation unit, merging their tentative `static` queue/layer/semaphore declarations. Overlay shutdown therefore cleared the backend queue before the partial-copy test. AI namespaced those overlay globals and added an assertion that shutdown preserves the backend queue; production compiles the files separately. The previous transparent-pixel failure at 1× was a harness defect, rather than evidence about fractional filtering. GPU harness compilation passes, but execution returns **77, no Metal device** in this sandbox; the corrected pixel assertions still require a real-Mac rerun.
- **Portrait stencil:** [AH.report.md](AH.report.md) reports navigation failure before an attack portrait was reached. The stencil reset and raster tests provide useful coverage, but there is still no successful automated visual verdict for the actual ATTACK ENTRY portrait.

**Further improvements worth scheduling.** These are narrower engineering recommendations, with runtime impact still to be measured.

- **Formalize shared-state ownership.** `ppu_fs.cpp` has unsynchronized file/directory allocation tables and check/use/close paths; `cellAudio.c` uses a volatile worker-stop flag; the frame count is written with an interlocked operation and read as a plain volatile value. Add explicit atomic lifecycle state and descriptor ownership/locking, plus focused thread-sanitizer tests. Review guest control-word publication separately: an acquire fence after a plain `memcpy` read does not itself create a C/C++ atomic synchronization relationship. Preserve the current guest-memory performance when choosing the control-word solution.
- **Bound caches for long sessions.** The draw engine admits 8192 pipeline entries while Metal's pipeline/function tables cap at 4096, and failed pipeline handles remain cached. Surface/depth tables also have fixed lifetime capacities. Measure counts across many maps and long post-game sessions, report exhaustion visibly, and add safe eviction/retry where needed. Reuse the existing deferred resource-retirement pattern and retain full-byte verification of the vertex caches.
- **Report displayed and guest rates separately.** `eng_present` increments its FPS count for every guest frame even when the 30-FPS presentation cap suppresses display. The visible FPS counter can still show about 60 at that cap. Track guest flips and actual drawable submissions separately so performance measurements and the menu agree.
- **Debounce settings persistence.** Move/resize notifications synchronously serialize, write, fsync, and rename settings on AppKit's main thread. Coalesce geometry changes and persist after a short idle interval or at shutdown; keep menu application immediate. Also report persistence failure to the UI rather than retaining only a stderr diagnostic.
- **Consolidate version identity and dependencies.** Store ELF hashes, expected entry/TOC, hook profiles, and required content version in one generated build manifest. Add CMake presets for 100/140 and host sanitizers, document the SDK/tool versions and Python dependencies, and replace the stale project-template README/config examples with the actual port workflow. An entry/TOC match alone cannot establish that executable bytes match a static lift.
- **Enforce filesystem boundaries.** The three VFS translators append guest paths without a common canonical containment policy, and the disc mount does not consistently enforce read-only access. Centralize mount resolution, reject parent traversal, and protect the dump at the runtime boundary. Coordinate save import/export with active saves and prevent simultaneous writers to the same hdd0.

**Verification performed during this review.** All compilation and fixtures used disposable task storage. C/C++ regression binaries were freshly compiled with AddressSanitizer and UndefinedBehaviorSanitizer. Python crypto/import checks used the project's existing environment. The shared build and bundle were not rebuilt or repackaged.

| Area | Fresh verification | Result |
|---|---|---|
| FIFO, flip pacing, recycle/snapshot | Q, T, Y, AA, AB suites; AG2 FIFO/RESC suite | All passed |
| Draw engine and transfers | SDK draw engine; AG2 engine suite | All passed |
| Mutation/cache/fetch | X hash, AA vertex and cache suites | All passed |
| SPU | Shuffle/vector property tests; lifted image/thread-group selection | Passed; image suite 101/101 |
| Polling | 1000 registration races, collisions, crossing stores | Passed |
| System/editor overlay | AF overlay; SDK system-overlay suite | Passed |
| Editor | Explicit 1.00 and 1.40 profile fixtures | Both passed |
| Filesystem | AD update-overlay/DLC/bare-mount fixture | Passed |
| Savedata | SDK I/O and fixed-callback round trips | Passed |
| Audio timing | Z mocked-device recovery, 2-second and 30-ms stalls | Passed; 0% silent blocks, minimum gap 4.369 ms |
| Retail save import | AC synthetic PFD/import suite | 12 tests run; 11 passed, optional external pfdtool check skipped |
| EDAT crypto | AD fixture modes/corruption/wrong-key suite | 84 checks passed |
| Current runner settings | Isolated `--settings-test` | Passed |
| Current runner version guard | 1.00 ELF supplied to 1.40 runner | Correctly rejected, exit 1 |
| Metal | Current AG/AH harness compiled and attempted | Skipped, exit 77; no device |
| Build/test inventory | CTest list, ignore rules, both Git whitespace checks | 0 registered tests; missing tracked fixtures confirmed; whitespace checks clean |

The separate defect probes reproduced R01, R02, R03, and R06. They used synthetic ELF/EDAT/save data and a disposable interrupted process. No full battle playthrough, real-device GPU/audio measurement, Finder/TCC launch, relocated-machine run, or fresh complete game rebuild was performed. Earlier host screenshots and performance reports are supporting historical evidence, not new results from this review.
