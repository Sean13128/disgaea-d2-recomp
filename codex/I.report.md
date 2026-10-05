# Task I — macOS input and intro movie

Implemented keyboard/controller input and a clean movie-finished fallback. Actual movie decoding and physical-controller/visible-window verification remain outstanding.

## Root causes and changes

- Keyboard fallback existed only in the Windows backend. Added an AppKit local monitor on the Metal window, with a mutex-protected physical-key snapshot read by `cellPadGetData`. Focus loss clears keys, aliases remain independent, pressure and left-stick/D-pad reports agree, and `PAD_NO_KEYBOARD=1` disables capture. Return sends Cross **and** Start; Z/Space send them separately. Controls are documented in OPERATIONS.md.
- SDL polling treated device index as pad port and centered axes at 127. Devices now retain instance IDs, newly discovered mapped controllers fill free ports, and neutral axes are 128. macOS init/update/close run on the main queue; SDL video is not initialized. D2 imports `cellPadGetData` (0x8B72CDA1) and `cellPadGetInfo2` (0xA703A51D), not GetDataExtra. Existing Info2 reports virtual port 0 connected with standard capabilities. Added GetDataExtra forwarding for SDK completeness.
- Missing PAMF header queries silently returned success without filling outputs, causing D2 to allocate/read the wrong header buffer (magic zero). Implemented 0xCA8181C1 / 0x44F5C9E3 and the remaining missing D2 PAMF exports 0x28B4E2C1 / 0x9AB20793. Corrected sector sizes, 48-byte descriptors, coding types, VIDEO/AUDIO aggregate queries, 64-bit file-size ABI, guest-endian AVC/audio/filter outputs, and firmware error constants. The real header has AVC 1280×720 plus stereo ATRAC3plus at 48 kHz.
- The SDK has no real demux or H.264 decoder; vdec emits dummy frames and vpost performs no conversion. Added D2-only overrides for `_NisMovie_Open` (0015FD14), Play (0015F9F4), and Close (0015F680): ready state 2, then idle state 1 with success, so the unchanged IsPlaying/Update flow completes without creating codec resources. `D2_MOVIE_NATIVE=1` restores the original path for investigation. Direct lifted calls bypass the function registry, so CMake renames only the three original definitions in a build-directory copy; generated source and dump are untouched.

## Movie coverage audit

Compared EBOOT imports to the generated HLE table:

| Module | D2 imports resolved | Remaining gaps |
|---|---:|---|
| cellPamf | 8/8 | D2 metadata covered; EP/multiple-group APIs unverified |
| cellDmux | 8/10 | QueryAttr 0xA2D4189B, QueryEsAttr 0x02170D1A missing; Open/EnableEs callback ABI is also wrong and callbacks call guest addresses as host pointers |
| libvdec | 8/8 | Decoder is a stub; no AVC/MPEG-2 decoding |
| cellVpost | 1/4 | Close 0x10EF39F6, QueryAttr 0x95E788C3, Open 0xCD33F3E2 missing; existing Exec does no conversion |
| cellAdec | 8/8 | API coverage exists; no complete PAMF audio pipeline established |

These missing codecs are bypassed by the default D2 facade, not claimed implemented. `I-native-final.log:326–341` confirms real PAMF header/stream/AVC parsing; lines 342–343 still fail D2's getStreamInfo at NisMovie.cpp:258. Native playback is not working.

## Files changed

- SDK: `CMakeLists.txt`, `libs/input/cellPad.c`, `cellPad.h`, new `pad_macos.m` / `pad_macos.h`, `libs/input/tests/test_pad_macos.m`, `libs/video/rsx_metal_backend.m` (only attach/detach monitor hooks), `libs/codec/cellPamf.c` / `.h`, and `libs/codec/tests/test_pamf.c`.
- Port: `port/CMakeLists.txt`, new `port/src/d2_movie.cpp`.
- Documentation/checks: `OPERATIONS.md` Controls section, `codex/I.check.sh`, this report.

## Verification

- Configured from port with the OPERATIONS.md flags and `-B build-i`; final native executable linked (`port/runs/I-build-final.log`). No other build directory, game dump, commits, or pushes touched.
- `I-pad-test.log:7–8,13`: worker→main queue polling, GetDataExtra, synthetic NSEvents through the shared local-monitor handler, aliases/Shift/focus loss, guest-endian pressure/status, SDL without video, unmapped first joystick, controller priority, centered sticks and disconnect/reconnect: PASS. `I-pad-disabled-test.log:6–7,12` repeats with keyboard disabled: PASS. No physical pads are accessible here. WindowServer returns window number 0, so this is explicitly a synthetic event-handler test, not proof of real event-queue delivery.
- `I-pamf-test.log:8,16`: metadata/ABI tests PASS for both a synthetic fixture and the actual dis3_0.dat first sector, including 64-bit output writes and reader-buffer canaries.
- `I-final.log:290–291`: opened and finished cleanly; no NisMovie errors or unresolved PAMF imports. Lines 6791 / 9738 / 12646 / 15590 deliver Cross / Start / Down / Cross to D2 with `len=28`, each followed by release. Line 21942 presents frame 840. The 40-second run ends by alarm (142), without a native fault. Software rendering is used because the sandbox has no Metal device.
- `bash -n codex/I.check.sh` and SDK `git diff --check` pass. The script uses grep, contains no rm, and writes only build-i plus a unique log directory.

## Host follow-up

Run `bash codex/I.check.sh` on the real host, with physical controllers disconnected during deterministic tests. It requires native NSApplication event-queue delivery (exit 77 without WindowServer), tests enabled/disabled keyboard and the real header, then opens D2 for interactive keyboard and physical pad hot-plug checks. `auto` also sends timed guest pad pulses; `tests` runs regressions only. Confirm visible scene/menu response separately: shader/rendering progress and the existing cellRescSetWaitFlip 0x0D3C22CE log flood are outside this task.

Prior art: SDK Windows keyboard fallback; [ps3recomp PR #160](https://github.com/sp00nznet/ps3recomp/pull/160) main-run-loop architecture; [RPCS3 PAMF format/ABI](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellPamf.h). SDL's [JOYSTICK_THREAD](https://wiki.libsdl.org/SDL2/SDL_HINT_JOYSTICK_THREAD) hint is Windows-only; macOS uses explicit main-thread controller initialization/update.
