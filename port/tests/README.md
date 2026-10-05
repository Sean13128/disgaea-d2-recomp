# Asset-free regressions

Run `ctest --test-dir port/build --output-on-failure` after configuring the port,
or run independently of game files and lifts:

```sh
PYTHON="$PWD/.venv/bin/python" port/tests/run.sh "$PWD/ps3recomp" /absolute/path/to/new-test-build
```

Use Python dependencies from `tools/requirements-lifts.txt` and the documented
native build dependencies. Each CTest entry compiles its fixture in a separate
test build directory and preserves `build.log`. CPU C/C++ fixtures use ASan and
UBSan. No test reads the game dump or personal saves. Synthetic files are created
in test build directories or fixture-owned temporary directories.

Coverage: Q/T/Y/AA/AB FIFO ordering, flip pacing, recycling and snapshot queues;
AG2 FIFO/RESC ABI and engine transfers; X mutation hashes; AA vertex conversion
and cache correctness; Z audio recovery after 2-second/30-ms stalls; update/DLC
filesystem mounts; EDAT authentication/corruption; synthetic retail save import;
SDK save round trips, polling and SPU vector/shuffle properties; overlays;
editor bounds, presets and hooks for both executable versions; host hotkeys;
Metal scaling, partial copies and panel composition.

Editor fixtures generate `ppu_recomp.h` from the selected SDK's asset-free
header preamble and `d2_cheats_data.h` from the tracked schema/template. They do
not depend on old worker builds. GPU checks return 77 when Metal is unavailable
and CTest reports **Skipped**; failures on an available GPU remain failures.
The importer's optional pfdtool cross-check is a unittest skip when that external
tool is absent. Set `AC_PFDTOOL` to enable it.

These fixtures were promoted from worker experiments under `codex/`; this is the
supported regression entry point. `AA.replay.c`/`AA.replay-drain.c` are retained
as diagnostic helpers for private packet captures, which contain game data and
are intentionally outside the asset-free suite. Save-callback extraction and
rasterization using real saves are likewise host diagnostics, not clean tests.

New SDKs also register their savedata transaction and EDAT cache failure fixtures
when present. Game builds register the SDK loader validation fixture against
that build's runtime library; 1.40 builds also register synthetic runner failure
checks. These additions require the usual `cmake --build ... --target
DisgaeaD2Recomp` before CTest, and do not read real ELFs during testing. The locked
5b24f49 export predates these new SDK fixtures.

Issue bookmarks: `ctest --test-dir port/build-an -R 'd2.AN-' --output-on-failure`
covers JSONL writing, the table summarizer, rolling guest/display rates, Mach CPU
sampling, versioned map/stage reads, and asynchronous PNG capture (skip 77
without Metal). Run `bash codex/AN.host-check.sh` on the real Mac for F2/menu,
note and toast verification; `auto` creates a timed bookmark. Read captured
bookmarks with `.venv/bin/python tools/d2_flags.py port/flags/flags.jsonl`.
Each `flag` line is complete immediately; `note` and `screenshot` lines update
the same `(session, number)` without rewriting history.

AP audio regressions: `ctest --test-dir port/build-ap -R 'd2.AP-' --output-on-failure`
covers output-only gain, delayed SurMixer queue publication, same-handle ATRAC
switches, disjoint seek/prefetch ranges, looping EOF queries, and warnings.
`codex/AP.atrac-check.py <scratch-directory>` repeats streaming checks with the
three real BGM files read from the dump (ASan/UBSan; outside asset-free CTest).
`bash codex/AP.host-check.sh` checks CoreAudio on copied saves.
