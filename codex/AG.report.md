# AG — macOS menus and settings

Implemented in `port/build-ag/DisgaeaD2Recomp` and rebuilt `port/dist/Disgaea D2.app`. No commits/pushes, game-dump edits, other build-directory writes, cheat-overlay edits, or codec/FIFO edits.

## Root causes and implementation

- The host exposed only Quit/fullscreen and had no settings model. Added AppKit Graphics, Window, Audio, Game and Controls menus, validated JSON loading, atomic same-directory saves to `~/Library/Application Support/DisgaeaD2Recomp/settings.json`, and remembered window geometry. UI/model work stays on main; RSX configuration and audio gain cross threads through atomics.
- Enlarging the presentation layer alone cannot increase detail. Metal now scales color/depth targets, MRTs, snapshots, viewport/scissor edges and implicit clear/blit extents at 1×/1.5×/2×/3×. Uploaded textures and guest surface metadata remain native. Live changes preserve retained color/depth/stencil contents and recreate swizzled RTT views with stable handles. Native-size readback resolves scaled targets first. WPOS is corrected through a separate host constant; texel-space texture sampling reuses the existing FP normalization helper with native dimensions.
- Draws without a declared zeta used the native display depth buffer, which is the wrong size for scaled/RTT targets. Each color target now owns a matching fallback depth buffer, included in resize migration and resource retirement.
- Host master gain/mute now run in `cellAudio.c` after guest ring consumption/clipping and before device submission. Port levels, block retirement, notifications and clock semantics remain intact.
- Presentation caps skip drawable submissions while still rendering guest commands/RTT history. T's vblank/flip retirement remains untouched. FPS reports completed RSX frames. VSync changes reach `CAMetalLayer.displaySyncEnabled` on main.

Menus include output filters, aspect, VSync, presentation caps, FPS, four window sizes, native/borderless fullscreen, topmost, geometry retention, Cmd+M mute, 10% volume steps, focus mute, import/export/open-save-folder/open-log, AF's weak Cheats hook, reset and current keyboard mapping. Borderless windows can remain key/main windows.

Import invokes the existing verified importer with `--into` pointing to the active HDD0; it uses the project `.venv` when available. The script is bundled as a resource and other Python candidates are checked for availability. Export copies a plaintext port/RPCS3 slot without overwriting a destination.

## Files changed by AG

- `port/src/d2_settings.m`, `port/main.cpp` (settings initialization/test entry only), `port/src/d2_bundle.cmake` (macOS source/resource/link setup).
- `ps3recomp/libs/video/rsx_metal_backend.m`, `rsx_draw_engine.c`, new `rsx_host_settings.h`.
- `ps3recomp/libs/audio/cellAudio.c`, new `cellAudio_host.h`.
- `codex/AG.host-check.sh`, `codex/AG.metal-test.m`, `.gitignore` (two AG test exclusions), `patches/AG-host-settings.diff` (AG-only SDK delta).

Existing/concurrent changes are retained; do not attribute the entire working-tree diff to AG.

## Verification

- Final own-directory build/package: `port/runs/AG-build-complete.log`; bundle fixup/signing succeeded. `codesign --verify --deep --strict` passed (`AG-bundle-signature.log`). Bundled importer resource exists.
- CLI and bundled runner: `AG-unit-final.log:1`, `AG-bundle-unit.log:1`: settings round-trip, malformed input, scale edges/extents and actual atomic output gain **PASS**. Optional real-host UI test exercises menu actions, focus mute and geometry.
- `AG-engine-test.log:134`: **all checks passed**; `AG-fp-test.log:53`: **36 passed, 0 failed**. Existing importer suite: `AG-import-tests.log:15`: **12 tests**, OK, one optional external-pfdtool cross-check skipped.
- Requested 40-second headless run: `AG-delivery.log:1` loads 2×/50% volume, main CFRunLoop services guest worker; `:1866` applies the live settings override; `:2290` reaches guest frame 1200. Exit **142**, expected alarm. No assertion/corruption crash. Metal is unavailable and the logged software fallback is **not** graphics verification.
- GPU regression harness compiled without warnings; `AG-metal-test.log:1`: **SKIP: no Metal device** (77). It tests actual viewport/scissor pixels, scaled/MRT/RTT resources, native upload/readback, preserved depth/stencil and matching fallback depth.
- Shell syntax, relevant diff whitespace and reverse-apply check of the SDK patch passed.

## Remaining host checks / limitations

Run `bash codex/AG.host-check.sh` on the real Mac. It uses only build-ag, isolated JSON and copied saves; checks native menus and Metal resources, captures 1280×720 vs 2560×1440 source frames, measures 2× Castle Hallway via Y's route/analyzer, and tests live scaling with a presentation-only 30 FPS cap. Visual quality, Metal shader execution, 2× throughput, physical audio controls and interactive import/export remain unverified here. The script fails clearly if the Hallway route or real Metal is unavailable; `AG_PAD_SCRIPT` can adjust the route.

A moved bundle still needs an available Python 3 with PyCryptodome for retail-save import; a Python-free importer is not implemented. Export is plaintext, not PS3 resigning. Separate movie volume and input remapping are deferred optional features. Menu-only output/scale settings target the register-file engine; the legacy vtable stays at native resolution.

Prior art inspected: [SDK macOS PR #160](https://github.com/sp00nznet/ps3recomp/pull/160), [Twisted Metal runner](https://github.com/sp00nznet/twistedmetal/blob/main/src/boot_main.cpp), existing SDK FP normalization and Metal resource-lifetime tests. Frame pacing follows T; the host route/analysis follows Y.
