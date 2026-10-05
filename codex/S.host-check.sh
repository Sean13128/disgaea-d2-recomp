#!/bin/bash
# Real-Mac loaded-save measurement. S_HEADLESS=1 runs the identical sandbox path.
# S_SKIP_BUILD=1 S_BINARY=port/build-s/DisgaeaD2Recomp.before selects baseline.
set -eu
cd "$(dirname "$0")/.."
seconds=${S_SECONDS:-140}
if (( seconds < 130 )); then echo 'S_SECONDS must be >=130 for the loaded-map window'; exit 1; fi
out="$PWD/port/runs/S-${S_LABEL:-host}-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-S.XXXXXX)
printf '%s\n' "$scratch" > "$out/scratch.txt"
mkdir -p "$scratch/hdd0" "$scratch/hdd1"
cp -R port/hdd0/. "$scratch/hdd0/"
if [[ ${S_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-s -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
    -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
    -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-s --target DisgaeaD2Recomp -j 4 > "$out/build.log" 2>&1
fi
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY PAD_FILE
if [[ ${S_HEADLESS:-0} == 1 ]]; then export PS3RECOMP_METAL_HEADLESS=1; fi
# Explicit diagnostic mode: drains FIFO without the sandbox's software drawing.
if [[ ${S_FIFO_ONLY:-0} == 1 ]]; then export PS3RECOMP_RSX_FIFO_ONLY=1; fi
pad='75:0x4000'
for ((t=79; t<seconds; t+=4)); do pad="$pad,$t:0x4000"; done
logfile="$out/map.log"
start=$(date +%s)
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
PAD_SCRIPT="$pad" PS3_HOST_CPU=1 D2_BOOT_TRACE=1 GCM_FLIPCOUNT=1 PAD_TRACE=1 \
  perl -e 'alarm shift; exec @ARGV' "$seconds" \
  "./${S_BINARY:-port/build-s/DisgaeaD2Recomp}" work/EBOOT.elf > "$logfile" 2>&1 &
pid=$!
printf 'elapsed_s cpu_pct frames flips\n' > "$out/map.samples"
sampled=0
while kill -0 "$pid" 2>/dev/null; do
  sleep 5
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  elapsed=$(($(date +%s)-start))
  cpu=$(ps -p "$pid" -o pcpu= 2>/dev/null || true)
  record=$(grep '\[d2-boot\] frames=' "$logfile" | tail -1 || true)
  frames=$(printf '%s\n' "$record" | sed -n 's/.*frames=\([0-9]*\).*/\1/p')
  flips=$(printf '%s\n' "$record" | sed -n 's/.*flip_requests=\([0-9]*\).*/\1/p')
  printf '%s %s %s %s\n' "$elapsed" "${cpu:-0}" "${frames:-0}" "${flips:-0}" >> "$out/map.samples"
  if (( sampled == 0 && elapsed >= 115 )); then
    sample "$pid" 8 -file "$out/map.sample.txt" > "$out/sample-command.log" 2>&1 &
    sample_pid=$!
    sampled=1
  fi
done
status=0
wait "$pid" || status=$?
if (( sampled )); then wait "$sample_pid" || true; fi
printf 'map exit=%s (142 is expected timeout)\n' "$status" | tee "$out/summary.txt"
printf 'headless=%s fifo_only=%s binary=%s\n' "${S_HEADLESS:-0}" "${S_FIFO_ONLY:-0}" "${S_BINARY:-port/build-s/DisgaeaD2Recomp}" | tee -a "$out/summary.txt"
if ! grep -q 'LOAD complete for.*NPUB31321_NORMAL_00' "$logfile"; then
  echo 'FAIL: requested save was not loaded' | tee -a "$out/summary.txt"
  exit 1
fi
if [[ ${S_HEADLESS:-0} != 1 ]] && ! grep -q '\[rsx\] Metal backend init OK' "$logfile"; then
  echo 'FAIL: real Metal did not initialize' | tee -a "$out/summary.txt"
  exit 1
fi
grep -E '\[gcm-rate\]|\[d2-boot\]|\[HOSTCPU\] process=|LOAD complete for|/Data/MAP/' "$logfile" > "$out/map.metrics" || true
awk 'NR>1 && $1>=105 {cpu+=$2; n++; if(!first) {first=$1; f=$3; g=$4} last=$1; l=$3; h=$4}
  END {if(n) printf "ps CPU mean: %.1f%% (%d samples)\n",cpu/n,n;
       if(last>first) printf "Guest frames/s: %.2f; flips/s: %.2f (%ds window)\n",(l-f)/(last-first),(h-g)/(last-first),last-first}' \
  "$out/map.samples" | tee -a "$out/summary.txt"
# HOSTCPU uses getrusage and works when sandboxed ps reports zero.
awk '/\[HOSTCPU\] process=/ {i++; if(i>=21) {split($2,a,"="); sum+=a[2]; n++}}
  END {if(n) printf "getrusage CPU mean: %.1f%% (%d intervals, >=105s)\n",sum/n,n}' \
  "$logfile" | tee -a "$out/summary.txt"
printf 'Measurements: %s\nSave copy retained: %s\n' "$out" "$scratch"
