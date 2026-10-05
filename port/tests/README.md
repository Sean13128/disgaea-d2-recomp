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
