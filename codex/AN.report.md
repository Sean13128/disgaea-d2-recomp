AN implemented the player “Flag Issue…” tool in `port/build-an` (D2 1.40).

The missing pieces were a bookmark writer, rolling history behind AL’s FPS counters, and a nonblocking one-shot PNG API. The existing periodic game-surface dump fences the GPU and writes PPM; the compositor already preserves the presented frame. The new SDK API snapshots that preserved texture on its queue, then encodes/writes PNG on a background queue. It also works when guest flips have stopped.

Changes:
- `port/src/d2_flags.{h,cpp,m}`: F2 request, serial background JSONL/log writer, wall/launch times, 1s/10s guest/display rates and worst guest/display intervals (including an ongoing stall), guarded 1.00/1.40 map/stage reads, Mach thread CPU deltas over approximately 2s, RSS, scale/cap, screenshot path/status. Audio underruns are null because cellAudio exports no counter.
- `port/src/d2_cheats.cpp`, `port/src/d2_settings.m`, `port/CMakeLists.txt`: existing F1 input path routes physical F2; Game menu has “Flag Issue…”. The existing AppKit FPS overlay hosts “Flagged #N”. A preallocated, non-modal note panel accepts Return/Escape; the game continues running. Note/capture updates append to the original `(session, number)`; the initial bookmark is saved immediately.
- SDK `libs/video/rsx_metal_backend.{h,m}`, `rsx_metal_overlay.m`: weak per-frame hook using AL’s exact guest/display outcomes and asynchronous preserved-frame PNG API. Changes copied to `patches/AN-runtime.diff` (no unrelated worker changes).
- `tools/d2_flags.py`: readable table, top three CPU threads, notes, screenshot status; merges updates and tolerates truncated records.
- `port/tests/AN.{flags-test.m,location-test.cpp,metal-test.m,summary-test.py}`, test runner/CMake/README: registered asset-free tests. `.gitignore` retains the requested `codex/AN.host-check.sh`.

Verification:
- Release configure/build succeeded using only `port/build-an`, Python `.venv/bin/python`, version 140, and the OPERATIONS.md compiler flags. Final build log: `port/runs/AN.build.log`, “Linking CXX executable DisgaeaD2Recomp”.
- `port/runs/AN.tests.log`: 6 tests passed, 2 Metal tests skipped (77). Includes JSON/table, both versioned map readers, editor-140 and hotkey regressions. CPU C/C++ fixtures run ASan/UBSan. PNG fixture checks completion off main, preserved pixels, dimensions and BGRA→RGBA on a real device.
- `port/runs/AN.writer-evidence.txt`: JSONL escaping/nulls/failure preservation, rolling counters/current stall, Mach CPU totals, F2 repeat/up suppression PASS; final input handler measured **0.012 ms** (<5 ms).
- Required `work/EBOOT.elf` run: `port/runs/AN.log:5` correctly rejects version 1.00 for this 1.40 build. Smoke run used `work/v140/EBOOT.elf`, automatic flag at 5s, graceful stop at 12s.
- `port/runs/AN.v140.log:1336–1341`: initial flag and screenshot-status update saved. Record: launch 5.0027s, CPU window 2.0029s, RSS 498,384,896 bytes, PPU main 50.87%, RSX render 23.13%, synth2 15.20%, plus named NisGraphics/FIOS/audio threads; map/stage 0/0 at boot, scale 1, cap 60.
- Same log `:45/:78`: sandbox has no Metal device, software fallback works. FPS availability is explicitly false and screenshot status “unavailable”; summarizer displays that honestly. `:1496–1500`: clean shutdown, exit 0. Shell/Python syntax and diff whitespace checks passed.

Remaining: real-Mac PNG, note/toast, F2/menu, fullscreen and live FPS verification. Run `bash codex/AN.host-check.sh` (interactive; F2 and type a note), or append `auto` for a timed flag. The script checks files/CPU/FPS and keeps its logs; it never profiles, deletes saves, or removes variable paths. Main-thread handler timing is measured; native panel/window presentation needs this host check.

Flags live in the parent of `PS3_HDD0_ROOT` under `flags/` (the app’s Application Support directory), otherwise the Application Support default. Read them with `.venv/bin/python tools/d2_flags.py port/flags/flags.jsonl`. Nothing committed/pushed; dump, packaging, launcher, existing launch scripts, SDK accessors and AM’s guest_poll files were untouched. Concurrent AM/AO changes were left intact.
