# N — macOS app packaging

Created `port/dist/Disgaea D2.app` (~29 MB), with no game dump or decrypted ELF bundled. No commits/pushes; no dump, other build directories, pad/GCM/Resc/codec/saveData source files modified by N.

## Root causes / changes

- The port had only a CLI executable, build-local save paths, and absolute Homebrew dylib dependencies. CMake now builds an independent AppKit launcher and packages the CLI runner with its transitive dylibs, rewrites install names, and ad-hoc signs the result. SDL2 plus glslang/SPIRV-Tools are bundled; Homebrew spirv-cross is linked statically on this Mac.
- The launcher discovers the current project paths, app-relative project paths, or previously configured paths. Missing data opens NSOpenPanel pickers. Config format at `~/Library/Application Support/DisgaeaD2Recomp/config` is two UTF-8 lines: `game_root=/absolute/path/to/dump` and `eboot=/absolute/path/to/EBOOT.elf`. It checks for PARAM.SFO and a 64-bit big-endian ELF header. Config uses an atomic POSIX rename in the same directory because Foundation's replacement-directory operation was denied in the sandbox.
- `PS3_VFS_ROOT` points to the dump. `PS3_HDD0_ROOT` and `PS3_HDD1_ROOT` point to Application Support's `hdd0`/`hdd1`; working directory is also Application Support. Output goes to `~/Library/Logs/DisgaeaD2Recomp/latest.log`. Existing `port/hdd0` saves are not automatically migrated.
- Plist has the requested identifier, version, games category, high-resolution/controller flags, and minimum system version 13.0. The local dump's ICON0.PNG is padded/resized into an ICNS during the build using sips/iconutil, with a sips fallback for restricted icon encoders. Assets remain ignored.
- Metal window code now supports Cmd+F / Cmd+Ctrl+F and a resizable letterboxed Metal sublayer. Guest drawable resolution remains unchanged; compositor scaling preserves aspect ratio. No draw-engine/FIFO edits. A menu event monitor lets Cmd+Q reach Quit before the game-key monitor consumes Q.

## Files

- `.gitignore`: whitelist N's host script only; `port/dist/` remains ignored.
- `port/CMakeLists.txt`, `port/src/d2_bundle.cmake`, `d2_package.cmake.in`, `d2_Info.plist.in`, `d2_launcher_paths.h.in`, `d2_launcher.m`, `d2_icon.sh`.
- `ps3recomp/libs/video/rsx_metal_backend.m`: window/layout/shortcut changes only. Reproducible N-only SDK patch: `patches/N-window.diff` (reverse applicability checked).
- `codex/N.host-check.sh`, this report.

## Verification

- Initial complete `build-n` CMake build/package succeeded. Latest launcher also builds independently with `cmake --build port/build-n --target DisgaeaD2App`. Latest packaging step succeeded: `port/runs/N-package.log`, `verified='1'` / `Verified 2 executable files`.
- `port/runs/N-bundle-check.log`: `valid on disk`, `satisfies its Designated Requirement`, plist `OK`. `port/runs/N-dylibs.log`: no `/opt/homebrew` dependency references. ICNS is recognized by `file`; app remains ignored by git. Shell syntax checks pass.
- Required raw 40-second run: `port/runs/N.log`; exits 142 as expected from timeout, continues presenting guest frames.
- Actual bundled launcher run for 40 seconds with `CFFIXED_USER_HOME` redirected to N-owned scratch: `port/runs/N-app.log`, lines 1–4 resolve dump/ELF and Application Support hdd0/hdd1; line 1268 presents guest frame 600. Config creation and HDD1 cache creation verified. Exit 142. Metal is unavailable in this sandbox (line 99 backend init FAILED); this verifies software fallback/startup, not visible Metal rendering.

## Remaining / host check

Run `bash codex/N.host-check.sh` on the real host to rebuild and launch via LaunchServices. Check file pickers on a relocated setup, both fullscreen shortcuts, wide/tall resizing, input, audio, and save/load. The script leaves the app running.

Concurrent SDK edits currently block a fresh complete build: first `cellMsgDialog.c` had undefined `CELL_SYSUTIL_ERROR_BUSY`; latest `N-build.log` shows `<atomic>` / `<stdatomic.h>` conflicts while compiling codec C sources as C++. N did not change those files. The existing dist app uses the last successfully linked runtime and the latest launcher. `bash codex/N.host-check.sh launch-only` verifies/launches that bundle while those workers finish.

Redistribution needs rebuilding the runtime AND third-party libraries for the intended deployment target, licenses/notices, Developer ID signing/notarization, and distribution without copyrighted game assets (including the generated local icon). Although the plist declares 13.0 as requested, this Mac's current executable/SDL2 Mach-O minimum is 26.0; this local bundle does not establish macOS 13 compatibility. A release build should set `CMAKE_OSX_DEPLOYMENT_TARGET=13.0` and supply libraries actually built for 13.0.
