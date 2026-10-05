#!/bin/bash
# Uses only build-y and a save copy. No frame dumps or deletion.
# Y_BINARY=./port/build-y/Y-baseline permits the matched pre-fix comparison.
# Y_MANUAL=1 loads Continue, then lets the user walk into Castle Hallway.
set -euo pipefail
cd "$(dirname "$0")/.."
seconds=${Y_SECONDS:-60}
if [[ ! "$seconds" =~ ^[0-9]+$ ]] || (( seconds < 40 )); then
  echo 'Y_SECONDS must be >=40'; exit 1
fi
out=$(mktemp -d "$PWD/port/runs/Y-host.XXXXXX")
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-Y-host.XXXXXX)
printf '%s\n' "$scratch" > "$out/scratch.txt"
mkdir -p "$scratch/hdd0" "$scratch/hdd1"
cp -R port/hdd0/. "$scratch/hdd0/"
if [[ ${Y_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-y -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
    -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-y --target DisgaeaD2Recomp -j 4 > "$out/build.log" 2>&1
fi
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY PAD_FILE PAD_SCRIPT PAD_STICK PAD_SWEEP
unset D2_WARP_STAGE D2_DRAW_TRACE PS3RECOMP_METAL_FRAME_DUMP PS3RECOMP_METAL_OVERLAY_CAPTURE
if [[ ${Y_HEADLESS:-0} == 1 ]]; then export PS3RECOMP_METAL_HEADLESS=1; fi
if [[ ${Y_FIFO_ONLY:-0} == 1 ]]; then export PS3RECOMP_RSX_FIFO_ONLY=1; fi
pad='10:0x4000,14:0x4000,18:0x4000'
if [[ ${Y_MANUAL:-0} != 1 ]]; then
  # Replay nav1's Down, Left, Left, Down route; each press has a release gap.
  pad="$pad,24:0x0040,24.25:0x0040,24.5:0x0040,26:0x0080,26.25:0x0080,26.5:0x0080,28:0x0080,28.25:0x0080,28.5:0x0080,30:0x0040,30.25:0x0040,30.5:0x0040,30.75:0x0040,31:0x0040"
fi
logfile="$out/run.log"
printf 'Log: %s\nRemain in Castle Hallway (map30001) through the measurement.\n' "$logfile"
status=0
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
GCM_FLIP_TRACE=1 GCM_RECYCLE_TRACE=1 GCM_FLIPCOUNT=1 D2_WARP_TRACE=1 \
PS3_HOST_CPU=1 PAD_SCRIPT="${Y_PAD_SCRIPT:-$pad}" \
  perl -e 'alarm shift; exec @ARGV' "$seconds" \
  "${Y_BINARY:-./port/build-y/DisgaeaD2Recomp}" work/EBOOT.elf > "$logfile" 2>&1 || status=$?
printf 'Exit: %s (142 is the expected alarm)\n' "$status" | tee "$out/summary.txt"
grep -nE '\[D2-warp\]|\[gcm-rate\]|\[HOSTCPU\]|LOAD complete|map30001|backend init|FIFO timing' \
  "$logfile" > "$out/metrics.txt" || true
if [[ "$status" != 142 ]]; then
  echo 'FAIL: game exited before alarm; inspect run.log' | tee -a "$out/summary.txt"; exit 1
fi
if [[ ${Y_HEADLESS:-0} != 1 ]] && ! grep -q '\[rsx\] Metal backend init OK' "$logfile"; then
  echo 'FAIL: real Metal unavailable; headless cannot establish renderer throughput' | tee -a "$out/summary.txt"; exit 1
fi
if ! grep -q 'LOAD complete for.*NPUB31321_NORMAL_00' "$logfile"; then
  echo 'FAIL: requested save did not load' | tee -a "$out/summary.txt"; exit 1
fi
python3 codex/Y.analyze.py "$logfile" | tee -a "$out/summary.txt"
if grep -qE 'fifo recycle waiting|ref queue overflow|HOST CORRUPTION' "$logfile"; then
  echo 'FAIL: FIFO/corruption warning in run.log' | tee -a "$out/summary.txt"; exit 1
fi
if [[ ${Y_HEADLESS:-0} == 1 ]]; then
  echo 'Headless timing does not establish visible Metal speed.' | tee -a "$out/summary.txt"
fi
printf 'Measurements: %s\nCopied save retained: %s\n' "$out" "$scratch"
