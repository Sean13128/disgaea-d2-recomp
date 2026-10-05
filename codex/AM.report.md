# AM — character-menu PPU cost

Implemented SDK accessor improvements; real-Metal character-menu speed still needs the supplied host check. No commits/pushes, dump edits, launcher/packaging edits, or writes to original saves.

## Root causes and changes

- Lifted stores use external `vm_write8/16/32/64` → loader `VM_WRITE_COH` → poll notify. Successful PPU store-conditionals, SPU DMA PUT/coherency writes, cellSync CAS, and GCM GET/ref/label writes also notify. The HLE inline writers in `ppu_memory.h` only notify indirectly on coherent/reserved lines; their other writes already rely on the bounded recheck.
- Previously even an unwatched store called `ps3_poll_notify`, hashed the line, and performed sequentially consistent loads. `guest_poll.h` now checks a global waiter count inline with one relaxed atomic load. With any waiter active, a single-line store checks the line filter inline too. Only matching/crossing stores enter the original bucket/mutex/broadcast path. Windows remains a no-op.
- TLS cost came from the read poll state plus a separate store epoch, and the `PPU_SPINBT` enable cache. State is now consolidated; any store invalidates its size, preserving the rule that reads interleaved with stores are work rather than spins. Darwin stores cache the TLS object's address in a public pthread key: no TLV resolution on the normal store path. Reads retain **one** TLV lookup, rather than state plus epoch; spin-trace enable is process-wide. Removing every read TLV lookup remains open: an all-pthread-key variant slowed the mixed benchmark, so it was rejected. No private pthread layouts/reserved keys used.

## Wakeup argument and regressions

This is a **bounded scheduling hint**, not an unbounded Dekker handshake. Registration occurs under the bucket lock, before the value recheck. A matching notifier locks that same bucket; after the predicate recheck it broadcasts only once cond_wait has atomically released the mutex. If relaxed global/line filters miss a concurrent registration, or a direct HLE store never notifies, the existing **100 µs timed wait** returns and callers re-read guest memory. Actual wall latency also includes host scheduling. No notification is required to terminate the wait; guest reservation/coherency operations are unchanged.

Regression coverage: one million empty-global notifications prove zero slow calls, including a deliberately positive line filter; 1,000 registered waits verify unrelated hash-collision bypass, crossing-store wakeups with a 200 ms test timeout, and counter cleanup. Production-timeout stress races 10,000 notified/unnotified publications against registration. Loader validation additionally runs 10,000 identical read/store pairs at each width, catching false spin backoff after store-state invalidation.

## Recon (1.40 ELF checked with Capstone)

`002D11C0` is a graphics binding routine, with seven vertex-layout cases; it converts the supplied guest buffer to an RSX offset (`0039E3FC`), caches the offset/type at object `+4BC/+4B8`, binds vertex attribute formats/offsets (`002FE8FC`, methods `1740/1680`), uploads vertex-program instructions (`002FE4AC`, `0B80`), and invalidates vertex caches (`002FDECC`, `1710/1714`).

`002D295C` compares packed render-state bits with cache `+D08`, conditionally emits state changes, compares texture bindings/generations at `+CF8/+CFC`, selects shaders and vertex layout, and issues indexed/non-indexed draws. These are shared render-batch routines, not a character-stat/table scan. Their hot helper calls incur lifted guest-stack spills and scalar accessors. A native batch/helper override might help, but must preserve reserve/recycle callbacks, shader transfers, guest state, and FIFO ordering; no clearly safe whole-function replacement was established.

Prior art read with `gh`: Twisted Metal runtime patch plus repository trees for Shadow of the Colossus / Simpsons Arcade and ps3recomp PR #160. No reusable solution to this particular accessor/TLS cost found.

## Measurements

M4 arm64 Release, same production runtime/accessors, no benchmark assertions disabled. Sources: `codex/AM.notify-bench.c` and `codex/AM.accessor-bench.cpp`. Direct notifier: seven rounds of 30 million stores per case. Actual loader accessors: 14 rounds of 10 million operations, alternating before/after processes at interactive QoS. Medians:

