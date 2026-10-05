#!/bin/bash
# Uses only build-ab and a save copy. No frame dumps or deletion.
# AB_BINARY=./port/build-ab/AB-baseline permits the matched pre-change comparison.
# AB_MANUAL=1 loads Continue, then lets the user walk into Castle Hallway.
set -euo pipefail
cd "$(dirname "$0")/.."
seconds=${AB_SECONDS:-60}
if [[ ! "$seconds" =~ ^[0-9]+$ ]] || (( seconds < 40 )); then
  echo 'AB_SECONDS must be >=40'; exit 1
fi
out=$(mktemp -d "$PWD/port/runs/AB-host.XXXXXX")
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-AB-host.XXXXXX)
printf '%s\n' "$scratch" > "$out/scratch.txt"
mkdir -p "$scratch/hdd0" "$scratch/hdd1"
cp -R port/hdd0/. "$scratch/hdd0/"
if [[ ${AB_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-ab -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
    -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-ab --target DisgaeaD2Recomp -j 4 > "$out/build.log" 2>&1
fi
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY PAD_FILE PAD_SCRIPT PAD_STICK PAD_SWEEP
unset D2_WARP_STAGE D2_DRAW_TRACE PS3RECOMP_METAL_FRAME_DUMP PS3RECOMP_METAL_OVERLAY_CAPTURE
if [[ ${AB_HEADLESS:-0} == 1 ]]; then export PS3RECOMP_METAL_HEADLESS=1; fi
if [[ ${AB_FIFO_ONLY:-0} == 1 ]]; then export PS3RECOMP_RSX_FIFO_ONLY=1; fi
if [[ ${AB_RECORD:-0} == 1 ]]; then
  export RSX_FIFO_RECORD="$out/hallway.fifo" RSX_FIFO_RECORD_FRAME="${AB_RECORD_FRAME:-2040}"
  export RSX_FIFO_RECORD_FRAMES="${AB_RECORD_FRAMES:-4}"
fi
if [[ ${AB_ENGINE_NULL:-0} == 1 ]]; then
  # Reuse the existing GPU-free draw-engine backend, with artifact writes disabled.
  export D2_DRAW_TRACE="$scratch" D2_DRAW_TRACE_MIN_FRAME=999999999
  export D2_DRAW_TRACE_MAX_FRAME=1 D2_DRAW_TRACE_TEXTURE_LIMIT=0
fi
pad='10:0x4000,14:0x4000,18:0x4000'
if [[ ${AB_MANUAL:-0} != 1 ]]; then
  # Replay nav1's Down, Left, Left, Down route; each press has a release gap.
  pad="$pad,24:0x0040,24.25:0x0040,24.5:0x0040,26:0x0080,26.25:0x0080,26.5:0x0080,28:0x0080,28.25:0x0080,28.5:0x0080,30:0x0040,30.25:0x0040,30.5:0x0040,30.75:0x0040,31:0x0040"
fi
logfile="$out/run.log"
printf 'Log: %s\nRemain in Castle Hallway (map30001) through the measurement.\n' "$logfile"
status=0
# Measure first; profiling must not distort the completed-flip window.
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
GCM_FLIP_TRACE=1 GCM_RECYCLE_TRACE=1 GCM_FLIPCOUNT=1 D2_WARP_TRACE=1 \
PS3_HOST_CPU=1 PAD_SCRIPT="${AB_PAD_SCRIPT:-$pad}" \
  perl -e 'alarm shift; exec @ARGV' "$((seconds + 12))" \
  "${AB_BINARY:-./port/build-ab/DisgaeaD2Recomp}" work/EBOOT.elf > "$logfile" 2>&1 &
pid=$!
sleep "$seconds"
cp "$logfile" "$out/measured.log"
if command -v sample >/dev/null 2>&1 && kill -0 "$pid" 2>/dev/null; then
  sample "$pid" 8 -file "$out/profile.txt" > "$out/sample.log" 2>&1 || true
fi
if [[ -s "$out/profile.txt" ]]; then
  python3 codex/AB.profile.py "$out/profile.txt" > "$out/ppu-profile.txt"
else
  printf '%s\n' 'PPU profile unavailable; inspect sample.log (sandbox task inspection may be denied).' > "$out/ppu-profile.txt"
fi
wait "$pid" || status=$?
printf 'Exit: %s (142 is the expected alarm)\n' "$status" | tee "$out/summary.txt"
grep -nE '\[D2-warp\]|\[gcm-rate\]|\[HOSTCPU\]|LOAD complete|map30001|backend init|FIFO timing' \
  "$logfile" > "$out/metrics.txt" || true
if [[ "$status" != 142 ]]; then
  echo 'FAIL: game exited before alarm; inspect run.log' | tee -a "$out/summary.txt"; exit 1
fi
if [[ ${AB_HEADLESS:-0} != 1 ]] && ! grep -q '\[rsx\] Metal backend init OK' "$logfile"; then
  echo 'FAIL: real Metal unavailable; headless cannot establish renderer throughput' | tee -a "$out/summary.txt"; exit 1
fi
if ! grep -q 'LOAD complete for.*NPUB31321_NORMAL_00' "$logfile"; then
  echo 'FAIL: requested save did not load' | tee -a "$out/summary.txt"; exit 1
fi
python3 codex/Y.analyze.py "$out/measured.log" | tee -a "$out/summary.txt"
cat "$out/ppu-profile.txt" | tee -a "$out/summary.txt"
if grep -qE 'fifo recycle waiting|ref queue overflow|HOST CORRUPTION' "$logfile"; then
  echo 'FAIL: FIFO/corruption warning in run.log' | tee -a "$out/summary.txt"; exit 1
fi
if [[ ${AB_HEADLESS:-0} == 1 ]]; then
  echo 'Headless timing does not establish visible Metal speed.' | tee -a "$out/summary.txt"
fi
printf 'Measurements: %s\nCopied save retained: %s\n' "$out" "$scratch"
if [[ ${AB_HEADLESS:-0} != 1 ]]; then
  python3 - "$out/summary.txt" <<'PYRATE'
import re, sys
text = open(sys.argv[1]).read()
fps = float(re.search(r'Castle Hallway: ([0-9.]+)', text)[1])
print('PASS: hallway >=59.5 distinct flips/s' if fps >= 59.5 else 'TARGET MISSED: hallway <59.5 distinct flips/s')
sys.exit(0 if fps >= 59.5 else 2)
PYRATE
fi
