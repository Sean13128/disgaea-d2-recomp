# S — arm64 SPU and guest-memory hot paths

Implemented in the shared SDK; no game-specific override was needed. No commits/pushes, game-dump edits, or edits to codec/overlay/savedata/pad files. Only `port/build-s` was built.

## Causes and changes

- **arm64 lacked SPU SIMD.** `spu_shufb` used the scalar byte loop while x86 already had SSE. Added NEON `vqtbl2q_u8`, using `(selector XOR 3) & 31` to select directly from host-native words while preserving SPU big-endian byte positions. All special classes remain exact: `10→00`, `110→FF`, `111→80`. Added NEON byte rotate/shift (immediate/register/bit-index forms), `cbd/chd/cwd/cdd` insertion controls, and `fm/fma/fms/fnms`. Scalar references remain available; `SPU_HELPERS_SCALAR` disables these SIMD paths for testing. Property tests caught differing scalar/vector FMA NaN payload priorities; NaN operands fall back to the reference.
- **Disabled store diagnostics were hot.** `barrier_watch_hit` is the debug write/value watch, not O's poll notifier. Outlined its reporting behind an inlined, thread-safe cached enable gate; dynamically armed `g_barrier_sync_watch` remains live.
- **Notifier buckets collided.** O already checked per-bucket waiter counts, but unrelated lines could wake waiters sharing one of 256 mutex buckets. Added a 4096-entry atomic line-count filter before bucket hashing/locking. Registration still precedes the under-lock value recheck; removal occurs under that lock. Filter collisions only add work. Rare cross-line poll reads yield/re-read instead of waiting on the first line's condition.
- **`vm_read32` carried disabled tracing buffers.** Outlined read/value/histogram/spin diagnostics behind a cached gate. Bounds checks, raw-SPU MMIO, forced reads, GCM ref publication, value tracking and poll detection retain their behavior. ARM64 disassembly shows the normal read stack frame shrinking from **2464 to 64 bytes**.

PPU-main sample inspection: frame update `func_0006810C` contains the work; render submission `func_002EE4D8` accounts for 1043 inclusive stack samples, `func_002EC964` for 890 (includes its explicit 30µs syscall wait). No guest leaf was comparable to the shared helpers: `spu_shufb=1678`, debug write watch `=665`, `vm_read32=402`, `ps3_poll_notify=293` (Q's collapsed leaves). The hot synth2 `00006280` loop directly uses rotate/shuffle/two FMAs. Existing bounds checking already inlines; it was retained.

## Files

SDK:
- `runtime/spu/spu_helpers.h`
- `runtime/spu/tests/test_spu_shufb.c`
- `runtime/spu/tests/test_spu_vectors.c` (new)
- `runtime/platform/guest_poll.c`
- `runtime/platform/tests/test_guest_poll_filter.c` (new)
- `runtime/ppu/ppu_loader.cpp`

Project: `codex/S.host-check.sh`, this report, `patches/S-perf.diff`, and one `.gitignore` allowance for the host script. SDK patch includes both new tests.

## Verification

Release build: `codex/S.build-before.log`, `codex/S.build-after.log` (target `DisgaeaD2Recomp`).

- `codex/S.shufb-test.log`: `ok (4096 exhaustive selectors + 200000 random cases)`; every selector in every output lane, with distinct source bytes.
- `codex/S.vectors-test.log`: `SPU vectors ... PASS` for 200000 cases, every byte count/alignment, arbitrary float bits and 3375 FP edge triples (signed zero, subnormals, infinities, quiet/signaling NaNs). Tested optimized C, C++ and forced scalar. x86 SSE variants also compile.
- `codex/S.helpers-test.log`: `63 passed, 0 failed`.
- `codex/S.sanitizers.log`: shuffle/vector properties pass ASan + UBSan.
- `codex/S.poll-test.log`: O's bounded/changed-before-wait/notified/unnotified cases PASS. New filter test passes 1000 registration races, unrelated bucket collisions, crossing stores and prior publication; test waits extend to 200ms so the normal 100µs timeout cannot hide a lost wakeup.
- `port/runs/S-watch-smoke.log:10,16`: `[RVAL] ... 0x003FDE60`, `[wv] ... 0x3FDE60`. `port/runs/S-watch-window-smoke.log:14`: `[ww] 0x0FEFFF18 ...`. Both 40-second diagnostic runs terminate by alarm, confirming enabled watches still operate.
- `git diff --check` passes in both repositories. No crashes/SPU unsupported-op messages in the loaded-map runs.

## Measurements

Identical copied saves, `75:0x4000`, Cross every 4 seconds, movie skip, headless savedata, directory `NPUB31321_NORMAL_00`. Load/map evidence: before `map.log:4143,4168`; after `map.log:4155,4180` (`LOAD complete` and `Data/MAP/mp300/map30003.lzs`). Measured 105–135s in 140s runs:

| Sandbox software drawing | Guest fps | CPU (getrusage) |
|---|---:|---:|
| Before: `port/runs/S-before-20261005-032043` | 11.97 | 157.1% |
| After: `port/runs/S-after-20261005-032751` | 11.97 | 128.1% |

**29 percentage points / 18.5% less CPU at the same throughput.** Sandbox Metal initialization fails and falls back to software drawing; these fps values do not predict visible Metal speed. Sandboxed `ps` reports zero CPU, so the reliable CPU values come from `[HOSTCPU] process=` (seven intervals from ~105s). Sandbox `sample` cannot inspect the process; its failure is retained in each `sample-command.log`.

A separate **FIFO-only** post-change run (`port/runs/S-after-fifo-20261005-033249/summary.txt`) sustains **59.93 guest fps / 59.97 flips/s at 58.1% CPU**. Load/map evidence: `map.log:6511,6535`. This diagnostic bypasses drawing (`S_FIFO_ONLY=1`), so it demonstrates guest execution headroom, not visible Metal throughput. Its initial 40s overlapped the watch smoke run; the reported 105–135s window was isolated.

`codex/S.microbench.log` (5M dependent operations, indicative): shuffle 8.58→4.66 ns/op; rotate 6.51→4.21; FMA 4.92→4.56. Disassembly confirms a two-register NEON `tbl` and no common-path `barrier_watch_hit` call.

## Real-Mac check / remaining

Run `bash codex/S.host-check.sh`. It builds only `build-s`, copies saves into unique task scratch storage, measures fps and CPU, captures an 8-second macOS sample at 115s, and writes `port/runs/S-host-*/summary.txt`. Uses `grep`, no `rm`; real Metal drawing is enabled by default. Save copies are retained.

For a matching host baseline first: `S_SKIP_BUILD=1 S_BINARY=port/build-s/DisgaeaD2Recomp.before S_LABEL=host-before bash codex/S.host-check.sh`. Then run the default script.

**Visible 56→60 fps and post-change Metal leaf distribution remain to be measured on the real Mac.** The baseline executable is retained in `build-s/DisgaeaD2Recomp.before`.
