# AO — synth2 CPU cost

Implemented shared SPU optimizations; no commits or pushes. Used only `port/build-ao`. The dump, user saves, `port/build`, AM's guest-poll/PPU files, and other workers' builds were untouched.

**Root causes and changes**

- Lifted leaf loops wrote every intermediate value to `ctx->gpr`. LS calls/probes and a potentially aliasing LS pointer prevented useful compiler promotion. `tools/spu_lifter.py` now keeps leaf registers in locals and spills written registers on every exit/transfer. Functions containing calls, channels, traps or tracing remain uncached. LS diagnostic/policy gates select the original body, preserving diagnostic register visibility. `--no-register-cache` provides reference emission.
- Clang's scalar-loop/union lowering produced unnecessary 64-bit add/mask sequences and deinterleaved endian loads. Explicit NEON word arithmetic, immediate comparisons, halfword arithmetic shifts, and quadword BE loads/stores retain lane semantics. Normal LS helpers use the same data helpers after their existing diagnostics.
- FMA checked three input vectors for NaNs before each operation. The new path checks the result once and recomputes NaN results with the original scalar reference. The reference contract is host `fmaf`, including NaN payloads; hardware SPU extended-FP behavior was not substituted.
- Ordinary audio transfers resolved Darwin TLS for a policy-only recent-PC ring and for the stack-reset armed flag. The ring now records policy transfers only; stack reset accesses TLS only after matching a registered target. Trampoline TLS remains.

**Files**

SDK: `runtime/spu/spu_helpers.h`, `spu_context.h`, `spu_channels.c`, `spu_drain.c`, `tools/spu_lifter.py`, and three new `runtime/spu/tests/test_spu_{register_cache,vector_lanes}.*` fixtures. Export: `patches/AO-runtime.diff`.

Port/tooling: `.gitignore` (allow AO host script), `tools/generate_lifts.py`, `patches/LIFTS.json`, `port/tests/{CMakeLists.txt,run.py,repro-test.py}`, `port/tests/AO.synth-bench.{c,py}`, `AO.bench-compare.py`, `AO.audio-compare.py`, and `codex/AO.host-check.sh`. Generated `port/spu` and `port/spu-140` were recreated through the documented generator, never hand-edited.

Generation used `PYTHON="$PWD/.venv/bin/python" tools/generate_lifts.sh --version all --spu-only --allow-sdk-worktree --port-dir port/build-ao/regenerated-verified`. The explicit development option records SDK HEAD/diff SHA256; ELF hashes and stale-extraction checks remain mandatory. Default release generation still enforces SDK.lock. Both final regenerated source trees matched the built trees byte-for-byte (`port/runs/AO.generate.log`).

**Measurements and verification**

Exact generated bodies for the four sampled kernels execute synthetic inputs without continuing into the next guest function. Hashes cover all registers, all LS bytes and exit PC; mixer PCM is hashed separately. Five alternating paired trials, 300,000 calls/kernel, process CPU clock:

| Kernel | Before ns/call | After ns/call | CPU reduction |
|---|---:|---:|---:|
| 6280 stereo mix, 64 iterations | 396.6 | 243.6 | 38.6% |
| 24E0 scale, 256 iterations | 2127.2 | 1267.1 | 40.4% |
| 0D88 clear, 256 iterations | 1693.6 | 1017.9 | 39.9% |
| 1010 interpolation step | 14.8 | 14.9 | -0.7% |

Evidence: `port/runs/AO.bench-summary.txt` and its `.json` trials. State hashes, respectively: `b8035e397b1451c5`, `f2b447a7e5cdffb6`, `3dba4a73ae2e312f`, `83af0d04272ad70a`. Stereo PCM (16 × 256-frame cases): **`f7bf718f4c2883b3`** in baseline, 140 and 100. `AO.hash-check.txt:6` and `AO.hash-check-100.txt:6`: `PASS: bit-identical synth PCM/register/LS/exit hashes versus reference`.

`port/runs/AO.ctest.log:91`: **100% tests passed out of 44** (40 passed; four GPU tests explicitly skipped without Metal). Includes SPU vectors/shuffle, audio-clock, 1,600 randomized cached/reference LS/GPR cases with wrapping/branches/returns/diagnostic gates, and 100,000 SIMD lane/LS cases. Scalar helper variants also passed. The final first-use diagnostic-gate fixture adjustment passed again (`AO.cache-final.log`).

40-second baseline/final headless 140 runs used independent hdd0/hdd1 copies, `PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00`, and identical valid `PAD_SCRIPT='12:0x4000,18:0x4000,24:0x4000'`. Used `work/v140/EBOOT.elf`, matching the 140 runner. Both ended by alarm (142), loaded the save, and had no SPU unsupported/unregistered/OOB/fault diagnostics. Final log: `AO.final.log:1926` LOAD complete; `:1944`, `:2048`, `:2099` report 187.5 blocks/s and 0% silence.

Raw AUDIO_WAV is f32le, not a WAV container. Whole-file SHA256 differs:
- baseline: `f96de31efb8d0b300d21532dc47c90681271414ff39bf870a33d0ecf6a5bd7f9` (7,440 blocks).
- final: `b5c5c2e129c40caa56fad6196e78e8841f99987c92a20780f369e77562f8e73d` (7,460 blocks).

`AO.audio-compare.txt` finds **4,200 exactly matching nonzero blocks in order**, including **2,516 consecutive blocks / 13.419 seconds**. Different wall-clock startup/gap/fade placement prevents claiming whole-capture identity. Deterministic fixture PCM/LS identity is established; complete game-output identity is not.

**Remaining**

Run `bash codex/AO.host-check.sh` on real Metal with other builds idle. It compares the preserved baseline/current binaries, copies saves into unique scratch directories, captures each synth thread sample at 30–35 seconds, and retains all evidence without deleting variable paths. The **<25% of a core target is not established** by kernel timings; further optimization may be needed after the host sample. Include AO's patch when the combined SDK export/SDK.lock is refreshed.

Prior art inspected with `gh`: the reference ports' SPU/audio inventories, Twisted Metal's extractor/workload tooling, and [ps3recomp PR #160](https://github.com/sp00nznet/ps3recomp/pull/160). Existing NEON rotate/shuffle implementations were reused.