| CPU operation | Before | After |
|---|---:|---:|
| Store + notify, no waiters | 1.681 ns | 0.290 ns |
| Store + notify, unrelated waiter | 1.698 ns | 0.427 ns |
| Production vm_write32 | 6.053 ns | 5.364 ns |
| Production vm_write64 + vm_read32 | 12.663 ns | 10.742 ns |

These are synthetic CPU timings, not a predicted menu FPS gain. Raw evidence: `port/runs/AM.notify-{before,after}.log`, `AM.accessor-{before,after}.final.log`, `AM.microbench-summary.txt`. The baseline binary is retained at `port/build-am/AM-baseline`. Intermediate all-pthread/native-TLS benchmark logs are retained separately.

Headless (`METAL_HEADLESS=1`, `RSX_FIFO_ONLY=1`, fresh HDD0/HDD1 copies per run) title runs, excluding first 15 seconds: **60.000051 → 59.999954 distinct flips/s**, 1,482 flips / 1,482 vblanks in 24.699979 s before; 1,441 / 1,441 in 24.016685 s after. Evidence: `AM.title-before.log`, `AM.title-after.log`. Matching idle hub runs (3 s after map30003 load until Triangle): **59.848151 → 59.999907 flips/s**, 392 flips / 393 vblanks in 6.549910 s before, 400 / 400 in 6.666677 s after. Menu attempts after the last Cross: **60.000206 → 59.851336 flips/s**, 402 / 402 in 6.699977 s before, 402 / 403 in 6.716642 s after. Evidence: `AM.hub-{before,after}.log`, `AM.headless-summary.txt`. Both pairs ended via alarm; headless does not reproduce the reported 22–30 FPS character-screen slowdown.

The first final hub run overlapped CTest and is excluded from the performance comparison (`AM.final.log`). Blind Triangle/Cross/Cross inputs are only a **menu attempt**; FIFO-only output cannot confirm that it is the character screen. Do not interpret its flip rate as reproduction of the real-Metal symptom.

## Files and verification

SDK (also exported as `patches/AM-runtime.diff`):

- `runtime/platform/guest_poll.{c,h}`
- `runtime/platform/tests/test_guest_poll{,_filter}.c`
- `runtime/ppu/ppu_loader.cpp`
- `runtime/ppu/tests/test_loader_validation.cpp`

Port: only my guest-poll-filter target / C language enable in `port/tests/CMakeLists.txt`; concurrent AN test additions there belong to AN. New AM benchmark sources, `codex/AM.host-check.sh`, this report, and AM logs/patch. No changes to `port/CMakeLists.txt` or the concurrent flag-tool files by AM.

Build: only `port/build-am`, version 140, requested Python/include/configure flags. **CTest: 100% passed, 42 registered tests; 38 passed / 4 Metal-device skips** (`port/runs/AM.ctest.log`; other workers added tests during this task). Strengthened poll/filter/loader checks also passed, and the filter target passed standalone CMake configuration. Direct fixture evidence: `AM.poll-filter.log` ends with “empty global fast path, 1000 registrations … PASS”; `AM.poll-stress.log` reports “10000 notified/unnotified registration races PASS”; `AM.loader-poll.log` reports “identical read/store work resets poll state at all widths”. `git diff --check` and `bash -n codex/AM.host-check.sh` clean. The initial concurrent AN compile/editor-fixture errors were fixed by their worker before these passing checks.

## Next host check

Run `bash codex/AM.host-check.sh` outside the sandbox. It rebuilds only build-am, runs CTest, compares retained baseline/current with separate save copies, automatically loads Continue, asks the operator to open the CHARACTER screen by 35 s, then records distinct flips, 5 s `sample`, CPU logs, and frame PNGs. Default duration 75 s/binary. `AM_MANUAL=0` attempts Triangle/Down/Cross/Cross; `AM_BINARY=...` measures just one binary. Inspect PNGs to verify the scene, and compare PPU/accessor/TLV self time. Copied saves are retained; the script contains no deletion commands.

Runtime 1.40 rejects the task template's `work/EBOOT.elf` (1.00), so measurements use the matching **`work/v140/EBOOT.elf`**. Disposable build/measurement material is isolated at `/Volumes/Data/ai-tmp/codex/d2-AM.tPQOxP`; game/save originals are untouched. Real-Metal menu gain and the remaining one read-side TLV lookup are not yet verified/resolved.
