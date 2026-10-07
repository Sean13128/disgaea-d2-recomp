# Task BB — texture content-hash throughput (yourname = BB, build dir port/build-bb)

Context (Claude's real-Metal profile, port/runs/BA-host.kExo82/battle and BA-host.xNczbV): the game holds 60 fps everywhere; the goal is CPU/power. On the Baal battle map `eng_texture_content_hash` (ps3recomp/libs/video/rsx_draw_engine.c ~770-796, called from eng_texture_slot ~874) is the largest single RSX-thread cost: 352 of 1230 active RSX samples (~3% of a core). It is a 4-stream FNV-1a-64 over each cached texture's full guest span, once per engine frame. A prior hot-cache microbenchmark (port/runs/performance-review-20261005/texture-hash-bench.cpp, texture-hash-results.txt) measured FNV 34.4 us vs XXH3 22.4 us per MiB, but it re-hashed the same allocation (cache-hot) — not representative.

Do NOT touch: port/build or other build dirs, ps3recomp/libs/input/cellPad.c (Claude edited it; leave as is), ps3recomp/libs/video/rsx_metal_overlay.m and libs/audio/cellAudio.c (pre-existing local edits). Do not commit.

## Part 1 — measure realistically first
Extend the benchmark (new file port/runs/BB-hash-bench/, your own build line) to compare, on BOTH cache-hot and cold/realistic working sets:
  (a) current 4-stream FNV (copied unchanged),
  (b) the same FNV widened to 8 independent streams (no new dependency),
  (c) XXH3_64bits (xxHash v0.8.3, BSD-2-Clause, single header, XXH_INLINE_ALL),
  (d) optionally any other dependency-free candidate you judge strong (e.g. NEON/CRC32C-based), only if its mutation-detection quality is defensible for a 64-bit in-memory change-detection key.
Realistic working set: many distinct texture-sized buffers (mix of 16 KiB..4 MiB, total >= 64 MiB so it exceeds caches), hashed once each per "frame" in rotating order; report ns/MiB medians over >=5 paired rounds, clang -O2 (the SDK runtime is -O2). Write results to port/runs/BB-hash-bench/results.txt.

## Part 2 — implement the winner only if it is clearly faster on the realistic set (>=20%)
- Prefer no new dependency if (b)/(d) is within ~10% of XXH3. If XXH3 wins clearly, vendor the single xxhash.h into the SDK (e.g. ps3recomp/third_party/xxhash/ with its LICENSE) — do NOT depend on /opt/homebrew headers.
- Keep the function signature/semantics: same readable handling, full span, all mip levels / cube faces covered exactly as now. Hash is an in-memory cache key only (never persisted) — confirm by grep.
- Tests: extend the existing hash/texture-cache ctest fixtures so a single-byte mutation anywhere in the span (first/last byte, each mip level, each cube face, non-multiple-of-8/32 tail lengths) changes the hash and triggers re-upload; unchanged data does not.
- If nothing clears 20% on the realistic set, change nothing in the SDK and report the numbers.

## Verify
- Full ctest in port/build-bb passes (Metal tests may skip in sandbox).
- Export only your SDK changes to patches/BB-texture-hash.diff.
Report: benchmark table (hot + realistic), decision and why, files changed, tests added. Write codex/BB.report.md.
