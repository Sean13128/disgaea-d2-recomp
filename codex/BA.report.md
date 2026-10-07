# BA — clean profiling build

- Build OK: configure and `cmake --build port/build-ba -j 4` both exited 0. Fresh Ninja build, Release, version 140, `src/recomp-140`, project venv Python, and all four requested Homebrew include flags.
- ctest: **54 passed, 4 skipped, 0 failed**; exit 0, 44.65 seconds. Skipped: `d2.AN-metal`, `d2.metal`, `d2.metal-overlay`, `d2.AL-metal` because no Metal device was available in the sandbox.
- Binary SHA256: `2d15142b555f818e952a034a3f874cca4b7c28042aceb2d0b721c2982e72599a`.
- Root HEAD: `0d3238eb6bec64c57c233fc9afa486c96b6f52a5`.
- SDK HEAD: `fec80283ea16abe5e642248f94b009586ffc3358`. Recorded SDK diff: existing changes in `libs/audio/cellAudio.c` and `libs/video/rsx_metal_overlay.m` (33 insertions, 1 deletion).

Evidence: `port/runs/BA-configure.log:15` selects 140; lines 47–48 confirm configuration/generation. `port/runs/BA-build.log:442` links `DisgaeaD2Recomp`. `port/runs/BA-ctest.log:119` reports no failures; lines 129 onward list the four skips. `port/build-ba/Testing/Temporary/LastTest.log` records the missing Metal device. HEADs, SDK diff stat, and binary hash are saved in `port/runs/BA-build-info.txt`.

Root causes/fixes: none; build-only task. Files produced: `port/build-ba/`, the four requested `port/runs/BA-*` logs/metadata, and this report. No source, patch, SDK, dump, other build directory, commit, or push was modified by BA. Remaining: real-host execution of the four GPU tests; no game run or deployment was requested or performed.
