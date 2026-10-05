# Disgaea D2 → native macOS — Operations Log

**Goal:** Disgaea D2: A Brighter Darkness (PS3, BLUS31313) running natively on this Mac (Apple M4, arm64) through static recompilation.
**Approach:** [sp00nznet/ps3recomp](https://github.com/sp00nznet/ps3recomp): lift the PPU code to C++, link it against the HLE runtime, and render RSX through Metal.
**Repo:** https://github.com/Sean13128/disgaea-d2-recomp (private). The whitelist `.gitignore` excludes game files, decrypted ELF, lifted code, logs, and saves. SDK changes go in as `patches/*.diff`. Nothing is pushed until the user reviews the file list.
**Agents:** Claude (orchestrates, reviews, integrates). Codex `gpt-6.1-sol` (`codex exec`) handles the heavy investigation and fix tasks in the background.

## Scope rules (from user)
- **Sony networking (PSN/NP/TUS/score/trophy servers, sys_net sockets) is out of scope.** These get dummy/offline handlers only; don't spend worker effort making them functional.

## Standing practices
- **Profiling pass after each major merge batch** (user request): `sample $(pgrep -x DisgaeaD2Recomp) 8`, read where the guest threads wait or work, log findings here with CPU% and fps, and assign the top issue to a worker. Samples are kept in `port/runs/*profile*`.

## Usage budget (check `agent-usage` before every Codex launch)
- **Codex must keep ≥10% for the user until the Thursday Oct 9 4:10pm CT reset.** Hard stop for new workers at **≤15% left**. Per-worker cost is measured from the before/after readings below (the user notes A–C cost ≤1% each; most of the 15% was used before this project).
- Claude weekly limit resets Oct 8 3pm CT.

| When | Codex left | Claude 5h / weekly left | Note |
|---|---|---|---|
| Oct 4 10:13pm | 85% | 85% / 65% | baseline (A–C ≤1% each per user; most usage predates the project) |
| Oct 4 ~10:40pm | 84% | – / 65% | after C finished, D running |
| Oct 4 ~10:50pm | 84% | 82% / 65% | after D; launching E, F |
| Oct 4 11:05pm | 82% | 80% / 65% | after F; launching G, H (E running) |
| Oct 4 11:15pm | 81% | 77% / – | after E, G; H, I running |
| Oct 4 11:50pm | 81% | 75% / – | after H, I; launching J |
| Oct 5 ~12:00am | 80% | – | user OK'd more parallel workers; launching K, L, M, N |

---

## 📊 Progress dashboard (updated Oct 4, 11:55pm CT)

**Overall: ~80% of the way to "playable start to finish"** (12 of 15 checkpoints done; see below).

### Code translation
| Metric | Done | Total | % |
|---|---:|---:|---:|
| PPU (main CPU) functions lifted to C++ | 10,374 | 10,374 | 100% |
| SPU (co-processor) programs lifted | 2 (713 functions) | 2 | 100% |
| Firmware functions D2 imports that have a handler | 277 | 305 | 91% |
| Firmware libraries fully covered | 12 | 26 | 46% |
| **Unhandled firmware calls the game actually hits at runtime** | **1** (`cellRescSetWaitFlip`, 78×/run) | – | – |

The 28 unhandled imports are mostly PRX loaders, sockets, keyboard, the movie codecs and text conversion. The game has not called them in any run so far. Only `cellRescSetWaitFlip` is hit, and it's a suspect for the hang (Codex J).

### Game-flow checkpoints (verified on real Metal)
| # | Checkpoint | Status |
|---:|---|---|
| 1 | Boots natively (CRT, threads, FS, GCM, audio init) | ✅ |
| 2 | Loading screen renders (Prinny "NOW LOADING") | ✅ |
| 3 | NIS / Disgaea D2 logos | ✅ |
| 4 | Title menu | ✅ |
| 5 | New Game → story intro text | ✅ |
| 6 | First in-engine 3D map scene (Flonne) | ✅ |
| 7 | Cutscene dialogue advances with input | ✅ (scripted); Laharl meteor cutscene reached (`milestones/cutscene-laharl-meteor.png`) |
| 8 | A human plays with keyboard/gamepad in the live window | ✅ user skipped the meteor scene with △ via keyboard |
| 9 | Free movement in the castle hub | ✅ user walked the hub after Continue ("full speed" until the next room) |
| 10 | First battle (grid, attacks, enemy turn) | ✅ **user entered a battle on real Metal: map, units, HUD render correctly** (`milestones/first-battle-user.webp`). Minor: ATTACK ENTRY portrait drawn on a white box (Codex V) |
| 11 | Save game | ✅ user saved in-game (`NPUB31321_NORMAL_00`, 1.5 MB SAVEDATA.DAT, RPCS3 layout) |
| 12 | Continue / load save | ✅ restart → Continue → `LOAD complete` → castle hub |
| 13 | Menus, shops, Item World | ⏳ |
| 14 | Stable 60-minute session | ❌ crash ~6.5 min / hang (Codex J) |
| 15 | Movies play (intro FMV) | ✅ intro movie plays fully via VideoToolbox |

### Subsystems
| Subsystem | State |
|---|---|
| Graphics (RSX → Metal, guest shaders → MSL) | ✅ title/story/map correct |
| Audio (synth2 SPU + ATRAC3plus → CoreAudio) | ✅ BGM decodes, CoreAudio output |
| Input (keyboard + SDL gamepads) | ✅ scripted; 🟡 human test pending |
| File system / FIOS cache / saves dir | ✅ (save/load untested) |
| PSN / online | ✅ reported offline cleanly |
| Movies (PAMF/H.264) | ✅ VideoToolbox |
| Stability | 🟡 crash fixed and verified (7.5 min clean); the lldb-only hang did not recur |

### Performance and stability
| Metric | Value |
|---|---|
| Frame rate (real Metal, M4) | ✅ title 60.0 · battle 60.0 · **Castle Hallway (heaviest, ~800 draws) 59.99** · 1 flip per vblank |
| CPU use (game process) | **~70% on the map** after S (was ~700%) |
| Game speed | ✅ full speed everywhere measured (title, castle, hallway, battle) |
| Memory (game process) | ~640 MB (system at 12/16 GB incl. workers) |
| Longest verified run without crash | **450 s (7.5 min), ended by timer: no crash, no corruption, no hang** |
| Build time (incremental / full lifted code) | ~25 s |

### Effort to date
| Metric | Value |
|---|---|
| Codex workers dispatched | 21 (A–R, K2–K4); R running |
| SDK patches (local, upstream candidates) | 14 |
| Codex budget left | 81% (stop ≤15%) |

---

## Current status
| Milestone | State |
|---|---|
| EBOOT decrypted | ✅ `work/EBOOT.elf` |
| Runtime builds on macOS arm64 | ✅ (needed PR #206 + Homebrew include path) |
| D2 lifted (10,374 funcs, 21 chunks) | ✅ `port/src/recomp/` |
| Native arm64 binary links | ✅ `port/build/DisgaeaD2Recomp` (~25 s build) |
| Boots: CRT, threads, cellGame, NP, FIOS, GCM init, Resc, file reads | ✅ |
| RSX FIFO drained / Metal window | ✅ (Codex A) guest runs on a worker thread, main thread services the macOS run loop. Verified on the real host: window opens on the M4, host triangle test OK |
| Guest shader translator (glslang + spirv-cross) | ✅ guest VP/FP translate to MSL; Metal pipelines compile on the real host |
| Audio init (synth2/cellAudio/ATRAC) | ✅ (Codex D) synth2 SPU ⇄ PPU event/mailbox protocol works; silent audio clock at 187.5 Hz |
| Guest frames on real Metal | 🟡 **first real art:** Prinny "NOW LOADING" sprite renders and animates (`port/runs/milestones/first-frame-now-loading.png`). ~53 fps, 3,180 frames/60 s with no stall. Later scenes fixed by Codex G |
| Audio output | ✅ ATRAC/synth2 decode + CoreAudio; **choppy-audio fix (W): 0.04% silent blocks** |
| Loading progress | ✅ (Codex E) stable: 4/4 runs × 55 s keep presenting (~2,500 frames), no SPU faults, reused cache OK |
| Input (keyboard/gamepad on macOS) | ✅ (Codex I) AppKit keyboard monitor + SDL2 gamepads on main thread; scripted input verified on real Metal |
| New Game → story → in-engine map | ✅ real Metal, scripted input (`port/runs/milestones/story-intro.png`, `ingame-flonne-garden.png`) |
| Stability in long play | ❌ host memory corruption → SIGSEGV in pad_poll_sdl2 at ~6.5 min; timing-dependent GCM ref hang (Codex J) |
| Intro movie (PAMF) | ✅ **plays in-game on the real Mac**: 2,793/2,793 pictures, 2,733/2,733 audio blocks, full 296 MB stream, clean close. Movies are on by default again (`D2_MOVIE_SKIP=1` to skip) |
| NisGraphics + synth2 SPU lifted | ✅ `port/spu/` (152 + 560 funcs); 6 NisGraphics threads run and DMA-poll for work |
| synth2 SPU audio | ✅ running |
| Title screen | ✅ **D2 logo → full title menu (New Game / Continue / Settings) on real Metal, ~52 fps** (`port/runs/milestones/title-screen.png`) |
| Playable | ⏳ |

## Layout
```
Disgaea D2-RE/
  Disgaea D2 A Brighter Darkness - [BLUS31313]/  game dump (read-only, never modified)
  Disgaea 4 Complete+/       Steam PC build (x64 reference)
  work/                      EBOOT.bin/.elf, RECON.md, strings, logs
  ps3recomp/                 SDK checkout (local patches below)
  port/                      the D2 port: CMakeLists, main.cpp, stubs.cpp, src/recomp, out/, runs/, hdd0/
  port/run.sh [secs] [name]  build + run with a timeout -> port/runs/<name>.log
  .venv/                     Python tool deps
```

## Local patches to the ps3recomp SDK
1. **PR #206** (upstream, still open): only pass `-msse4.1` to compilers that accept it. arm64 clang rejects the flag.
2. `tools/ppu_lifter.py`: `PS3RECOMP_CHUNK_LINES` env var overrides the 600k-line chunk size (we lift with 50k so builds run in parallel within 16 GB of RAM).
3. `runtime/ppu/ppu_sysprx.cpp` `sys_lwcond_create/wait`: corrected the `sys_lwcond_t` layout to 8 bytes (be32 lwmutex at +0, be32 queue id at +4). The old code wrote a be64 at +0, which left the 32-bit word FIOS checks at 0 and caused an endless "wait for invalid cond 'fios worker cond'" loop. It also wrote past the end of the struct at +8. Twisted Metal and Shadow of the Colossus ports hit the same bug. **Upstream candidate.**

Build configure line (Homebrew SDL2 needs its parent include dir):
```
cmake -B port/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
  -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include
```

## Controls

- Click the Metal game window to focus it. Keyboard controls use physical macOS key positions: arrows = D-pad (also left stick); Z = Cross; X / Esc / Backspace = Circle; A = Square; S = Triangle; Q / W = L1 / R1; 1 / 2 = L2 / R2; Space = Start; either Shift = Select. Return / keypad Enter presses **both Cross and Start**; use Z or Space for separate actions.
- Port 0 falls back to keyboard when no real controller occupies it. A connected SDL2 GameController takes precedence; unplugging restores keyboard. Focus loss releases held keys. `PAD_NO_KEYBOARD=1` disables the keyboard monitor (the existing neutral virtual port 0 remains connected). `PAD_TRACE=1` logs guest button transitions.
- SDL initializes and polls controller drivers on the AppKit main thread, without initializing SDL video. SDL's standard A/B/X/Y positions map to Cross/Circle/Square/Triangle for Xbox, PlayStation and MFi mappings. Hot-plug tracks device instance IDs, including when an unmapped joystick precedes a controller. SDL2's [JOYSTICK_THREAD hint](https://wiki.libsdl.org/SDL2/SDL_HINT_JOYSTICK_THREAD) is Windows-only; macOS uses main-thread initialization/polling. Physical pads still need real-host verification.
- Run `bash codex/I.check.sh` for native event regressions followed by a 40-second interactive game run; `bash codex/I.check.sh auto` also sends timed guest button pulses. Disconnect physical pads during deterministic keyboard tests, then connect/unplug them during the interactive run.
- Movies currently complete immediately through the D2 facade, with `[D2 movie] finished cleanly (no decoded frames)`. The SDK lacks real demux/video decoding. `D2_MOVIE_NATIVE=1 bash codex/I.check.sh` restores the original path for codec investigation; it is not working playback.

## Recon facts (see work/RECON.md)
- PPU: 9,950 OPD functions, TOC 0x3fde60, 305 imports across 26 libraries. About 105 had no handler at first count (mostly PSN).
- SPU: no SPURS. `NisGraphics.spu.elf` (raw SPU thread group of 6, image at EBOOT 0x3c1300, 20,116 bytes) and `synth2.elf` (audio).
- Engine: NIS "NisLib" with FIOS 1.3.5. Data is NISPACK archives. The intro movie is PAMF (`dis3_0.dat`).

---

## Log

### 2026-10-04
- Recon: decrypted the EBOOT with RPCS3 0.0.40 (FW 4.46 installed from the disc PUP).
- Found the ps3recomp ecosystem. PR #160 shows a macOS runner reaching menus (Yakuza: Dead Souls), so the README's "macOS cannot run a game" is stale.
- Built the runtime on arm64. The headless Metal self-test clears correctly, but the triangle check reports MISMATCH (to investigate).
- Lifted D2 and built the port.
- **Run 1:** stalled in FIOS "wait for invalid cond" → fixed the lwcond layout (patch 3).
- **Run 2:** FIOS OK. GCM init, Resc init, NisGraphics SPU group created (no lifted image), first file read (`NisAnmShadow.txf`). Then the main thread spins on the GCM control register (`put=0x19C get=0`). The `[rsx] backend init` line never appears, so the frame-clock thread is likely not running or is blocked. Suspect: Metal/AppKit window creation off the main thread deadlocks while the main thread runs the guest.
- Other gaps seen: unresolved NIDs `0xD1CA0503`, `0x01220224` (cellResc), `0xE7FA820B` (cellSysutil). `/dev_hdd1` maps into the game dir (FIOS cache open fails; harmless for now).

- Started `OPERATIONS.md`. Launched 3 Codex workers (`gpt-6.1-sol`, reasoning high, workspace-write + network):
  A = frame clock/Metal/FIFO (`port/build-a`), B = SPU lift (`port/build-b`), C = HLE gaps + /dev_hdd1 (`port/build-c`).
  Prompts: `codex/common.md` + `codex/{A,B,C}.md`; logs `codex/*.log`; reports `codex/*.report.md`; completion in `codex/status.txt`.

- **Codex B done** (`codex/B.report.md`): lifted both SPU images into `port/spu/` (extract_spu_images → spu_lifter → build_spu_workloads). SDK fix: `runtime/spu/spu_dma.h` halted any SPU after 256 identical DMAs, which killed NisGraphics' legitimate command-buffer poll. The repeat limit is now opt-in via `SPU_DMA_REPEAT_LIMIT` (**patch 4, upstream candidate**). synth2 is registered but not started by the game yet. Note: the Codex sandbox reports `[RSX metal] no Metal device available`, so Metal must be verified outside the sandbox.

- **Codex A done** (`codex/A.report.md`). Root cause: the runner created the Metal window on the frame-clock thread, which dispatches synchronously to the macOS main queue while main is busy in `ppu_run()` → deadlock. SDK fix: on macOS, `ppu_run()` moves the guest to a 16 MB-stack pthread and services the CFRunLoop on main (**patch 5**). Also: Metal now falls back to the built-in MSL path when no shader translator is present, which fixed the host triangle MISMATCH (**patch 6**). `sceNpGetNpId` was missing a GUEST_PTR translation, which caused a SIGSEGV (**patch 7**). Added a software-backend fallback for sandboxed runs.
- Claude verified outside the sandbox: `ps3recomp_host --draw` pixel OK, and the D2 window opens ("Metal backend init OK"). 0 guest frames in 40 s: it stalls in audio init (synth2 SPU starts, cellAudio ports open, NisAt3Line threads start, then waits after `port_send` to event queue 2).
- Installed `spirv-cross` (brew); glslang was already present. Launched **Codex D**: audio stall + shader translator.

- **Codex C done** (`codex/C.report.md`, gaps in `codex/C.missing-nids.md`). Implemented `cellRescVideoOutResolutionId2RescBufferMode` (0xD1CA0503), `cellRescGcmSurface2RescSrc` (0x01220224; SetSrc now 1280x720 pitch 5120), and `cellSaveDataEnableOverlay` (0xE7FA820B). `/dev_hdd1` → `PS3_HDD1_ROOT` (default `hdd1` beside hdd0), so the FIOS disk cache now gets created. Fixed the PS3 open-flag constants (O_CREAT etc. were wrong) and real `statvfs` free space (**patch 8**). Added 61 PSN-offline handlers in `port/src/d2_psn.cpp` (NP OFFLINE / NO_LOGIN). Zero unresolved NIDs at boot; 36 lower-priority gaps remain.

- **Codex D done** (`codex/D.report.md`). Implemented `sys_spu_thread_bind_queue` + blocking SPU receive, per-thread SPU event-port routing, and an SPU lifter continuation after `stop 0x110`. Set the POSIX cellAudio clock to 187.5 Hz. Shader translator enabled (Homebrew glslang/spirv-cross detected; 65/65 translator tests pass). Headless run: 404 frames, then stall in cellSyncMutexLock.
- **Claude, real Metal (combined build):** guest pipelines compile, ~10 draws/frame. main2: 810 frames/60 s, loaded all ANM_HI. main3: stopped at ~500 frames during BGM pack loads (nondeterministic). Frames captured via `PS3RECOMP_METAL_FRAME_DUMP` are fully black. SDK tweak: `PS3RECOMP_METAL_FRAME_DUMP_EVERY` + `%u` numbered dump paths (**patch 9**).
- Launched **Codex E** (loading race, SPU fault, FIOS cache reopen) and **Codex F** (black frames; offline analysis + `codex/F.metal-check.sh` for Claude to run on real Metal).

- **Codex F done** (`codex/F.report.md`). Black frames had two causes: (1) NV0039 main→VRAM transfer copies on subchannel 1 were never executed, so textures and palettes stayed zero; (2) the draw engine applied transfer-object methods as 3D registers (FORMAT→COLOR_MASK etc.) (**patch 10**). Added the opt-in `D2_DRAW_TRACE` capture.
- **Claude ran `codex/F.metal-check.sh` on real Metal** → `port/runs/F-metal.3NNE/`. Frames 60–300 show the Prinny NOW LOADING sprite. 🎉 Frames from ~360 on are black despite 28 draws/frame. ATRAC decoder errors are flooding the log. Launched **G** (post-loading black scene) and **H** (ATRAC).

- **Codex E done** (`codex/E.report.md`, `patches/E-runtime.diff`). Fixed SPU DMA tearing, macOS lwmutex exclusion, FIOS cache recovery (reused HDD1 works), and the FIFO pointer rewind race (**patch 11**). Launched **Codex I**: macOS keyboard + gamepad input, PAMF movie.

- **Codex G done** (`codex/G.report.md`). Root cause: `cellGcmResolveLocated(MAIN, off)` used the ambiguous resolver, which preferred VRAM once loading allocated VRAM at the same offset page, so MAIN-memory vertex rings read zeros → degenerate geometry (**patch 12**).
- **Claude ran `codex/G.metal-check.sh` on real Metal** → `port/runs/G-metal.UrA3/`: 4,680 frames in 90 s; NIS logo, D2 logo, then the **full title menu renders correctly**. 🎉

- **Codex H done** (`codex/H.report.md`, `patches/H-atrac.diff`). cellAtrac treated D2's 100 KB streaming ring as the whole 3.6 MB file → decoder garbage. Implemented the streaming/refill model and the 4 missing NIDs (GetStreamDataInfo, AddStreamData, IsSecondBufferNeeded, GetBufferInfoForResetting). Fixed FFmpeg packet padding and a decoder-table allocation race (**patch 13**). Validated the full 153.7 s BGM and voice decodes under ASan/UBSan.
- **Claude ran `codex/H.host-check.sh` on the real host**: SDL `driver=coreaudio rate=48000 channels=2`, test tone submitted, game BGM decoded and mixed (~50% non-silent blocks, peaks 0.43), 0 ATRAC errors.

- **Codex I done** (`codex/I.report.md`). macOS keyboard input via an AppKit local monitor on the Metal window (see **Controls**). SDL2 gamepad fixes: instance IDs, centered sticks at 128, main-thread init/poll. Implemented cellPamf header queries. The D2 movie facade (`port/src/d2_movie.cpp`) skips movies cleanly; `D2_MOVIE_NATIVE=1` restores the original path.
- **Claude, real Metal, scripted input** (`port/runs/play1.*`): title → Up → Cross on **New Game** → story intro text → in-engine 3D map (Flonne in the garden). 🎉
- Claude raised the `PAD_SCRIPT` cap 32→512 events (**patch 14**). A 7-min scripted run (`port/runs/play2.H500`) crashed at ~386 s: SIGSEGV in `pad_poll_sdl2` on a garbage `s_sdl_controllers` slot (=0x1) although no controller was opened → **host memory corruption**. An lldb watchpoint rerun instead **hung** at frame 5340 (~80 s): GCM put==get, guest waits on ref 0x2E99. Launched **Codex J** for both.
- Added `port/play.sh` (one-command launcher; saves in `port/hdd0` + `port/hdd1`, log in `port/runs/play-latest.log`).

- User: Codex budget is wide, so more parallel workers are OK. Launched 4 more on non-overlapping areas:
  **K** movie playback (PAMF demux + VideoToolbox H.264 + vpost), **L** save/load (cellSaveData audit + round-trip harness), **M** remaining 28 imports + make the noisy trace logs opt-in, **N** `Disgaea D2.app` bundle (icon from ICON0.PNG, saves in ~/Library/Application Support, fullscreen/resizing).

- K and M failed instantly with `Selected model is at capacity` (server-side). Added `codex/launch.sh <TASK>`, which retries with backoff on capacity errors (logged to `codex/retries.txt`), and relaunched K and M. All future launches go through it.

- **Codex J was stopped by OpenAI's cybersecurity content filter** partway through (memory-corruption/ASan debugging). Per policy, it was not rephrased to get around the filter; Claude took over J's work. J's partial work found the root cause before it was stopped: ASan `global-buffer-overflow` in `cellPadGetData`. The `said[32]` array in the **PAD_SCRIPT** test code was not enlarged when Claude raised the event cap to 512, so scripted runs with >32 events overwrote `s_sdl_controllers` → SIGSEGV. **It only affects scripted test runs, not normal play.** J already fixed it (`said[PAD_SCRIPT_MAX_EVENTS]`) and added a loud corruption check (`[cellPad] HOST CORRUPTION`, abort) in the SDL slot accessor. Claude is rerunning the 7.5-min scripted session on real Metal (`port/runs/play3.*`) to confirm, and to see whether the GCM-ref hang (seen only under lldb) recurs.

- **User observation (real Mac, watching play3):** visuals look great; speed ~0.25x, audio crackling, fans maxed at 60–70 °C, 12/16 GB used. Claude measured the game at **~700% CPU**: 6 NisGraphics SPU threads DMA-poll nonstop, PPU hot-read spins, FIOS/audio polling. Launched **Codex O**: adaptive backoff/notification for spin-polls, thread QoS. Target < 250% CPU and full 60 fps game speed.

- **play3 (real Metal, 7.5 min, fixed build):** ran to the timer, with no crash, corruption, or GCM hang. Reached Laharl's meteor cutscene with dialogue. Only ~16 fps under heavy machine load (4 Codex builds + spin-polling). Lesson: PAD_SCRIPT holds each press for 40 *polls*, so at low fps, presses 2 s apart merge and dialogue stops advancing. Space presses ≥ 4 s apart until speed is fixed.

- **Codex N done** (`codex/N.report.md`, `patches/N-window.diff`): `port/dist/Disgaea D2.app` (~29 MB, no game data inside). It has an AppKit launcher that finds the dump and EBOOT.elf (file pickers on first run; config in `~/Library/Application Support/DisgaeaD2Recomp/config`). Saves go to `~/Library/Application Support/DisgaeaD2Recomp/{hdd0,hdd1}`, logs to `~/Library/Logs/DisgaeaD2Recomp/latest.log`. The icon is built locally from ICON0.PNG. SDL2/glslang are bundled and ad-hoc signed. Cmd+F / Cmd+Ctrl+F fullscreen, resizable letterboxed window, Cmd+Q quits. Real-host check: `bash codex/N.host-check.sh` (pending until K/L finish their SDK edits; currently a full rebuild breaks on their in-progress files).

- **Combined build (L+M+N+O) on real Metal:** CPU **~73–80%** (was ~700%), and logs are now ~170 KB per 90 s. **Black screen** cause: K's in-progress native movie path hits a VideoToolbox decode error (-12909), so the game sits on a black movie. `D2_MOVIE_SKIP=1` restores rendering (loading/title verified). **Native "no save data" popup**, user report: the script pressed Continue with no saves, and L's native NSAlert appeared. Correct message, wrong UI. Launched **Codex P**: PS3-style in-window Metal overlay for cellSaveData + cellMsgDialog, pad/keyboard navigation, guest input suppressed while it's open, no native alerts.
- **Codex L done** (`codex/L.report.md`): cellSaveData rewritten for D2's real callbacks. Binary PARAM.SFO, RPCS3 layout under `$PS3_HDD0_ROOT/home/00000001/savedata/`, atomic commit, list/fixed/auto save. cellGame reads the real PARAM.SFO.
- **Codex M done** (`codex/M.report.md`): L10n SJIS↔UTF-8 (iconv CP932), PRX-load variants, offline socket stubs, FS AIO write / SdataOpenByFd, error dialog. **Logging quiet by default** (`PS3RECOMP_TRACE_WAIT/EVENT/HOTREAD=1`, `PS3_VERBOSE=1` to re-enable). Fixed a C/C++ atomics header conflict.

- **User: still 0.25–0.5x speed.** Claude `sample`d the live process (`port/runs/Q-profile-sample.txt`). The PPU main thread spends ~26% waiting in `cellGcm_fifo_recycle` (command ring full, nanosleep loops) and ~15% in `cellRescSetWaitFlip→cellGcmSetWaitFlip` (nanosleep). The frame_clock drain thread is asleep 84% of the time (fixed 4 ms / 16 ms cadence). The guest waits on a drain that only runs every few ms → slow game at low CPU. Launched **Codex Q**: event-driven RSX drain (wake on `put` moves / ring-full), condition-based recycle/flip/label waits, 60 Hz flip pacing kept.

- **User: Laharl-on-meteor dialogue waits for ✕ (or △ to skip).** Cause was in my test script: PAD_SCRIPT held each press for 40 *polls*, and at slow game speed that outlasts the 4 s gap, so the button never released. Fixed: each press now holds for 250 ms of wall time (min 2 polls) and then releases (**patch 15**, `cellPad.c`). Stopped the stuck play4 run. The main build is temporarily blocked by P's in-progress overlay file; the playthrough resumes after P.

- **User played live:** skipped the meteor cutscene with △ in the running window (first human input on the real game). The session then reached the **castle throne room** (Laharl, Etna, Flonne, dialogue): `milestones/castle-throne-room.png`. Note: play4 was not actually killed (`pkill` missed it), so it is still running with the old script.

- **User created an in-game save** during play4. cellSaveData logged `SAVE complete` then `LOAD complete` for `NPUB31321_NORMAL_00` (ICON0.PNG 71 KB, SAVEDATA.DAT 1.5 MB, binary PARAM.SFO). Copied it to `port/hdd0` (play.sh), `~/Library/Application Support/DisgaeaD2Recomp/hdd0` (the .app) and `port/runs/saves-backup/`. Next scripted runs will test **restart → Continue** with this save.

- **cont1 (restart → Continue with the user's save):** `LOAD complete` → castle hub (`milestones`: hub frame f4200). ~49 fps average. User, playing live in that window: **full speed** in the hub (slower in the next room), reached the **stage selector**, picked a stage → **screen went black**. Log: "storyselect mapload thread" opens `MAP/mp001/map00101.lzs` (previews). After selection: constant 218 draws/frame, identical near-black frames, no pipeline/shader/FS errors. Added `port/capture.sh` (diagnostic session on a copy of the saves: frame dumps every 120 frames, D2_BOOT_TRACE guest snapshots, hot-read waits, PAD_TRACE) for the user to reproduce.

- **Codex O done** (`codex/O.report.md`): generic guest-poll backoff via hashed cache-line condition waits, notified by PPU stores, stwcx, SPU PUTs and reservations. Covers the SPU DMA-poll and PPU hot-read paths, cellSync mutex backoff, and thread QoS (`PS3_POLL_BACKOFF=0` disables it). Headless CPU 684%→117%, fps 13.9→20.9 (**patch 16**). The launcher bug reran O 3× after success (any 'at capacity' line anywhere in the log triggered a retry). Fixed `codex/launch.sh`: retry only on nonzero exit with the capacity error in the last lines. Stopped the redundant rerun.

- **Codex K done** (`codex/K.report.md`, `patches/K-movie.diff`): full movie pipeline (streaming PAMF demux, VideoToolbox AVC with reordering, Vpost YUV→RGBA, PAMF ATRAC3plus audio, per-worker guest callback stacks). **Claude's real-host check** (`port/runs/K-host.s3S1tE`): VT works on the host, but after 2 pictures `DecodeAu error=-12909` (bad data, 17,968-byte AU) → D2's vdec thread exits. Launched **Codex K2** to find and fix the AU/AVCC packaging, with offline FFmpeg cross-checks.

- **User went to bed (~1:10am).** Claude continues autonomously. Started **battle1**: a New Game scripted run (✕ to advance, △ to skip cutscenes, 250 ms presses, 16 min) to reach the first story battle and reproduce the black screen without user input.

- **Codex K2 done** (`codex/K2.report.md`). Root cause: the PPS changes mid-stream (98 parameter-set changes, 46 on non-IDR pictures). The decoder recreated the VT session each time, discarding reference frames, so the next P picture failed with -12909. Fix: keep compatible sessions, defer incompatible resets to the next IDR, recover bad data by skipping to IDR without a fatal vdec error, and compute full DTS/PTS. Offline: 2,793/2,793 AUs match FFmpeg exactly, ASan clean. Movie audio was fine (silent until PCM block 348). Host check queued after battle1.

- **Claude's K2 host check** (`port/runs/K2-host.jxcoRF`): VT decodes on the host, but the game receives only 3 pictures while the demux keeps feeding AUs (62–68 …), so the movie never completes. The standalone test stops at 40 AUs with 3 errors. Launched **Codex K3** (picture-output/reorder/callback handshake stall). Movies stay skipped by default.
- **battle1** (New Game, 16 min, ✕/△ script): ~46 fps sustained over 16 min, no crash. Reached the castle but the script wandered into the character status menu (renders perfectly). Blind scripts can't navigate to the stage gatekeeper. Next: closed-loop navigation via `PAD_FILE` + frame dumps, starting from the user's save.

- **nav1 (closed-loop PAD_FILE navigation from the user's save, ~35–40 fps):**
  - ⚠️ At boot the game showed **"There was an error in the installed Game Data. Delete the Game Data and reinstall."** It wasn't seen in cont1 with the same save. Suspect P's in-progress cellSaveData/cellGame edits in the current tree (or a stray `port/hdd0/game/BLES00000` from a worker test). Dismissing with ✕ continues normally. **Recheck after P finishes.**
  - Continue → LOAD complete → throne room → **Castle Hallway**. Blind navigation to the Dimension Guide wasn't converging (camera-relative controls, dark corridor), so I stopped it. The battle black screen awaits the user's `port/capture.sh` run.

- **Codex K3 done** (`codex/K3.report.md`). The 3 standalone "errors" were backwards PTS, not VT failures. Fixes: decode synchronously (VT may delay callbacks with temporal processing); sorted PTS reorder queue (max_reorder=1); an async per-AU decoder worker with back-pressure instead of returning BUSY when the 64-picture queue was full (D2 then waited forever for AUDONE); GetPicItem independent of GetPicture. With mocked VT the real lifted D2 consumed all 2,793 pictures, got every AUDONE/PICOUT/SEQDONE, and moved on to START.dat. Real-VT host check running (`port/runs/K3-host.*`).

- **Claude's K3 host check** (`port/runs/K3-host.3uMTOb`): **real VideoToolbox decodes all 2,793 pictures with 0 errors**, audio OK. Real frames look right (`milestones/movie-nis-logo-videotoolbox.png`). In-game, pictures 1–353 play at about real time, the decoder drains to pending=1, and then the guest never feeds another AU (stall upstream in demux/stream feed or A/V sync). Launched **Codex K4**.

- **Codex K4 done** (`codex/K4.report.md`). Two demux races: (1) DEMUX_DONE was sent while the demuxer was still BUSY, so NisMovieDmux's next SetStream got BUSY and waited forever (the picture-353 stall); (2) audio and video FlushEs shared one busy slot, so the EOF flush failed and the movie aborted. The paced mock (24 fps, 5–15 ms VT latency) now completes all 2,793 pictures and reaches START.dat. Added `PS3RECOMP_CODEC_TRACE=1`. Real-VT host check running.

- **Claude's K4 host check** (`port/runs/K4-host.BoHDjP`): ✅ **full intro movie plays in-game on real VideoToolbox**: vdec pictures=2793 AUDONE/PICOUT=2793 SEQDONE=1, adec 2,733 PCM consumed, dmux 295,852,032/295,852,032 bytes, all ES released. `play.sh` plays movies by default again (`capture.sh` keeps skipping them for speed).

- ⚠️ **P and Q were rerun 6–7× each** by launchers that started before the `launch.sh` retry fix (they kept the old logic in memory). Both had finished. Stopped them; Codex 74%→72%.
- **Codex Q done** (`codex/Q.report.md`, `patches/Q-fifo.diff`): event-driven drain kicks, generation-based completion conditions for ring recycle / WaitFlip / labels / semaphores, real RESC flip waits, present at 60 Hz before draining, missed refreshes skipped (**patch 17**). Headless: title 34→**60 flips/s**, loaded map 28→**60 flips/s**, software-draw title 31→58 fps. Real-Metal check running.
- **Codex P done** (`codex/P.report.md`): in-window system overlay for save/msg dialogs (details after the host check).

- **Q real-Mac check** (`port/runs/Q-host-20261005-022651`): **title 59.99 fps @ 97% CPU; loaded map 55.7 fps @ 120% CPU.** 🎉
- **P real-Mac check**: P's script aborted on a unit test that needs a key window (unattended screen). Claude ran the overlay check directly (`port/runs/ovl.*`): Continue with no saves → in-window PS3-style **"Load saved data / There is no saved data. ✕ OK ○ Back"**, ✕ dismisses, New Game → story. No macOS popups.
- **"Error in the installed Game Data" root cause** (`port/runs/gderr.*`): appears on the **second boot** with a persistent hdd0. Boot 1's ContentPermit creates `game/NPUB31321/USRDIR` without PARAM.SFO; boot 2's DataCheck reports it as existing, so D2 rejects it. Not the stray BLES00000. Launched **Codex R** (valid PARAM.SFO on create, NONE for broken dirs, self-heal).

- **Profiling pass #2** (after the O+Q+P merge; `port/runs/Q-host-*/newgame.sample.txt`, loaded map ~56 fps): the PPU main thread has **no single wait ≥8%**, so it is no longer latency-bound. Remaining hot leaf functions are small: `spu_shufb` (lifted synth2 audio SPU, ~1.7k samples) and `barrier_watch_hit` (O's notify hook, ~0.7k). Candidates if the map needs a steady 60: vectorize `spu_shufb` with NEON and cheapen the barrier watch.

- **Codex R done** (`codex/R.report.md`): `cellGameDataCheck` reports installed data only with a valid PARAM.SFO. `ContentPermit` no longer fabricates empty game-data dirs (D2 never creates game data). Explicit creation writes binary GD PARAM.SFO (**patch 18**). Real Mac: R's two-boot check PASSes both boots. Claude booted a copy of the user's `port/hdd0` (legacy empty `game/NPUB31321`): `DataCheck: NONE (PARAM.SFO missing/invalid)` → **no error, straight to title**. Self-heals existing installs.

- **Mac app rebuilt** with all fixes (`cmake --build port/build --target DisgaeaD2Dist` → `port/dist/Disgaea D2.app`, signature verifies). Launched via `open`: the launcher never reached the runner (empty `~/Library/Logs/DisgaeaD2Recomp/latest.log`) even with a valid config written to `~/Library/Application Support/DisgaeaD2Recomp/config`. Most likely macOS privacy (TCC): a LaunchServices-launched app needs the user's one-time approval to read files on `/Volumes/Data`, so it sits on that prompt or the file picker. **User action:** double-click the app and Allow access (or pick the dump folder and `work/EBOOT.elf`). Closed it for the night.

- **Repo prepared (local only, NOT pushed):** project commit `270982a` (84 files, 1.6 MB: sources, docs, scripts, worker prompts/reports, patches; no game data, lifted code or logs). SDK changes are committed on the local ps3recomp branch `d2-macos` (`f1d2b5c`) and exported as `patches/ps3recomp-d2-macos.diff` (110 files, audited: no binaries, no personal paths). **Awaiting the user's review before `git push`.** Note: 25 docs/reports mention local paths (`/Volumes/Data/...`); the user should decide whether to scrub them.

- **Codex S done** (`codex/S.report.md`, `patches/S-perf.diff`): NEON `spu_shufb` (exhaustive selector tests), debug store-watch and `vm_read32` tracing outlined behind cached gates, 4096-entry line filter before notifier buckets (**patch 19**). Real Mac: **map CPU 70%**, but **69.9 flips/s**, so the game runs ~16% fast (vsync was not enforced; the CPU limit hid it before). Launched **Codex T**: firmware-correct vsync flip pacing at 60 Hz.

- **Codex T done** (`codex/T.report.md`, `patches/T-vsync.diff`). S's 69.9 was a **sampling artifact** in S's script, but T fixed real firmware defects: flip mode was ignored, flips could merge, vblank counters were manufactured on query, and flip handlers/status fired early. Now each VSYNC flip retires on its own tick of a monotonic 60 Hz clock, with Metal presentation in lockstep (**patch 20**). **Real Mac: title 59.998 / map 60.002 flips/s, flips == vblanks.** 🎯

- **Morning (Oct 5, ~6:30am): the user took over the nav2 window** (Continue → castle → gatekeeper → stage) and **entered the first battle**. Map, units, HUD, help panel, Bonus gauge all correct, so the old stage-select black screen no longer reproduces (likely fixed by the overnight Q/T/S timing work). One visual bug: the top-left "ATTACK ENTRY" portrait renders on an opaque white rectangle. Launched **Codex V** (alpha/transparency for that draw). Codex U (debug stage warp) is still useful for automated battle testing.

- **User feedback in battle: "biggest issues are speed and audio; audio is painfully distorted."**
  - **Battle profile** (live sample, `/Volumes/Data/ai-tmp/claude/d2/battle-sample.txt`): ~37 fps @ 88% CPU. PPU main 42% in `cellRescSetWaitFlip`; the RSX render thread is 48% blocked on main-queue dispatch; the **main thread is 54% in `nanosleep`**: A's `ppu_run` main loop did `CFRunLoopRunInMode(0.01, returnAfterSourceHandled) + Sleep(1)`, so every main-queue present waited out a sleep. **Claude fixed it** (block in `CFRunLoopRunInMode(0.25, false)`, sleep only on `kCFRunLoopRunFinished`) (**patch 21**). Awaiting the user's speed impression.
  - **Audio:** the user's capture (`port/runs/capture.Yy9G/mix.f32le`, 211 s) shows **exactly alternating silent/non-silent 256-sample blocks (".#.#.#", 50.5% silent), no clipping**, i.e. audio gated at 93.75 Hz = the "distortion". Launched **Codex W**.

- **User: after the main-thread sleep fix, battle speed is "about half the slowdown, 0.5–0.75 of full".** Live battle profile (`port/runs/battle-profile-2.txt`): CPU ~110%, presentation 60/s, PPU main 46% in RescSetWaitFlip, 8.6% ring recycle, 8.6% guest usleep; RSX thread 71% idle, and `eng_texture_content_hash` costs 7.5%. Neither side is saturated, so flips probably retire a vblank late. Launched **Codex X** (per-flip latency instrumentation, battle-speed fix). Audio was silent in that session because W's in-progress cellAudio edits were in the tree when capture.sh rebuilt.

- **Codex U done** (`codex/U.report.md`): **`D2_WARP_STAGE=<n>`** (opt-in, port-only `port/src/d2_debug_warp.cpp`). After Continue loads the hub, it replays the stage-select confirmation path (`0002E3C4`, `001E1B80(0)`, `0008D8A4(11,0)`) and enters battle without navigation. `D2_WARP_STAGE=1` = first battle (map 101, mission 5011). `D2_WARP_TRACE=1` logs state only. The old 218-draw "black" frame was the stage fade-in (final overlay alpha ramps from 0.26). It no longer freezes; frames advance with real geometry. **Automated battle testing now possible.**

- **Codex W done** (`codex/W.report.md`, `patches/W-audio-clock.diff`). Root cause of the "painful distortion": with a device open, cellAudio consumption was driven only by device room, and the CoreAudio callback takes 512 frames = **two** PS3 blocks at once, so every other block was consumed before the guest rendered it (silence). Fix: always pace on the monotonic 256/48000 s deadline and use device room only as back-pressure (**patch 22**). **Real Mac (CoreAudio): 0.037% silent blocks (was 50%), continuous pattern.** WAV: `port/runs/W-host.QzEtYh/mix.wav` (sent to the user).

- **User confirmed: "audio improved tremendously"** after W's fix. ✅

- **Codex X done** (`codex/X.report.md`, `patches/X-battle-speed.diff`): D2 calls Finish → RESC ConvertAndFlip → WaitFlip once per frame (no 30 fps divider). **Headless warp battle: 60.0 distinct guest flips/s**, with no late-retirement bug found. Sped up the texture mutation hash (4 independent streams) and added `GCM_FLIP_TRACE`. Fixed the stale Q sync test for T's VSYNC. If real Metal battles are still slow, the cost is in the Metal backend/GPU path, not guest pacing. Real-Metal check queued until the user closes their session.

- **X real-Metal battle check** (warp → battle 101): **59.998 distinct guest flips/s = vblanks/s, 440/440 flips retired on the next tick**, 0 undrained FIFO submissions; submit→retire mean 10.0 ms. Battle pacing is correct on real hardware with the current build. Asked the user to re-feel battle speed.

- **User playtest (play.sh, latest build):** "battle feels smooth"; **castle main room drags**. Live profile (`port/runs/hub-profile.txt`): PPU 18% waiting in `cellGcm_fifo_recycle` (ring full) + 27% WaitFlip while the RSX thread is 60% idle, so heavy scenes (~800 draws) overflow the ring and the drain/recycle waits for vblank/present. Launched **Codex Y**.
- **User: "something happened and audio went out of whack like before"**, right after Claude's `sample` suspended the process ~8 s. W's deadline clock does not resync after a stall. Launched **Codex Z** (resync after hitches, App Nap opt-out, SIGSTOP/SIGCONT test).

- **User left for work (~7am).** Asked for: (1) a late-game save from the web to stress-test full-map battles, (2) keep improving efficiency; granted screen control (needs an in-person approval dialog, so not usable while away).
  - Found on [GameFAQs saves](https://gamefaqs.gamespot.com/ps3/687861-disgaea-d2-a-brighter-darkness/saves): **NA post-game save by XYZexal (02/19/2014, 1,552 KB, cycle 1, DLC chars/weapons)**, and a maxed EU save (RoronoaZoro97, 1,533 KB). **Download awaits the user's explicit OK.** Retail PS3 saves may need secure-file decryption/resign (pfd/Apollo-style, using public keys) to load in our RPCS3-layout cellSaveData.

- **Codex Z done** (`codex/Z.report.md`): discard deadline debt > 3 blocks (~16 ms), ≥4.33 ms reserve after each notification so short delays can't burst, and an `NSActivityLatencyCritical|UserInitiated` process activity (App Nap off) (**patch 23**). **Real Mac: 5 s SIGSTOP mid-BGM → 0% silent before / first second after / settled; continuous pattern.** WAV `port/runs/Z-host.pZGZPs/mix.wav`.

- **Codex Y done** (`codex/Y.report.md`, `patches/Y-fifo-*`): fixed a generic flip-ordering defect (a direct flip could present before the preceding unread commands ran). Headless hallway 56.3→59.8. **Real Mac (Y host check, Castle Hallway map30001): 30.0 distinct flips/s (788/1576 vblanks)**, recycle mean 1.55 ms × ~7 wraps/frame. Claude's Metal hallway profile (`port/runs/hallway-metal-profile.txt`): RSX 48% idle, 26% FIFO processing dominated by CPU per-element vertex decode, plus vm_read/write and TLS lookups. PPU and RSX are serialized per ring wrap. Launched **Codex AA** (overlap drain with PPU writes, bulk/NEON/cached vertex fetch, hot-path TLS/watch removal).

- **Codex AA done** (`codex/AA.report.md`): engine-only decoding (no double decode), NEON bulk vertex fetch, a 32 MiB verified vertex cache, immutable MTLBuffers, redundant-bind suppression, chunked self-kicking drain, and hot-path gates. Recorded hallway drain **8.27→4.88 ms/frame** (**patch 24**). **Real Mac still 30.000 flips/s**: recycle mean 0.91 ms × ~7/frame, **wake_next_submit 17.45 ms** (PPU frame-build time just over one vblank → always retires on the 2nd tick). Launched **Codex AB**: snapshot the ring into a host command queue on recycle so the PPU never waits for Metal encoding (ordering-preserving), plus a PPU work profile.

- **Codex AB done** (`codex/AB.report.md`, `patches/AB-fifo-snapshot*`): an RSX copy worker snapshots complete command packets into 64×64 KiB host buffers and publishes guest GET after copying, so recycling no longer waits for Metal encoding. Ordered execution is preserved (17 new sync checks; replay checksum identical) (**patch 25**). **Real Mac, Castle Hallway: 59.992 distinct flips/s (1588/1588 vblanks)**, recycle mean 0.064 ms (was 0.91), wake→submit 12.05 ms (was 17.45). 🎯

- **User approved the GameFAQs NA post-game save download.** Identified save `23628` = `NPUB31321_NORMAL_04` (ICON0.PNG, PARAM.PFD, PARAM.SFO, SAVEDATA.DAT **1,498,160** B = protected/encrypted form of our 1,498,152 B plain file). GameFAQs 403s non-browser clients (TLS fingerprinting) and the browser pane cannot save downloads, so the user was asked to click the link once; a watcher copies it from `~/Downloads` into `saves-import/` and unzips it. Launched **Codex AC**: `tools/d2_save_import.py` (secure-file decrypt via public PFD format + D2's secure file id → plain RPCS3 layout, written to a copy, never over the user's saves).

## Post-goal feature backlog (user request, Oct 5)
- **Resolution options**: internal render resolution scale (native 720p → 1080p/1440p/4K, i.e. render targets scaled up for a sharper image), plus output filtering (nearest/linear, integer scale).
- **Display options**: windowed sizes, fullscreen (exclusive vs borderless), aspect (16:9 letterbox/stretch), vsync on/off, frame-rate cap.
- **Save import/export menu**: keep Codex AC's `tools/d2_save_import.py` (console/PSN-format save → port/RPCS3 plain layout, plus reverse) as a maintained tool and expose it later as a user-facing option (settings menu / app menu: "Import PS3 save…", "Export save…") operating on `~/Library/Application Support/DisgaeaD2Recomp/hdd0`.
- **Audio options**: master mute/volume (and maybe a separate movie volume), mute when unfocused.
- (Natural companions: key/controller remapping, a settings menu reachable from the window (e.g. Cmd+, or an in-window overlay like P's), settings persisted in `~/Library/Application Support/DisgaeaD2Recomp/settings`.)

## Stretch goals (user request, Oct 5)
1. ✅ **Cheat menu** (Codex AF, done): an in-window overlay to view and edit game state (HL/money, levels, stats, items, mana, Bonus Gauge, etc.). Reuse community knowledge: Cheat Engine tables / RPCS3 patch.yml / PS3 cheat codes for BLUS31313 map to guest addresses directly (same PPU memory layout). Implement as guest-memory pokes with labeled entries; persist presets.
2. **Vulkan backend for Windows + Linux**: ps3recomp already has D3D12 (Windows) and community Vulkan PRs (#182/#192). Port D2's port/runner to build there; the lifted C++ is platform-neutral. Needs per-platform input/audio/window equivalents of today's macOS work.
3. ✅ **Validate DLC** (done: v1.40 + 45 DLC flags, visitors announced in battle) (*found on MediaSVR*, copied to `dlc/`, extracted with `tools/pkg_extract.py`): `DISGAEA D2 … USA ALL DLC PACK FIX (NPUB3132).pkg` (1.2 MB → ~50 `USRDIR/Data/flag/flag000xxxxx.edat` unlock flags of 304–320 B + save icons) and the **official 1.40 update** `UP1063-BLUS31313_00-…-A0140-V0100-PE.pkg` (68 MB → new `EBOOT.BIN`, `Data/START_7.dat`, icons). DLC likely needs the 1.40 EBOOT (re-decrypt + re-lift + remap the few address-specific hooks) plus EDATA reading in cellFs/sceNpDrm (RPCS3 as reference). Original notes: D2 DLC (extra characters such as Pram, Marona, La Pucelle, Baal, items). Needs the user's own DLC packages (PSN .pkg + .rap/.edat licenses) installed into hdd0/game/NPUB31321 (cellGame/DataCheck, NPDRM EDATA decryption via `sceNpDrm*`, which today are offline stubs). The GameFAQs post-game save includes DLC characters, which makes a good test once DLC data is present.
4. **Super stretch: add characters from other Disgaea games**: import models/sprites/data from e.g. Disgaea 4 Complete+ (on disk) into D2's NISPACK databases (class tables, sprite/anim archives); needs data-format tooling (NISPACK/TX2/ANM, character DB records), likely built on community tools (D5tools, UDT, makaikit).

- **DLC check (user thought it was in the game folder):** none found in the dump, the ROM folder, RPCS3 dev_hdd0 or ~/Downloads (no .pkg/.rap/.edat). The two `NPUB31321` dirs inside the dump were **empty dirs created by Claude's very first run (Oct 4 21:56)** before the hdd0/hdd1 path fixes. Removed them with `rmdir` (empty-only); the dump is back to PS3_DISC.SFB / PS3_GAME / PS3_UPDATE. DLC needs the user's PSN .pkg + .rap files.

- **Codex V done** (`codex/V.report.md`, `patches/V-stencil-reset.diff`): the white box behind the ATTACK ENTRY portrait = stencil-clipped backing quad. NV40 front/back **stencil write masks reset to 0xFF** on hardware, but the SDK's zero-initialized register file left them 0, so the stencil never got written and the quad drew unclipped (**patch 26**). V's host check didn't reach battle (its script stalled at the title), so **visual confirmation is pending the user's next playtest**.
- **Codex AC done** (`codex/AC.report.md`, `tools/d2_save_import.py` + tests): retail save import. D2 secure file id `0f×16` (from lifted `func_00164C3C`), PFD v3/v4 + public-key verification, the protected-file block cipher (flatz pfdtool / Apollo as references), plain RPCS3 layout, free-slot selection, never overwrites. Kept as maintained tooling for the future Import/Export Save menu. **Installed the GameFAQs post-game save as slot `NPUB31321_NORMAL_01`** in `port/hdd0` and the app's hdd0 (SAVEDATA.DAT 1,498,152 B, SHA256 9f5a84…fc30). The user's own save stays slot 00.
- Rebuilt `port/build` and `port/dist/Disgaea D2.app` with V's fix.

- **User (remote, can't playtest): continue with DLC + patch, then a robust cheat/item/character menu and menu-bar settings (resolution etc.).** Claude decrypted the **v1.40 update EBOOT** (`work/v140/EBOOT.elf`, 5.2 MB, APP_VER 01.40). Launched **Codex AD** (v1.40 port with selectable version + install layout + DLC EDATA flags), **AF** (cheat/character/item editor overlay, community cheat research), **AG** (macOS menu bar: render scale, window/fullscreen, vsync, audio mute/volume, save import/export, cheats entry).

- **Codex AD done** (`codex/AD.report.md`): **v1.40 is the default build** (`D2_GAME_VERSION=140`, 1.00 still buildable). 10,315 lifted functions in `port/src/recomp-140`, all address hooks remapped (table in the report). Fixed SPU image selection when CRT entry addresses collide. `port/install-content.sh` installs update → `hdd0/game/BLUS31313`, DLC → `hdd0/game/NPUB31321`. RPCS3-compatible EDATA reading with validated klicensee/hashes (84 EDAT tests) replaced the offline NPDRM stubs (**patch 27**). **Real Mac: 45/45 DLC flags accepted; slot 01 post-game save → battle 101; the game announces the DLC visitors "Badass Overlord", "God of Destruction", "Phantom"** (`milestones/v140-dlc-visitors.png`). 🎉

- **Codex AG done** (`codex/AG.report.md`, `patches/AG-host-settings.diff`): native macOS menus (Graphics: render scale 1/1.5/2/3×, filter, aspect, VSync, presentation cap, FPS · Window: sizes, native/borderless fullscreen, topmost, remember geometry · Audio: Cmd+M mute, volume steps, mute when unfocused · Game: import/export save, open save folder/log, Cheats…, reset · Controls), settings in `~/Library/Application Support/DisgaeaD2Recomp/settings.json`, scaled color/depth/MRT targets, host gain in cellAudio (**patch 28**). Real Mac: hallway **59.97 flips/s at 1x and 2x**, but the **presented frame stays 1280×720 at 2x** (the RESC/display-buffer step discards the scale). Launched **Codex AG2**.

- **Codex AG2 done** (`codex/AG2.report.md`, `patches/AG2-render-scale.diff`): display buffers registered before Metal init now allocate as scaled targets. Fixed the RESC ConvertAndFlip ABI (`(context,index)`; it received the context address as the index) and queued RESC conversion in FIFO order. NV3089/NV308A transfers reach scaled engine targets. The overlay compositor/captures use target size (**patch 29**). **Real Mac: 2× presented frames are 2560×1440** (`milestones/render-2x-1440p-crop.png`: crisp 3D edges). AG2's RESC/presenter GPU tests pass at 1/1.5/2/3×. One harness test (`conversion_chain` stripe assertion, `codex/AG.metal-test.m:71`) still fails; low priority (likely a test expectation for filtered scaling), to recheck.

- **Codex AF done** (`codex/AF.report.md`): in-window cheat/editor for 1.00 and 1.40 (F1 / Cmd+Shift+C; menu bar Game → Cheats…). General (HL, Mana, Bonus Gauge, Cheat Shop CP/rates, infinite HP/SP, one-hit kills, EXP ×1–1024, free shop), Characters (level/EXP/mana/stats/aptitudes/class/move/jump/counter/skills/equipment), Items (bag+warehouse: add/remove via native helpers, rarity/level/stats), Presets (`~/Library/Application Support/DisgaeaD2Recomp/cheats/`). The live root pointer is resolved by validated signature (no hardcoded heap addresses). Struct map in the report. Edits persist through a real save/reload. **Real-Metal screenshots** (`milestones/cheat-menu-*.png`): HL 993,701,506,631, Laharl Lv 9999, item stats. Minor: ghost text behind the panel title.
- **Main build reconfigured for 1.40** (`port/build`, `-DD2_GAME_VERSION=140`) and `port/dist/Disgaea D2.app` rebuilt with everything. Updated the app config to `work/v140/EBOOT.elf` (the old config pointed at 1.00, which the 1.40 runner rejects). Launched **Codex AH** (polish: overlay ghosting, launcher version check + visible start errors, AG `conversion_chain` harness failure, automated portrait-stencil verification).

- **Codex AH done** (`codex/AH.report.md`): the "ghost text" is actually the live DLC announcement beneath a 96%-alpha panel, so the panel is now opaque. Launcher validates entry OPD + TOC for the build's version, falls back to the matching project ELF, and shows NSAlerts on start failure (**patch 30**). AG harness clear/transfer encoder fix. Real Mac: the OCR-driven portrait check **failed to navigate to an attack** (no portrait verdict); `AH.metal-check.sh` GPU harness **still aborts** (exit 134). AD/AH noted **a guest OOB + Bus error after repeated Cross in battle** (AD-host.UsTk9h/slot01/run.log:3224+; null-read by guest-fn 0x002EF390), seen only after the debug warp so far. Launched **Codex AI** (crash root cause: warp-only vs real path, plus the harness abort).

- **Pruned (user deferred to Claude's judgment):** deleted 35 old worker build dirs (`port/build-a…build-ah`, `build-j-asan`; ~2.5 GB, rebuildable in ~25 s each) and, in `port/runs/`, ~97k frame/audio dumps (`*.ppm`, `*.f32le`, raw/bin) plus 53 per-run `hdd0`/`hdd1` copies (FIOS cache.dat ~700 MB each). Kept `milestones/`, all logs/reports and anything touched in the last 2 h. Also cleared old scratch in `/Volumes/Data/ai-tmp/{claude/d2,codex}`. **Project 39 GB → 13 GB; scratch 37 GB → 4.5 GB (~60 GB freed).** Untouched: game dump, `port/hdd0` saves (slots 00/01), `dlc/`, ELFs, lifted sources, `port/build`, `port/build-ai` (AI running).
- **Commit/push plan:** after Codex AI finishes, commit project `main` (on top of local `270982a`) + ps3recomp `d2-macos` + re-export the combined SDK patch, show the file list/message, and push `main` to the private repo after the user's go. The ps3recomp branch stays local unless the user wants a fork/upstream PR.

- **Pushed** `main` (`270982a`, `fb8c2ec`) to the private repo **github.com/Sean13128/disgaea-d2-recomp** after the user's go. The ps3recomp `d2-macos` branch (`f1d2b5c`, `5b24f49`) stays local; its changes ship as `patches/ps3recomp-d2-macos.diff` (apply to ps3recomp `a679051`).
- **Codex AI done** (`codex/AI.report.md`): the battle OOB/Bus error was **debug-warp-only** (a hub announcement sprite kept a freed animation pack). The warp now drains native messages first. The GPU harness abort was a test-only static-name collision. **Real Mac: 120 s battle with constant Cross: PASS**, GPU harness PASS.

## Next actions
- [x] ~~User: reproduce the stage-select black screen~~ (no longer happens; battle works)
- [ ] **User:** play a full battle turn (move, attack, end turn, enemy turn) and report anything odd.
- [ ] **User:** double-click `port/dist/Disgaea D2.app`, Allow file access (macOS privacy), and confirm it launches.
- [x] ~~review + push~~ (pushed Oct 5)
- [x] ~~approve the GameFAQs save~~ → imported as slot 01
- [ ] **User:** playtest the post-game save (slot 01): full-map battles, check the ATTACK ENTRY portrait has no white box
- [x] (Codex A) Frame clock / Metal init on macOS: get the FIFO drained and a window open.
- [x] (Codex B) Lift `NisGraphics.spu.elf` (and `synth2`) with spu_lifter + build_spu_workloads; register in the port.
- [x] (Codex C) cellResc unresolved NIDs + map /dev_hdd1 to a writable dir.

## AD: update 1.40 and DLC (Oct 5)

`D2_GAME_VERSION=140` is now the CMake default. Version 100 remains available with `-DD2_GAME_VERSION=100`; use `work/EBOOT.elf` for 100 and `work/v140/EBOOT.elf` for 140. The runner rejects mismatched executables; `run.sh`, `play.sh`, and the app launcher choose the matching ELF. Generated 140 output is in `port/src/recomp-140`, `port/out-140`, and `port/spu-140`. Existing build caches need reconfiguration. AD's own build is `port/build-ad`; other workers should use their assigned directories.

`port/install-content.sh` defaults to a fresh hdd0 copy; `--into <hdd0>` installs update under `game/BLUS31313` and DLC under `game/NPUB31321`. Content is installed in `port/hdd0`; app-support hdd0 still needs host installation. All **45** supplied EDAT flags authenticate and are read as plaintext (license type 3, no RAP required). SDK fixes include update overlays, genuine local NPDRM checks, full HMAC authentication, writable EDAT caching, and imported-SPU fingerprint selection (overlapping CRT entries caused the 140 boot failure).

Headless title, Continue slot 01/00 → hub → battle all pass; 100 Continue/battle also passes. `bash codex/AD.host-check.sh` performs the pending real-Metal check using hdd0 copies and captures frames. Full findings, addresses, test evidence (84 crypto checks, 101 SPU checks), and one unresolved extra-input guest fault: `codex/AD.report.md`. SDK patch: `patches/AD-runtime.diff`. No shared distribution bundle was rebuilt by AD.
