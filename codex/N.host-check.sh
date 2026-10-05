#!/bin/bash
# Build only N's directory, then launch through Finder/LaunchServices.
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
root="$PWD"
mode="${1:-build}"
case "$mode" in build|launch-only) ;; *) echo 'Usage: bash codex/N.host-check.sh [build|launch-only]'; exit 2 ;; esac
mkdir -p port/runs
run="$(mktemp -d "$root/port/runs/N-host.XXXXXX")"
echo "Build/check logs: $run"
if [ "$mode" = build ]; then
(
    cd port
    cmake -B build-n -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
        -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
        -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include
    cmake --build build-n -j 4
) > "$run/build.log" 2>&1 || { tail -40 "$run/build.log"; exit 1; }
fi
app="$root/port/dist/Disgaea D2.app"
plutil -lint "$app/Contents/Info.plist"
codesign --verify --deep --strict "$app"
find "$app/Contents" -type f \( -name '*.dylib' -o -name DisgaeaD2Recomp \) \
    -exec otool -L '{}' \; > "$run/dylibs.log"
if grep -q '/opt/homebrew' "$run/dylibs.log"; then
    echo 'Unbundled Homebrew dependency; inspect dylibs.log'; exit 1
fi
echo 'Launching the app. If prompted, choose the BLUS31313 dump and work/EBOOT.elf.'
echo 'Try Cmd+F and Cmd+Ctrl+F, then resize wide/tall: artwork should keep its aspect ratio.'
echo 'Try input and audio. Cmd+Q quits. The app will remain running after this check.'
open -n "$app"
sleep 40
log="$HOME/Library/Logs/DisgaeaD2Recomp/latest.log"
grep -n -E 'D2 launcher|game_root=|eboot=|hdd[01]=|backend init|SDL .*backend|presented guest frame|fullscreen toggle|FAULT|SIGNAL|ERROR' \
    "$log" | tail -50 || true
grep -q '\[D2 launcher\]' "$log"
grep -q 'Metal backend init OK' "$log"
grep -q 'presented guest frame' "$log"
echo "Launch verified. Saves/cache: $HOME/Library/Application Support/DisgaeaD2Recomp/{hdd0,hdd1}"
echo "Game log: $log"
