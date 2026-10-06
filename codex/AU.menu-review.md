# AU: menu and options review vs other recomps and ports

Read-only review, Oct 5 2026. No source, build or run changes. This compares Disgaea D2's user-facing options with mature recomps, decomp ports and emulators, and ranks what to add next.

Legend: ✅ has it · 🟡 partial / in progress · ❌ missing · n/a not applicable · † from general knowledge of the project, not re-verified this session (wiki pages behind Cloudflare could not be fetched)

---

## 1. What we ship today

| Area | Feature | Where |
|---|---|---|
| **Graphics** | Internal resolution 1× / 1.5× / 2× / 3× (real scaled targets, 2× gives 2560×1440, AG2) | `port/src/d2_settings.m:220`, AG/AG2 |
| | Output filter: Linear / Nearest / Integer scale | `d2_settings.m:225` |
| | Aspect: Letterbox / Stretch | `d2_settings.m:229` |
| | VSync toggle, presentation cap 30/60/120/unlimited, Show FPS (guest + display) | `d2_settings.m:232-236`, AL |
| **Window** | Size presets, ⌃⌘F native fullscreen, borderless fullscreen, Always on Top, remember size/position (debounced) | `d2_settings.m:237-244` |
| **Audio** | ⌘M mute, master volume steps, mute when unfocused (host gain in cellAudio) | `d2_settings.m:245-250`, AP fixed the mute-at-launch BGM stall |
| **Game** | Import PS3 save (retail PFD decrypt via `tools/d2_save_import.py`, never overwrites), Export save (plaintext, RPCS3 layout), Open Save Folder, Open Log, Cheats…, Flag Issue… (F2) | `d2_settings.m:251-259`, AC |
| **Controls** | "Keyboard Mapping…" is an **info dialog only**, fixed layout; SDL2 gamepads auto-map; no rebinding | `d2_settings.m:261,323` |
| **Cheats / editor** | F1 / ⌘⇧C overlay: HL, Mana, bonus gauge, Cheat Shop, infinite HP/SP, one-hit kills, EXP ×1–1024, free shop; characters (level, stats, aptitudes, class, skills, equipment); items (add/remove via native helpers, stats, rarity); 4 preset slots | `d2_cheats.cpp`, `codex/AF.report.md` |
| | 🟡 **AS** (in progress): cheat UI moves from the overlay to the native menu bar + AppKit windows | OPERATIONS.md, log Oct 5 |
| | 🟡 **AT** (in progress): visual Item Editor window with icons from game files | same |
| **Diagnostics** | F2 Flag Issue: screenshot, fps, worst frame, map/stage, per-thread CPU, RSS, note → `flags.jsonl` (known bug: white bands in the screenshot) | `d2_flags.m`, AN |
| **Launcher** | Validates ELF entry/TOC for the build version, installs 1.40 update + 45 DLC flags, migrate hdd0, NSAlert errors | `d2_launcher.m`, AH/AL |
| **Settings file** | `~/Library/Application Support/DisgaeaD2Recomp/settings.json`, whitelist validation + clamping, atomic write (stage, fsync, rename), `D2_SETTINGS_PATH` override, Reset Settings | `d2_settings.m:27-111` |
| **Platform** | Retina backing scale, `public.app-category.games` (macOS Game Mode in fullscreen), stable local signing identity | `d2_Info.plist.in`, `rsx_metal_backend.m:509` |

Gaps that matter: no **speed-up/turbo**, no **rebinding**, no **AA**, no **screenshot key**, no **save backups**, no **texture replacement**, no **pause**, master-only volume.

---

## 2. Comparison matrix

Columns: **D2 (ours)** · Z64 = Zelda64Recomp · UR = Unleashed Recompiled · HM = Ship of Harkinian / 2 Ship 2 Harkinian / SpaghettiKart (libultraship) · sm64ex · PD = Perfect Dark port · GOAL = OpenGOAL · RPCS3 · PCSX2 · Dolphin · DPC = official Disgaea PC releases (D4 Complete+, D5 Complete, D7)

### Graphics

