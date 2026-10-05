#!/bin/bash
# AF only: copy saves/content, show a page, capture the in-window Metal menu.
# AF_HEADLESS=1 tests state/save behavior without claiming a visual pass.
# AF_VERSION=100 or 140; AF_SKIP_BUILD=1 uses the existing matching AF build.
# Usage: bash codex/AF.host-check.sh [general|characters|items|presets|verify|all]
set -euo pipefail
cd "$(dirname "$0")/.."
version=${AF_VERSION:-140}
case "$version" in 100) elf=work/EBOOT.elf;; 140) elf=work/v140/EBOOT.elf;; *) exit 2;; esac
mode=${1:-general}
case "$mode" in general|characters|items|presets|verify) modes=("$mode");; all) modes=(general characters items presets);; *) exit 2;; esac
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/AF-host.XXXXXX)
trap 'if [[ ${AF_KEEP_HDD:-0} != 1 ]]; then rm -rf "$scratch"; fi' EXIT
out=$(mktemp -d "$PWD/port/runs/AF-host.XXXXXX")
if [[ ${AF_SKIP_BUILD:-0} != 1 ]]; then
    (cd port; cmake -B build-af -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp -DD2_GAME_VERSION="$version" \
        -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
        -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
    cmake --build port/build-af -j4 > "$out/build.log" 2>&1
fi
grep -q "D2_GAME_VERSION:STRING=$version" port/build-af/CMakeCache.txt || { echo 'AF build version mismatch'; exit 1; }
unset PAD_FILE D2_WARP_STAGE D2_CHEATS_TEST_HL D2_CHEATS_TEST_SAVE D2_CHEATS_TEST_EDIT
export PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]"
export D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_01
export PS3RECOMP_METAL_HEADLESS=${AF_HEADLESS:-0} PS3RECOMP_RSX_FIFO_ONLY=${AF_HEADLESS:-0}
for page in "${modes[@]}"; do
    case "$page" in general|verify) index=0;; characters) index=1;; items) index=2;; presets) index=3;; esac
    mkdir -p "$out/$page/frames" "$scratch/$page"
    cp -R port/hdd0 "$scratch/$page/hdd0"
    # Reuse a private copy of the established FIOS cache to fit the 40s run.
    [[ ! -d port/hdd1 ]] || cp -R port/hdd1 "$scratch/$page/hdd1"
    if [[ $version == 140 ]]; then port/install-content.sh --into "$scratch/$page/hdd0" > "$out/$page/install.log"; fi
    export PS3_HDD0_ROOT="$scratch/$page/hdd0" PS3_HDD1_ROOT="$scratch/$page/hdd1"
    export PS3RECOMP_METAL_FRAME_DUMP="$out/$page/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=120
    export D2_CHEATS_OPEN_PAGE="$index" PAD_SCRIPT='10:0x4000,14:0x4000'
    if [[ $page == verify ]]; then
        export D2_CHEATS_TEST_HL=993701506632 D2_CHEATS_TEST_SAVE=1 D2_CHEATS_TEST_EDIT=1
    fi
    status=0
    perl -e 'alarm shift; exec @ARGV' 40 ./port/build-af/DisgaeaD2Recomp "$elf" > "$out/$page/run.log" 2>&1 || status=$?
    [[ $status == 142 ]] || { echo "FAIL $page: exit $status ($out)"; exit 1; }
    grep -q "LOAD complete for 'NPUB31321_NORMAL_01'" "$out/$page/run.log"
    grep -q 'D2 cheats.*HL=993701506631 party=118' "$out/$page/run.log"
    grep -q "sys overlay.*title='D2 cheats" "$out/$page/run.log"
    if grep -qE 'FAULT|Bus error|OOB access|test add/remove.*FAIL' "$out/$page/run.log"; then echo "FAIL $page ($out)"; exit 1; fi
    if [[ $page == verify ]]; then
        grep -q "SAVE complete for 'NPUB31321_NORMAL_01'" "$out/$page/run.log"
        .venv/bin/python codex/AF.save-check.py \
            port/hdd0/home/00000001/savedata/NPUB31321_NORMAL_01 \
            "$scratch/$page/hdd0/home/00000001/savedata/NPUB31321_NORMAL_01" > "$out/$page/save-diff.log"
        cat "$out/$page/save-diff.log"
    fi
    if [[ ${AF_HEADLESS:-0} != 1 ]]; then
        grep -q 'Metal backend init OK' "$out/$page/run.log"
        compgen -G "$out/$page/frames/f*.ppm" > /dev/null
        .venv/bin/python - "$out/$page/frames" <<'PY'
from pathlib import Path
import subprocess, sys
folder=Path(sys.argv[1]); frames=sorted(folder.glob('f*.ppm'),key=lambda p:int(p.stem[1:]))
for p in frames[-3:]:
    subprocess.run(['sips','-s','format','png',str(p),'--out',str(p.with_suffix('.png'))],check=True,stdout=subprocess.DEVNULL)
PY
    fi
    grep -nE 'D2 cheats.*(resolved|unit=0 |write|add item|test)|sys overlay.*open|SAVE complete' "$out/$page/run.log" > "$out/$page/evidence.txt"
    echo "PASS $page state: $out/$page/evidence.txt"
done
printf 'Output: %s\n' "$out"
if [[ ${AF_KEEP_HDD:-0} == 1 ]]; then printf 'Copied HDD: %s\n' "$scratch"; fi
echo 'Visual check: inspect the last frames. F1 or Cmd+Shift+C opens/closes; Q/W change pages; arrows navigate; Z edits; A cycles step; X backs out. Guest pad input is captured while open.'
