#!/bin/bash
# Automated real-Metal portrait check; only build-ah, private saves/settings.
# Captures, OCR and input evidence are retained. No gameplay state writes.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p port/runs
out=$(mktemp -d "$PWD/port/runs/AH-portrait.XXXXXX")
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/AH-portrait.XXXXXX)
printf 'Evidence: %s\nPrivate saves/cache: %s\n' "$out" "$scratch"
printf '%s\n' "$scratch" > "$out/scratch.txt"
if [[ ${AH_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-ah -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
    -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-ah --target DisgaeaD2Recomp -j 3 > "$out/build.log" 2>&1
fi
grep -q 'D2_GAME_VERSION:STRING=140' port/build-ah/CMakeCache.txt
clang -fobjc-arc codex/AH.ocr.m -framework Vision -framework Foundation -framework CoreGraphics \
  -o port/build-ah/AH-ocr > "$out/ocr-build.log" 2>&1
cp -R port/hdd0 "$scratch/hdd0"
if [[ -d port/hdd1 ]]; then cp -R port/hdd1 "$scratch/hdd1"; fi
test -f "$scratch/hdd0/home/00000001/savedata/NPUB31321_NORMAL_01/SAVEDATA.DAT"
mkdir -p "$out/frames" "$out/draws" "$scratch/hdd1"
pad="$scratch/pad.txt"
: > "$pad"
unset PAD_SCRIPT PAD_STICK PAD_SWEEP D2_CHEATS_OPEN_PAGE D2_CHEATS_TEST_HL D2_CHEATS_TEST_SAVE
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY D2_DRAW_TRACE_EVERY
seconds=${AH_SECONDS:-180}
[[ $seconds =~ ^[0-9]+$ ]] && (( seconds >= 40 ))
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
D2_SETTINGS_PATH="$scratch/settings.json" D2_SETTINGS_OVERRIDE='{"scale":1,"frame_cap":60}' \
PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_01 D2_WARP_STAGE=1 D2_MOVIE_SKIP=1 \
PAD_FILE="$pad" PAD_TRACE=1 PAD_NO_KEYBOARD=1 \
D2_DRAW_TRACE="$out/draws" D2_DRAW_TRACE_NEW_PIPELINES=1 D2_DRAW_TRACE_MIN_FRAME=1 \
D2_DRAW_TRACE_MAX_FRAME=1 D2_DRAW_TRACE_TEXTURE_LIMIT=0 \
PS3RECOMP_METAL_FRAME_DUMP="$out/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=60 \
  perl -e 'alarm shift; exec @ARGV' "$seconds" ./port/build-ah/DisgaeaD2Recomp work/v140/EBOOT.elf \
  > "$out/run.log" 2>&1 &
runner=$!
# Always stop just our runner if OCR/control fails; retain every evidence file.
trap 'kill "$runner" 2>/dev/null || true' EXIT
python3 codex/AH.portrait-drive.py "$out" "$pad" "$PWD/port/build-ah/AH-ocr" "$seconds" \
  > "$out/driver.log" 2>&1 &
driver=$!
for ((t=0; t<20; t++)); do
  if grep -q 'no Metal device' "$out/run.log"; then
    kill "$driver" 2>/dev/null || true
    echo 'FAIL: real Metal unavailable; no portrait verification'; exit 1
  fi
  if grep -q 'Metal backend init OK' "$out/run.log"; then break; fi
  sleep 1
done
if ! wait "$driver"; then
  tail -5 "$out/driver.log"
  echo "FAIL: automated navigation did not confirm the portrait. Evidence: $out"; exit 1
fi
grep -q 'Metal backend init OK' "$out/run.log"
grep -q "LOAD complete for 'NPUB31321_NORMAL_01'" "$out/run.log"
grep -q 'D2-warp.*confirm stage=101' "$out/run.log"
grep -q '\[V-stencil\] enabled=1 ref=255.*masks=FF/FF.*ops=1E01/1E01/1E01' "$out/run.log"
if grep -qE 'FAULT|OOB access|HOST CORRUPTION|command buffer failed|pipeline state failed' "$out/run.log"; then
  echo "FAIL: runtime/render error ($out/run.log)"; exit 1
fi
grep -nE 'AH-portrait|AH-pad.*execute' "$out/driver.log"
echo "PASS: slot 01 -> battle 101 -> queued attack; three portrait frames have transparent corners ($out)"