| Feature | **D2 (ours)** | Z64 | UR | HM | sm64ex | PD | GOAL | RPCS3 | PCSX2 | Dolphin | DPC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Resolution scale | **✅ 1–3×** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅† | ✅† | ✅† | ✅† | ✅ native res |
| Widescreen / ultrawide | **🟡 16:9 native; letterbox/stretch only** | ✅ any AR, HUD at 16:9 | ✅ 21:9+, UI alignment | ✅ | ✅† | ✅ | ✅† | 🟡 per-game patches† | ✅ patches† | ✅ + codes | 🟡 16:9† |
| MSAA / AA | **❌** | ✅† (RT64) | ✅ MSAA >2×, alpha-to-coverage | ✅ MSAA | ❌† | ✅† | ✅† | 🟡 FSR / AA† | ✅† | ✅† | ? |
| Texture filtering (aniso/bicubic) | **🟡 output filter only** | ✅† | ✅ bicubic GI | ✅† | ✅† | ✅† | ✅† | ✅ aniso† | ✅† | ✅† | ? |
| Texture packs / HD replacement | **❌** | ✅ (RT64 packs via mod menu) | ✅ via mods | ✅ `.o2r` in `mods/` | ✅ external data | ❌ | 🟡 mods | ❌† | ✅ | ✅ | n/a |
| Frame-rate unlock / interpolation | **❌ (60 fixed; correct for D2)** | ✅ any FPS | ✅ unlocked | ✅ interpolation | 🟡 forks | ✅ up to 240 | ✅† | 🟡 patches + vblank | 🟡 | 🟡 | ❌ |
| VSync / frame cap | **✅** | ✅ manual FPS slider | ✅ | ✅† | ✅† | ✅† | ✅† | ✅† | ✅† | ✅† | ✅† |
| HDR | **❌** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡† | ❌† | ✅ (HDR post)† | ❌ |
| UI / HUD scale | **n/a (fixed 720p UI, scales with output)** | ✅ HUD placement | ✅ UI alignment | 🟡† | ❌ | ❌ | ✅† | ❌ | ❌ | ❌ | ? |
| Integer / pixel-perfect scaling | **✅** | ❌ | ❌ | ❌† | ❌ | ❌ | ❌ | ❌ | ✅† | ❌ | ❌ |

### Input

