# Disgaea D2: A Brighter Darkness — native macOS recompilation

A note from the human
This project was built almost entirely by AI coding agents (Anthropic's Claude and OpenAI's Codex). I directed and tested it. My goal was simple: play my own copy of Disgaea D2 natively on my Mac, and maybe do some modding later.

Performance: on an M4 Mac it holds about 60 fps in battles and while exploring. It's been through a few optimization passes, and more are planned, focused on lowering CPU use and heat rather than raising the frame rate.
Do what you want with this, it's just for fun since everyone else is doing this stuff. Might try to get it on android. 

An unofficial, fan-made **static recompilation** of *Disgaea D2: A Brighter
Darkness* (PS3, North America, **BLUS31313**) into a native Apple Silicon macOS
app, built on [ps3recomp](https://github.com/sp00nznet/ps3recomp) with a Metal
renderer. It is not an emulator: the game's PowerPC and SPU code is translated
to native code ahead of time, on your machine, from **your own copy** of the game.

> [!IMPORTANT]
> **This repository contains no game code, assets, keys or saves, and none are
> provided or linked.** You must own a legitimate copy of the game and dump it
> yourself. Nothing here can be played without it.

## Legal disclaimer

- This is an independent, non-commercial fan project for preservation,
  interoperability and research. It is **not affiliated with, endorsed by or
  sponsored by** Nippon Ichi Software, NIS America, Sony Interactive
  Entertainment, or any of their partners.
- *Disgaea*, *Disgaea D2: A Brighter Darkness*, the characters and all related
  names and artwork are trademarks and/or copyrights of Nippon Ichi Software,
  Inc. / NIS America, Inc. *PlayStation* and *PS3* are trademarks of Sony
  Interactive Entertainment. They are used here only to identify the game this
  software works with.
- The repository holds only original source code, build scripts and
  documentation (see [LICENSE](LICENSE)). The recompiled code is generated
  locally from the executable you supply, is derived from the game, and must
  not be redistributed. Do not share decrypted executables, generated
  `port/src/recomp*` / `port/spu*` output, built app bundles, game files or
  DLC/update packages, and do not open issues asking where to get them.
- Do not use this project to play games you do not own. Piracy is not
  supported, and requests for ROMs, ISOs, packages or keys will be closed.
- Online/PSN features are not implemented and never will be; the game runs
  offline only.
- The cheat and item editors change your **local** save data only. Back up
  your saves before using them.
- The software is provided "as is", without warranty of any kind (see
  [LICENSE](LICENSE)). You use it at your own risk; the authors are not liable
  for lost saves or any other damage.

## Status

Playable start to finish on Apple Silicon at 60 fps: story, battles, Item
World, movies, music, saves (including importing retail PS3 saves) and the 1.40
update with its DLC. Native macOS menus cover graphics (1×–3× internal
resolution, filter, aspect, VSync, frame cap), window, audio, controls,
save import/export, a **Cheats** menu/window and a visual **Item Editor**.
Known issues and current work are tracked in [OPERATIONS.md](OPERATIONS.md).

## What you need

- A Mac with **Apple Silicon** (M1 or newer) on **macOS 13** or later, and
  about 2 GB of free disk space.
- Your own **Disgaea D2: A Brighter Darkness (BLUS31313)** disc, dumped from
  your own PS3 or a compatible Blu-ray drive. The
  [RPCS3 quickstart guide](https://rpcs3.net/quickstart) explains how to dump
  your disc and install the PS3 system firmware from Sony.
- For the default **1.40** build: your own **1.40 update** and **DLC**
  (title NPUB31321) for this game, installed into RPCS3 from packages you
  obtained yourself. Without them, build version **1.00** instead (see step 4).
- [RPCS3](https://rpcs3.net/) (only used to install your firmware, update and
  DLC, and to decrypt the game executable).
- Xcode Command Line Tools (`xcode-select --install`), [Homebrew](https://brew.sh/)
  and Python 3.11 or newer.

## Build instructions

**1. Install the build tools**

```sh
xcode-select --install
brew install cmake ninja sdl2 ffmpeg glslang spirv-cross nlohmann-json python
```

**2. Get the source and the patched SDK**

```sh
git clone https://github.com/Sean13128/disgaea-d2-recomp.git
cd disgaea-d2-recomp
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements-lifts.txt
./tools/bootstrap_sdk.sh "$PWD/ps3recomp"
```

`bootstrap_sdk.sh` clones upstream ps3recomp at the pinned revision, verifies
the checksum of our patch and applies it.

**3. Decrypt your game executable with RPCS3**

1. In RPCS3, install the PS3 firmware, then use **File → Install Packages/Raps/Edats**
   to install your 1.40 update and DLC packages.
2. Use **Utilities → Decrypt PS3 Binaries** on:
   - the **1.40** `EBOOT.BIN` in RPCS3's `dev_hdd0/game/BLUS31313/USRDIR/`
     (on macOS RPCS3 keeps `dev_hdd0` in `~/Library/Application Support/rpcs3/`);
   - optionally the **1.00** `EBOOT.BIN` in your disc dump's `PS3_GAME/USRDIR/`.
3. Copy the resulting `EBOOT.elf` files into this repository:

```sh
mkdir -p work/v140
cp "<path to 1.40>/EBOOT.elf" work/v140/EBOOT.elf
cp "<path to 1.00>/EBOOT.elf" work/EBOOT.elf      # optional, for the 1.00 build
```

The generator checks each file's SHA256 against the supported executables in
[patches/LIFTS.json](patches/LIFTS.json) and refuses anything else.

**4. Recompile the game code and build the app**

```sh
PYTHON="$PWD/.venv/bin/python" ./tools/generate_lifts.sh --version 140
cmake -S port -B port/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DPS3RECOMP_DIR=../ps3recomp -DD2_GAME_VERSION=140 \
  -DPython3_EXECUTABLE="$PWD/.venv/bin/python" \
  -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include
cmake --build port/build --target DisgaeaD2Dist
```

For the 1.00 build (no update or DLC needed), use `--version 100` and
`-DD2_GAME_VERSION=100` in a separate build folder such as `port/build-100`.
Generating the code takes a few minutes; the first build takes longer.

Optional: `ctest --test-dir port/build --output-on-failure` runs the asset-free
test suite.

**5. Play**

```sh
open "port/dist/Disgaea D2.app"
```

On first launch the app asks for your **disc dump folder** (the one containing
`PS3_GAME`) and the matching **decrypted EBOOT.elf**. For 1.40 it then offers
**Migrate hdd0…**: choose RPCS3's `dev_hdd0` folder and it copies only the
update and DLC game content (never saves). Saves, settings and logs live in
`~/Library/Application Support/DisgaeaD2Recomp/` and
`~/Library/Logs/DisgaeaD2Recomp/`. Retail PS3 saves can be imported from the
**Game** menu.

The built app is for you only; please don't share it (see the disclaimer).

## Controls and menus

- Keyboard (click the game window first): arrows = D-pad, **Z** = Cross,
  **X / Esc / Backspace** = Circle, **A** = Square, **S** = Triangle,
  **Q / W** = L1 / R1, **1 / 2** = L2 / R2, **Space** = Start, **Shift** = Select.
  Return presses Cross and Start together. SDL2 gamepads (Xbox, PlayStation,
  MFi) take over automatically when connected.
- **Menu bar** (click the game window first; in fullscreen move the mouse to
  the top edge): Graphics, Window, Audio, Game, **Cheats**, Controls.
- **F1 / ⌘⇧C** opens the Cheats window; **Cheats → Item Editor…** opens the
  item editor.
- **F2** flags an issue: it saves a screenshot, frame rate, map and CPU use, and
  an optional note, to `flags/flags.jsonl` in the Application Support folder,
  so you can attach it to a bug report.

## Reporting issues

Open a GitHub issue with your Mac model, macOS version, game version (1.00 or
1.40), what you were doing, and the relevant F2 flag entry or
`~/Library/Logs/DisgaeaD2Recomp/latest.log` excerpt. Never attach game files,
decrypted executables or generated code.

## Credits

- [ps3recomp](https://github.com/sp00nznet/ps3recomp) by sp00nznet, the
  recompiler and runtime this port is built on.
- The [RPCS3](https://rpcs3.net/) team, whose open research into the PS3 made
  this possible.
- The Disgaea modding and cheat communities for documenting the game's data.
- Third-party components and licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Developer notes

[SDK.lock](patches/SDK.lock) pins upstream base `a679051`, audited local revision
(see `revision` in the lock), the patched Git tree and combined patch SHA256. Bootstrap clones a new
SDK, checks the checksum, checks out the exact base and applies only that patch.
It verifies the resulting tree without creating a commit. Existing destination
directories and mismatches are errors. Later SDK changes require an audited patch
re-export and lock update; local uncommitted SDK edits are not included.

[LIFTS.json](patches/LIFTS.json) maps each supported ELF SHA256 to its loader,
PPU lift and SPU extraction/registration commands. It fixes
`PS3RECOMP_CHUNK_LINES=50000`, `PYTHONHASHSEED=0` and four lifter workers. The SPU
builder invokes the SDK lifter with separate symbol prefixes and registers both
full-image and executable-segment fingerprints. No hand-edited lift is required.
CMake generates the canonical HLE NID table in the selected build directory.
Generated loader metadata goes to `port/out*`, PPU code to `port/src/recomp*`,
and embedded SPU images/code to `port/spu*`. Each output metadata directory
contains a `generation.json` receipt. Remove an old generated SPU tree before
regenerating, or use a fresh output directory.

To generate just one version or keep outputs external:

```sh
PYTHON="$PWD/.venv/bin/python" ./tools/generate_lifts.sh \
  --sdk /absolute/path/to/sdk --version 100 --elf /absolute/path/to/EBOOT.elf \
  --port-dir /absolute/path/to/lifts
```

CMake defaults to the project's `ps3recomp` SDK and version 140 outputs. Explicit
`PS3RECOMP_DIR`, `RECOMP_DIR`, `SPU_DIR` and `D2_OUT_DIR` overrides are preserved;
relative values are resolved against `port/`. For external version 100 outputs,
configure with `-DD2_GAME_VERSION=100 -DRECOMP_DIR=/absolute/path/to/lifts/src/recomp
-DSPU_DIR=/absolute/path/to/lifts/spu -DD2_OUT_DIR=/absolute/path/to/lifts/out` and
the chosen SDK path. `D2_OUT_DIR` identifies generation metadata; the runner
loads the supplied ELF directly. Omit output overrides to switch between the
default version trees. Clear previously cached overrides with
`-U RECOMP_DIR -U SPU_DIR -U D2_OUT_DIR` to return to defaults. The 100 runner uses `work/EBOOT.elf`, the 140 runner uses
`work/v140/EBOOT.elf`; mismatched versions are rejected.

The maintained [asset-free test suite](port/tests/README.md) also runs without
any game files or configured game build. CTest reports unavailable Metal checks
as **Skipped** (exit 77), separately from CPU passes. Test headers come from the
selected SDK and editor schema; both 1.00 and 1.40 editor profiles are exercised.

macOS keys privacy grants (e.g. external-drive access) to the code signature.
Ad-hoc signatures change every build, so run `tools/make_signing_identity.sh` once
and import `signing/d2-signing.p12` into your login keychain (command printed by
the script). Packaging then signs with that stable identity automatically, and
falls back to ad-hoc signing without it.

`port/play.sh` runs the build without the app bundle; `port/capture.sh`
captures diagnostics. See [OPERATIONS.md](OPERATIONS.md) for the development
log, findings and validation limits.
