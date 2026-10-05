# Task D — audio handshake and guest shader translation

Audio init now completes. The final 40-second headless run presents **404 guest frames** before a later loading mutex wait. These are software-backend presentations; this sandbox exposes neither a Metal device nor a usable CoreAudio device.

## Root causes and fixes

- `sys_spu_thread_bind_queue`/`unbind_queue` were success-only stubs. Implemented per-thread SPU queue-number bindings and a blocking receive from the real LV2 queue, including error responses and explicit cancellation wakeup.
- Lifted synth2 hit `stop 0x110` at LS `0x931C`, then repeatedly re-entered its receive stub. No event was consumed and the mailbox-reading continuation was absent from the lift. The generic detector now seeds LS `0x9320`; the lifter preserves the next PC and dispatches the continuation after the runtime services the syscall. Interpreter execution shares the same receive hook.
- SPU user-event delivery consulted only group-wide connections, ignoring `sys_spu_thread_connect_event`. Added per-thread port routing. synth2 consumes queue 2 commands and sends port `0x3A` completions to queue 1 with the LV2 source/payload and mailbox acknowledgement.
- The POSIX cellAudio loop ran at roughly 500 blocks/sec without a device (2 ms sleeps), rather than 187.5. It now uses device backpressure or a monotonic silent clock, matching the existing Windows behavior.
- D2 uses its statically linked PPU synth2/surmixer code and lifted synth2 SPU, rather than a replacement libsynth2 HLE mixer. Queue 3, key `0x8000CAFE02460300`, receives cellAudio period notifications; queue 2 is consumed by the SPU, not a missing PPU receiver. `synth2_generate` waits on queue 1 twice per block; both completions now arrive. NisAt3Line0–2 remain in their 1 ms idle sleep at LR `0x00157E60`; no cellAtrac decoding call was observed.

## Files changed by D

- SDK: `runtime/syscalls/lv2_register.c`, `sys_event.c`, `sys_event.h`; `runtime/spu/spu_channels.c`, `spu_interp.c`; `tools/find_spu_functions.py`, `spu_lifter.py`; `libs/audio/cellAudio.c`; dependency stubs in `runtime/spu/tests/test_spu_lifted_start.c`.
- Port: `spu/synth2/spu_recomp.c/.h` regenerated (561 functions); `spu/README.md`; `main.cpp` adds periodic frame counts and optional `D2_BOOT_TRACE` snapshots; `src/d2_shader_trace.cpp` and its CMake source entry add opt-in GPU-free shader validation (`PS3RECOMP_SHADER_TRACE=1`).
- Integration fixture: `codex/D.validate.cpp`, `D.validate.py`. SDK-only changes saved in `patches/D-audio.diff`.
- No edits to C's cellResc/sysutil/NP/filesystem areas, game dump, other build directories, commits or pushes.

## Verification and translator result

- Configured from `port/`, copying OPERATIONS.md's flags and using only `-B build-d`. `port/runs/D.configure.log:25`: **Shaders: guest programs translated to MSL (glslang 16.6.0, ...libspirv-cross-c.a)**. Existing CMake detection works with Homebrew; no detection patch required. `D.build.log:407` and `D-build-final.log:3`: executable linked.
- `port/runs/D-final.log:204,247`: binding queue 2 number `0x01012000` succeeds; the SPU receives the real `0x0FF60200` command. Completions continue through the final loading wait, rather than stopping at audio init.
- `D-final.log:3162,4866,6573,8296,9991,11660`: frames 60, 120, 180, 240, 300, 360. Lines 12927/17078 show 403/404 completed frames; timeout exit **142**, as expected from the alarm wrapper.
- GPU-free trace uses the SDK's existing RSX decompilers and glslang/spirv-cross translator on programs actually submitted by the guest. `D-final.log:1433,1443,1446`: VP `09744A898D08E6EB`, **3 instructions → 3410 MSL bytes**; FP `EE698541A29A9F69`, **80 → 11140 bytes**; FP `D23008EDFF283E5D`, **4 → 3198 bytes**. All translate successfully. HLSL/MSL artifacts: `port/runs/D-shaders/`. This does not establish Metal compilation or rendering.
- Existing translator regression: `D-shader-test.log:67`: **65 passed, 0 failed**. Existing SPU group regression: `D-spu-test.log:27`: **95 passed, 0 failed**.
- `python3 codex/D.validate.py` links the actual build-d runtime and game objects, replacing only main. `D-test-repro.log:20–21`: blocking command receive, four mailbox words, per-thread completion queue and cancellation **PASS**. Line 29: silent audio **187.7 Hz**, expected 187.5. It also checks wrong queue type, duplicate binding, and unbound receive errors. `git -C ps3recomp diff --check` passes.

## Where boot stops afterwards

- At approximately 15–20 seconds the frame counter stops at 404. `D-final.log:17079,21451,25859,30327`: main guest thread is inside **cellSyncMutexLock**, wrapper LR `0x00160868`, mutex EA **`0x01FF0CB8`**. The wrapper calls import stub `0x0038F418`, NID `0x1BB675C2`. The lock holder/root cause of this later wait is not established.
- `NowLoadingThread` (tid 23) remains at LR **`0x002D47E8`**, in `func_002D47BC` polling `func_002D46D0` for six loading-state flags, yielding through syscall 141. Archives progress through START/ANM, BGM, message/voice packs and `SndPakSe_0.pak` (`D-final.log:8113–8142`). Audio queues continue servicing events. Title screen/gameplay is not established.
- Earlier intro-movie failure remains: `D-final.log:265–277` reads actual `PAMF` bytes but reports unresolved cellPamf NIDs `0xCA8181C1`/`0x44F5C9E3`, then ReaderInitialize sees magic zero and returns `0x80610302`. `cellRescSetWaitFlip` NID `0x0D3C22CE` remains unresolved. These were left outside D's changes.
- A subsequent run using the shared HDD1 cache stalled earlier: `D-audio-fix.log:112–124` repeatedly finds a valid cache.idx but a zero-length cache.dat header. Successful D runs use fresh private `PS3_HDD1_ROOT` directories; no filesystem workaround was applied. This separate cache-reopen problem needs C/FS follow-up.

For another 40-second run, retain the requested VFS/HDD0/alarm command and add `PS3RECOMP_METAL_HEADLESS=1 D2_BOOT_TRACE=1 PS3RECOMP_SHADER_TRACE=1` plus a **fresh private** `PS3_HDD1_ROOT` made under `/Volumes/Data/ai-tmp/codex`. Outside the sandbox, verify the actual Metal shader/pipeline logs and visible loading frames. Native `sample` profiling was denied by the sandbox; guest snapshots supplied the addresses above. D's disposable caches, binaries and downloaded reference files were removed after verification; the large initial stalled trace is compressed as `port/runs/D-baseline.log.gz`.

Reference behavior checked with `gh`: sp00nznet/ps3recomp PR #160, Twisted Metal's repository layout, and RPCS3's `sys_spu.cpp`, `SPUThread.cpp`, `cellSync.h` for the binding, stop/mailbox/event and mutex ABI.
