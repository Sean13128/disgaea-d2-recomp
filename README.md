# Disgaea D2 — native macOS port

Disgaea D2: A Brighter Darkness (PS3, BLUS31313), statically recompiled to native
arm64 macOS using [ps3recomp](https://github.com/sp00nznet/ps3recomp) and Metal.
No game data, decrypted executables, generated lifts, or saves are tracked.

Build prerequisites: macOS arm64, Xcode command-line tools, Python 3.11+, Git,
CMake and Ninja. Homebrew supplies SDL2, FFmpeg, glslang, spirv-cross and
nlohmann-json (`brew install cmake ninja sdl2 ffmpeg glslang spirv-cross nlohmann-json`).
Verified toolchain: Apple clang 21.0.0, CMake 4.4.3, Ninja 1.13.2, Python 3.14.5.

From the project root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements-lifts.txt
./tools/bootstrap_sdk.sh "$PWD/ps3recomp"
# Supply your own decrypted ELFs: work/EBOOT.elf (1.00), work/v140/EBOOT.elf (1.40).
PYTHON="$PWD/.venv/bin/python" ./tools/generate_lifts.sh
cmake -S port -B port/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DPS3RECOMP_DIR=../ps3recomp -DD2_GAME_VERSION=140 \
  -DPython3_EXECUTABLE="$PWD/.venv/bin/python" \
  -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
  -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include
cmake --build port/build --target DisgaeaD2Recomp -j 4
ctest --test-dir port/build -N
ctest --test-dir port/build --output-on-failure
```

[SDK.lock](patches/SDK.lock) pins upstream base `a679051`, audited local revision
`5b24f49`, the patched Git tree and combined patch SHA256. Bootstrap clones a new
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

Play with `port/play.sh`; diagnose with `port/capture.sh`. Build an app bundle
explicitly with `cmake --build port/build --target DisgaeaD2Dist`. Content and
saves remain external. See [OPERATIONS.md](OPERATIONS.md) for controls, content
installation, findings and current validation limits.
