# BB — texture content-hash throughput

Implemented eight-stream FNV in the shared SDK. No new SDK dependency, commits, or pushes.

## Benchmark and decision

Apple clang 21.0.0, arm64, `clang++ -O2 -std=c++17`; nine paired rounds, 16 frames each, algorithm order rotated. Thread CPU time is primary; wall medians agree closely. Realistic mode uses 160 distinct, pre-faulted buffers totaling **170.499771 MiB**, with 32 each near 16 KiB / 64 KiB / 256 KiB / 1 MiB / 4 MiB, unaligned pointers and span tails. Every buffer is hashed once per frame in rotating order. Hot mode uses the same size distribution against a shared 4 MiB allocation.

| Candidate | Hot median ns/MiB | Realistic median ns/MiB | Realistic CPU reduction vs FNV4 |
|---|---:|---:|---:|
| Current FNV4, copied unchanged | 30,605.1 | 30,420.4 | — |
| FNV8 | **17,320.5** | **17,584.1** | **42.20%** |
| XXH3_64bits v0.8.3, XXH_INLINE_ALL | 20,679.4 | 20,861.7 | 31.42% |

FNV8 clears the required 20% threshold and is **15.71% faster than XXH3** on the realistic set. Its paired realistic FNV8/FNV4 ratios range from 0.5584 to 0.5847: every round clears the threshold. Hot reduction is 43.41%. Choose FNV8: it is faster and adds no dependency. No optional CRC candidate was needed.

[xxHash v0.8.3](https://github.com/Cyan4973/xxHash/releases/tag/v0.8.3) was fetched with `gh`, pinned to `e626a72bc2321cd320e953a0ccf1584cad60f363`; header SHA256 `17973c0dc49d9854ca26caa191f0e12f7a424b68858d9a78de3860d959d85e4b`. The standalone benchmark's script fetches its header and BSD-2-Clause LICENSE into its own temporary directory. No Homebrew xxHash header is used. Reference-port inspection with `gh` confirmed Twisted Metal's separate SDK wiring; the relevant existing renderer prior art is the SDK's `rsx_live_draw.c`, which remains untouched.

Reproduce: `bash port/runs/BB-hash-bench/run.sh`. Source, build command, method and all round results are in `port/runs/BB-hash-bench/{hash-bench.cpp,run.sh,README.md,results.txt}`. Hardware sysctl queries were sandbox-blocked; the host is identified as Apple M4 in the supplied context. These are standalone throughput measurements, not a measured change in game CPU percentage or power.

## Root cause and semantics

Four FNV multiply chains limited full-span scan throughput. Eight independent accumulators process a 64-byte stripe before the existing word and byte tail loops. Seeds, odd FNV multiplier, memcpy loads and folding follow the existing implementation. A single changed byte affects one stream, whose subsequent xor/multiply steps and final folding are bijective for fixed surrounding words; this preserves single-byte mutation detection at a fixed span. It remains a noncryptographic in-memory cache key.

`rg` inspection of `eng_texture_content_hash`, `content_hash` and `last_hash_frame` in `rsx_draw_engine.c` confirmed that this hash is only stored in `eng_texture`, compared on cache hits and replaced after upload; it is never persisted. Signature, readable flag handling, address resolution, full-span limits, mip-chain/cube-face span calculation, upload semantics and once-per-frame scheduling are unchanged. Hash values change, which is safe for this transient key.

## Files changed

- `ps3recomp/libs/video/rsx_draw_engine.c`: FNV4 → FNV8 only.
- `ps3recomp/libs/video/tests/test_rsx_draw_engine.c`: exhaustive per-byte upload/reuse fixtures for short tails, pitched rows, linear/swizzled four-level mip chains, all six cube faces including alignment padding, BC1; unreadable cached spans retain their existing resource.
- `port/tests/X.hash-test.c`: expanded direct hash coverage to offsets 0–15 and spans 1–193; exhaustive full mip/cube spans and a 16,387-byte span. **316,776 individual byte mutations**, with stable hashes after restoration and zero/unreadable checks.
- `patches/BB-texture-hash.diff`: **SDK changes only**, the two video files above.
- `port/runs/BB-hash-bench/`: standalone benchmark, reproducibility notes and verification logs; `codex/BB.report.md`: this report.

No dump files, other build directories, or pre-existing cellPad/audio/overlay edits were modified.

## Verification

Configured exactly as OPERATIONS.md with only `-B port/build-bb` changed (shell brace flags expanded explicitly); `cmake --build port/build-bb -j 3` succeeds. Final incremental build also succeeds; its compiler command ends with `-O2`. `git diff --check` and reverse patch applicability checks pass. A source comparison against SDK HEAD verifies the benchmark FNV4 body is unchanged except for `noinline`.

Full suite: `PYTHONPATH="$PWD/.venv/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}" ctest --test-dir port/build-bb -j 3 --output-on-failure`.

- `port/runs/BB-hash-bench/ctest.log`: **100% tests passed out of 58**, 54 executed/passed, four Metal tests skipped; zero failures.
- Initial full run selected system Python without Crypto: three import failures only. The existing project virtualenv supplies PyCryptodome; no dependency installation or test-source workaround was needed. Initial log retained as `ctest-initial.log`.
- `port/build-bb/Testing/Temporary/LastTest.log` contains `PASS 316776 individual byte mutations, all alignments/tails, stable and unreadable inputs` and `[PASS] all 768 byte mutations re-upload; unchanged data reuses texture (4 mips, 6 faces, pitch=0)`, plus corresponding first/last/every-byte coverage for spans 17, 33, 65, 85 and 56.
- Targeted ASan/UBSan `d2.hash`, `d2.draw` and `d2.AG2-engine` also passed before the full suite (`targeted-ctest.log`).

The prescribed 40-second command with `work/EBOOT.elf` was attempted: `port/runs/BB.log:5` says `ERROR: this build requires D2 version 140 (work/v140/EBOOT.elf)`. The required configure line selects v1.40, so subsequent runs used its matching ELF. Initial matching run lacked Metal and hit sandbox VideoToolbox errors; log retained as `game-140.log`.

Matching v1.40 smoke: same command, with `PS3RECOMP_METAL_HEADLESS=1 D2_MOVIE_SKIP=1`, for 40 seconds. `game-headless.log:111` says `software fallback init OK (no Metal presentation)`, line 253 says `[D2 movie] finished cleanly (no decoded frames)`, and lines 264/278/288/460 report ordered conversion and flips. Exit 142 is the expected SIGALRM timeout. CoreAudio is also unavailable in this sandbox. This confirms boot/guest progress, not rendering correctness or battle performance.

## Remaining

Real-Metal Baal battle profiling and CPU/power comparison on the host. The microbenchmark improvement meets the implementation gate; no in-game power reduction is claimed. No unresolved implementation decision.