| Feature | **D2 (ours)** | Z64 | UR | HM | sm64ex | PD | GOAL | RPCS3 | PCSX2 | Dolphin | DPC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Rebinding UI | **❌ fixed map, info dialog** | ✅ in-game menus | 🟡 pad yes, keyboard "not yet" | ✅ | ✅ | 🟡 `pd.ini` | ✅† | ✅† | ✅ | ✅ | ✅ (D1 PC's was buggy) |
| Controller glyphs (Xbox/PS) | **n/a (game shows PS glyphs; correct for pads)** | n/a | ✅ PS/Xbox icon selection | 🟡† | ❌ | ❌ | ✅† | n/a | n/a | n/a | ✅ Xbox/PS4 prompts |
| Confirm-button swap | **❌** | n/a | n/a | n/a | n/a | n/a | ❌ | n/a | n/a | n/a | ✅ (D4C+) |
| Multiple profiles | **❌** | ❌† | ❌ | ✅ presets | ❌ | ❌ | ❌† | ✅† | ✅† | ✅ | ❌ |
| Gyro | **n/a** | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅† | ✅† | ✅ | n/a |
| Mouse | **❌ (menus only via menu bar)** | ✅ menus | ❌ | ✅ capture | ✅ mouse look | ✅ | ✅† | n/a | n/a | n/a | ✅ D4C+ KB+M |
| Deadzone / stick options | **❌** | ✅ | ❌† | ✅ | ❌† | ✅† | ✅† | ✅† | ✅† | ✅ | ? |

### Audio

| Feature | **D2 (ours)** | Z64 | UR | HM | sm64ex | PD | GOAL | RPCS3 | PCSX2 | Dolphin | DPC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Host mute / master volume | **✅ + mute unfocused** | ✅ main volume (v1.1.0) | ✅ | ✅ | ✅ | ✅† | ✅† | ✅† | ✅† | ✅† | ✅ |
| Separate music / SFX / voice | **❌ host; (game's own options, unverified)** | 🟡† | ✅ + music attenuation | ✅† | ✅† | ✅† | ✅† | ❌ | ❌ | ❌ | ✅† |
| Voice language | **in-game EN/JP (game feature)** | n/a | ✅ 6 languages | n/a | n/a | n/a | ✅† | n/a | n/a | n/a | ✅ |

### Quality of life

| Feature | **D2 (ours)** | Z64 | UR | HM | sm64ex | PD | GOAL | RPCS3 | PCSX2 | Dolphin | DPC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Speed-up / turbo / fast-forward | **❌** | ❌ | ❌ | ✅ speed/time savers | ❌ | ❌ | 🟡† | 🟡 frame-limit off / vblank† | ✅ turbo† | ✅ | ✅ D5C/D7 battle speed, D7 "Super" |
| Skip cutscenes / animations | **🟡 game's own skip; `D2_MOVIE_SKIP` env** | ❌ | ❌ | ✅ | 🟡 `--skip-intro` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ D7 Skip A/B effects |
| Save states | **❌** | ❌ | ❌ | ✅ F5–F7 | ❌ | ❌ | ❌ | 🟡 experimental† | ✅† | ✅† | ❌ |
| Rewind | **❌** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌† | ❌ | ❌ |
| Autosave | **❌ (game has none)** | ✅ | n/a | 🟡† | ❌ | ❌ | ✅† | n/a | n/a | n/a | ✅ D4C+ |
| Save slots / backups | **🟡 crash-safe writes (AJ); import/export; no backups** | ✅ automatic save backup (v1.1.0) | 🟡 saves preserved on update | ✅ save editor† | 🟡 text saves | ❌ | 🟡 | ✅ save manager† | ✅ memcards† | ✅ | ✅ |
| Achievements | **❌ (trophies stubbed)** | ❌ | ✅ native + notifications | ❌ | ❌ | ❌ | ❌ | ✅ trophies† | ✅ RetroAchievements | ✅ RetroAchievements (2409) | ✅ Steam |
| Mod loader / mods folder | **❌** | ✅ drag-and-drop, Thunderstore | ✅ HMM-compatible | ✅ `mods/` | ✅ | 🟡 custom levels | ✅ via launcher | ❌ | ❌ | ✅ graphics mods | ❌ |
| Cheat / trainer UI | **✅ deep editor; 🟡 AS → native** | ❌ (mods) | ❌ | ✅ cheat menu, save editor | ✅ cheats menu | ✅ Transfer-Pak cheats | ❌ | ✅ patch manager | ✅ Pnach 2.0 toggles | ✅ AR/Gecko | ✅ in-game Cheat Shop |
| Debug menus | **✅ F2 flags, env debug warp** | ❌ | ❌ | ✅ | ❌ | ❌ | ✅† | ✅ | ✅ debugger | ✅ | ❌ |
| UI style | **native menu bar + overlay (→ native windows)** | in-game RmlUi menus | in-game, game-styled | ImGui overlay + menubar | in-game | in-game | in-game + launcher | Qt | Qt + Big Picture | Qt | in-game |
| Launcher / installer | **✅ content install + validation** | ✅ ROM select | ✅ guided installer + integrity check | ✅ asset extractor | ❌ | ❌ | ✅ launcher | ✅ | ✅ | ✅ | Steam |
| Auto-updater | **❌** | ❌† | ❌ (replace files) | ✅ | ❌ | ❌ | ✅ launcher | ✅† | ✅ | ✅† | Steam |
| Crash reporting | **🟡 log + F2 flags** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌† | 🟡 logs | 🟡 | 🟡 | Steam |
| Screenshot key | **🟡 only via F2** | ❌† | ❌† | ✅† | ❌ | ❌ | ❌† | ✅† | ✅† | ✅† | Steam |
| Portable mode | **🟡 `D2_SETTINGS_PATH` env** | ✅ `portable.txt` | ✅ `portable.txt` | ✅† | ✅† | ✅† | ❌ | ✅† | ✅† | ✅ | ❌ |

### Accessibility and platform

| Feature | **D2 (ours)** | Z64 | UR | HM | sm64ex | PD | GOAL | RPCS3 | PCSX2 | Dolphin | DPC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Accessibility (TTS, remap, toggles) | **❌** | 🟡 remap | ❌ | ✅ text-to-speech (F9) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Fullscreen modes | **✅ native + borderless** | ✅ | ✅ | ✅ F11 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Retina / HiDPI | **✅** | ✅ | n/a | ✅† | ✅† | ✅† | ✅† | ✅† | ✅† | ✅† | n/a |
| ProMotion / 120 Hz pacing | **🟡 120 cap; guest 60** | ✅ any FPS | n/a | ✅† | ❌ | ✅ | ❌ | 🟡 | 🟡 | 🟡 | n/a |
| macOS Game Mode | **✅ games category** | ✅† | n/a | ✅† | ❌† | ❌† | ❌† | ✅† | ✅† | ✅† | n/a |
| Steam Deck / Linux | **❌ Metal only (Vulkan is backlog)** | ✅ Flatpak | ✅ Flatpak | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Takeaways.**
- Graphics are already at or above most ports for a 720p, 2D-heavy game. The missing items (AA, texture packs) are the ones that would show on 3D maps and sprites at 2–3×.
- The biggest gap for **Disgaea specifically** is speed. NIS added battle speed and animation skipping to every PC release, and grinding (Item World, level spam) is the core loop.
- Input is the weakest area. A fixed keyboard map with an info dialog is behind every comparable project.
- We lead on the cheat/editor and on content validation. Keep investing there via AS/AT, not in a duplicate.

---

## 3. Ranked recommendations (Disgaea D2)

Effort assumes our architecture: static recomp, AppKit menus, Metal backend, and the guest-memory bridge from AF.

### 1. Turbo / fast-forward: hold key plus toggle, 2× / 3× / 4×. **M**
- **Value:** highest for Disgaea. It speeds up Item World runs, battle animations and level grinding. The NIS PC releases ship it ([D5 Complete speed-up discussion](https://steamcommunity.com/app/803600/discussions/0/1733216893873137955); D7 has "Super" move speed and effect skips per [SeekingTech](https://seekingtech.com/how-to-speed-up-battles-in-disgaea-7/)). Emulator users get it from RPCS3's vblank/clock settings ([RPCS3 blog](https://blog.rpcs3.net/?p=1765)).
- **How:** the guest vblank is hard-coded to 60 Hz in `ps3recomp/libs/video/cellGcmSys.c:90-100` (`gcm_vblank_at`, `gcm_vblank_remaining_ns`). Scale that clock with a multiplier, and scale the guest time base / `sys_time_get_system_time` the same way. Present only every Nth flip, so Metal never has to exceed display rate. Audio: mute or drop blocks during turbo instead of resampling.
- **Risks:** ATRAC streaming refill timing (AP's fragile loop/refill path), so turbo should mute BGM decode rather than starve it. Movies (force normal speed or skip during PAMF). Some game timers may use the timebase and others vblank counts, so scale both together. Guest CPU headroom: PPU main is ~50% busy at 1×, so 3–4× may be CPU-bound on heavy maps. Expose "Max" as uncapped.
- **Best reference:** PCSX2 / Dolphin turbo hotkeys (hold + toggle, configurable %); NIS D7 for in-battle UX.

### 2. Input rebinding window (keyboard + pad), with deadzone and confirm swap. **M**
- **Value:** already on the backlog ("key remapping UI"). Every comparable project has it. Players with non-US layouts or Steam Input pads need it.
- **How:** a native NSWindow under Controls → "Configure…": a table of PS3 buttons with a "press a key" capture field. Store to `settings.json` (the same whitelist/clamp model). `pad_macos.m` reads a lookup table instead of constants. Add stick deadzone and "left stick as D-pad" toggles for SDL pads.
- **Risks:** low. Return currently maps to Cross+Start, so keep it as a bindable "combo".
- **Best reference:** Zelda64Recomp's in-game input menus ([README](https://github.com/Zelda64Recomp/Zelda64Recomp)); Ship of Harkinian's controller config ([README](https://github.com/HarbourMasters/Shipwright)).

### 3. Automatic save backups plus a "Restore Backup…" menu. **S–M** (quick-win tier)
- **Value:** high safety value. Cheats and the AT item editor write into saves, and one bad edit can wreck a 300-hour post-game file.
- **How:** AJ's save commit path already stages saves crash-safely. On each successful commit, copy the previous slot directory to `saves-backup/<slot>/<timestamp>/` and keep the last N (for example 10). Add Game → Restore Backup… listing slot, time and PARAM.SFO subtitle. Also snapshot before applying any editor batch (AS/AT).
- **Risks:** disk use is small (~1.5 MB per slot). Never restore while the game is mid-save; reuse AL's in-flight-save wait.
- **Best reference:** Zelda64Recomp v1.1.0 "automatic save backup" ([releases](https://github.com/Zelda64Recomp/Zelda64Recomp/releases)).

### 4. Anti-aliasing for 3D maps: MSAA on scaled targets, or a post-process FXAA/SMAA. **M**
- **Value:** medium-high. At 1–2×, jaggies on map geometry and unit models are the remaining visual weakness. Sprites are unaffected.
- **How:** start with a post AA pass in the presenter (cheap, no RSX-semantics risk). MSAA is the better option but touches surface resolve, readback/transfer paths and RESC conversion (AG2's territory).
- **Risks:** post AA blurs 2D UI and text. Apply it before UI composition only if the passes can be separated; otherwise make it optional and default off.
- **Best reference:** Unleashed Recompiled (MSAA beyond the original, alpha-to-coverage; [README](https://github.com/hedge-dev/UnleashedRecomp)).

### 5. Screenshot hotkey (⌘⇧S / F12) to a Screenshots folder. **S** (quick win)
- **Value:** small but frequent. Users currently have to file a "flag" to get a screenshot.
- **How:** reuse `rsx_metal_backend_capture_png` (already used by `d2_flags.m:272`). Fix the known white-band capture bug first, since it affects both.
- **Best reference:** Dolphin/PCSX2 hotkeys†.

### 6. Pause (menu + hotkey) and "Pause When Unfocused". **S–M**
- **Value:** medium. Mute-when-unfocused exists, but the game keeps running. Disgaea has no pause during enemy turns.
- **How:** gate the guest vblank/flip clock and the PPU vblank pump, using the same clock hook as turbo (#1). Building #1 makes this nearly free.
- **Risks:** SPU audio threads keep polling, so mute output while paused. Avoid pausing during saves.
- **Best reference:** emulators† (RPCS3/PCSX2 pause).

### 7. Texture dump and replacement (HD sprite/portrait packs). **L**
- **Value:** high for enthusiasts. AI-upscaled sprite packs are popular for 2D-heavy games, and this is the feature that makes 3× look like a remaster.
- **How:** the Metal backend already hashes textures (XXH3 shows up in profiles). Add `textures/dump/<hash>.png` on demand plus `textures/load/<hash>.png` overrides at upload, keyed by hash + format + CLUT.
- **Risks:** palettized/CLUT textures and atlas sub-rectangle updates make hashes unstable. Upload cost on first use. Scaled UV assumptions.
- **Best reference:** Dolphin custom textures / graphics mods; PCSX2 2.0 texture replacement ([PCSX2 2.0 blog](https://pcsx2.net/blog/2024/pcsx2-2-release/)); RT64 packs in Zelda64Recomp.

### 8. Separate host volumes: Music vs SFX/Voice. **M**
- **Value:** medium. First check D2's own in-game options (unverified here); if it already has BGM/SE/voice sliders, skip this item.
- **How:** BGM comes through ATRAC (NisAt3Line) while SE/voice go through synth2. Apply separate gains at those two mix points instead of the cellAudio master.
- **Risks:** voice may also be ATRAC, so it needs tracing per line. Keep AP's stall warnings green.
- **Best reference:** Unleashed Recompiled (per-channel volumes + music attenuation).

### 9. Unified Preferences window (⌘,) and per-slot / per-version profiles. **S–M**
- **Value:** medium polish. Menus are fine for toggles, but sliders (volume, turbo %, deadzone) want a panel. Standard on macOS.
- **How:** one NSWindow bound to the existing settings model. The menu items stay as shortcuts. AS's new AppKit windows are the pattern to reuse.
- **Best reference:** PCSX2 per-game settings over global ([PCSX2 2.0 blog](https://pcsx2.net/blog/2024/pcsx2-2-release/)); SoH presets.

### 10. Crash/hang reporter: "Last session ended unexpectedly" on next launch. **S**
- **Value:** medium. It turns silent deaths into actionable reports. The F2 infrastructure already writes JSONL.
- **How:** write a session marker at start and remove it on clean shutdown (AL's single shutdown path). On the next launch, offer "Open Log / Reveal Report", and attach the last log tail, the last F2 flag and the macOS `.ips` from `~/Library/Logs/DiagnosticReports`.
- **Best reference:** Ship of Harkinian crash reporting ([README](https://github.com/HarbourMasters/Shipwright)).

### Also considered, not recommended now

| Feature | Why not now |
|---|---|
| Save states | Very risky in a static recomp: guest threads, SPU programs, host Metal state, FIOS cache and ATRAC streams would all need serialization. RPCS3's equivalent is still experimental†. Backups (#3) cover the real need. |
| Frame-rate unlock / interpolation | The game logic is vblank-locked at 60, and the UI is 2D. There is little to gain and a lot of timing risk. |
| Ultrawide | The 2D UI and map culling are built for 16:9. This would be L effort for a fraction of users. Letterbox is correct. |
| Achievements / trophies | D2 has local trophies, but NP is scoped out (PSN rule). Ask the user before doing a local-only trophy list with macOS notifications (Unleashed style, M). |
| Mods folder (NISPACK file overlay) | Useful later for translation/text mods. It needs an FS redirect layer in FIOS/NISPACK lookup. M, low current demand. |
| Auto-updater (Sparkle) | Private repo with local builds. Revisit if the app is distributed. |
| Linux / Steam Deck | Blocked on the Vulkan backend (backlog). L. |
| RPCS3-style patch manager | Instruction patches don't apply to lifted code (AF). Community *memory-write* codes could load through the AF bridge, but that is an AS/AT follow-up, not a new system. |

---

## 4. Quick wins (≤ ~1 day each)

1. **Screenshot hotkey** (#5): reuses `rsx_metal_backend_capture_png`. Fix the white-band bug together with it.
2. **Save backup on every successful save + before each editor batch** (#3, backup half only; the restore UI can follow).
3. **Crash marker + next-launch prompt** (#10).
4. **Doc/menu hygiene:** the OPERATIONS "Controls" section still says movies "complete immediately" through the facade, but the status table says they play via VideoToolbox (`D2_MOVIE_SKIP=1` skips them). Fix that line. Also add "Open Screenshots / Backups Folder" items next to Open Save Folder.
5. **Portable mode via `portable.txt`** beside the app, mirroring `D2_SETTINGS_PATH` (Zelda64Recomp/Unleashed convention). This is a one-line check in `settings_path()` plus the saves root.
6. **Confirm/cancel swap toggle** for keyboard (D4C+ style). This is trivial once #2 lands; before that, a single boolean that swaps Z/X is enough.

---

## 5. In-progress work to account for

- **AS** (cheats → native menu bar + AppKit windows): recommendations #3 (snapshot before edits) and #9 (Preferences window) should reuse AS's snapshot/action bridge and window style rather than add new ones.
- **AT** (visual Item Editor): same backup hook. AT's icon extraction from game files is also groundwork for #7 (it touches the same texture-decode path).
- **Flag screenshot white bands:** a shared dependency of #5 and F2.

## Sources

- Zelda64Recomp README and releases: https://github.com/Zelda64Recomp/Zelda64Recomp · https://github.com/Zelda64Recomp/Zelda64Recomp/releases
- Unleashed Recompiled README: https://github.com/hedge-dev/UnleashedRecomp
- Ship of Harkinian: https://github.com/HarbourMasters/Shipwright · 2 Ship 2 Harkinian: https://github.com/HarbourMasters/2ship2harkinian · SpaghettiKart (MK64): https://github.com/HarbourMasters/SpaghettiKart
- sm64ex: https://github.com/sm64pc/sm64ex · Perfect Dark port: https://github.com/fgsfdsfgs/perfect_dark · Super Metroid (snesrev): https://github.com/snesrev/sm
- OpenGOAL FAQ: https://opengoal.dev/docs/faq/
- PCSX2 2.0: https://pcsx2.net/blog/2024/pcsx2-2-release/
- Dolphin RetroAchievements (2409): https://dolphin-emu.org/blog/2024/07 · Dolphin graphics settings: https://www.mintlify.com/dolphin-emu/dolphin/user-guide/graphics-settings
- RPCS3 FSR: https://hothardware.com/news/rpcs3-playstation-3-emulator-amd-fsr-support · RPCS3 vblank/clock scale: https://blog.rpcs3.net/?p=1765 · RPCS3 game patches (Cloudflare-blocked this session): https://wiki.rpcs3.net/index.php?title=Help:Game_Patches
- Disgaea 4 Complete+ PC (battle speed, Xbox/PS prompts, confirm swap, KB+M): https://tech-gaming.com/disgaea-4-complete-pc · Disgaea 5 Complete PC speed-up: https://steamcommunity.com/app/803600/discussions/0/1733216893873137955 · Disgaea 7 speed settings: https://seekingtech.com/how-to-speed-up-battles-in-disgaea-7/ · Disgaea PC (1) port options: https://destructoid.com/?p=203096
- D2 voice language (EN/JP) evidence: https://cdn.animenewsnetwork.com/press-release/2014-01-31/disgaea-d2-patch-now-available-for-north-america-and-europe
