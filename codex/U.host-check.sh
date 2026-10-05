#!/bin/bash
# Real Metal by default. U_HEADLESS=1 runs the GPU-free draw tracer instead.
# U_ADVANCE=0 omits the extra battle dialogue/button advances.
# Save selection is unattended; this probe never saves or changes the dump.
set -euo pipefail
cd "$(dirname "$0")/.."
stage=${D2_WARP_STAGE:-1}
if [[ ! "$stage" =~ ^[0-9]{1,5}$ ]] || (( 10#$stage < 1 || 10#$stage > 65535 )); then
  echo 'D2_WARP_STAGE must be 1..65535 (1 aliases map 101)'; exit 1
fi
stage=$((10#$stage))
if (( stage < 100 )); then stage=$((stage + 100)); fi
printf -v map_path '/Data/MAP/mp%03d/map%03d%02d.lzs' "$((stage / 100))" "$((stage / 100))" "$((stage % 100))"
out=$(mktemp -d "$PWD/port/runs/U-host.XXXXXX")
mkdir -p "$out/frames" "$out/draws"
if [[ ${U_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-u -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
    -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
    -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-u --target DisgaeaD2Recomp -j 4 > "$out/build.log" 2>&1
fi
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY PAD_FILE PAD_SCRIPT
unset SPU_DMATRACE_ALL YDKJ_DMA_IMG NV3089_GATE
if [[ ${U_HEADLESS:-0} == 1 ]]; then
  export PS3RECOMP_METAL_HEADLESS=1 PS3RECOMP_RSX_FIFO_ONLY=1
fi
pad='10:0x4000,14:0x4000'
if [[ ${U_ADVANCE:-1} == 1 ]]; then
  pad="$pad,22:0x4000,26:0x4000,30:0x4000,34:0x4000,38:0x4000"
fi
logfile="$out/run.log"
status=0
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$PWD/port/hdd0" \
D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
D2_WARP_STAGE="$stage" D2_BOOT_TRACE=1 PAD_TRACE=1 \
PAD_SCRIPT="${U_PAD_SCRIPT:-$pad}" \
PS3RECOMP_METAL_FRAME_DUMP="$out/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=120 \
D2_DRAW_TRACE="$out/draws" D2_DRAW_TRACE_MAX_FRAME=2400 \
D2_DRAW_TRACE_TEXTURE_LIMIT="${U_TEXTURE_LIMIT:-24}" \
  perl -e 'alarm shift; exec @ARGV' 40 \
  ./port/build-u/DisgaeaD2Recomp work/EBOOT.elf > "$logfile" 2>&1 || status=$?
printf 'Capture: %s\nExit: %s (142 is the expected 40-second timeout)\n' "$out" "$status" | tee "$out/summary.txt"
grep -nE 'LOAD complete|\[D2-warp\]|/Data/MAP/mp|\[d2-boot\]|Metal backend|FIFO timing|\[F-present\]|\[V-surface\]' \
  "$logfile" > "$out/metrics.txt" || true
grep -nE 'LOAD complete|\[D2-warp\]|/Data/MAP/mp|Metal backend|FIFO timing' \
  "$logfile" | tail -n 24 | tee -a "$out/summary.txt" || true
if [[ "$status" != 142 ]] || ! grep -q 'LOAD complete for.*NPUB31321_NORMAL_00' "$logfile" \
  || ! grep -q '\[D2-warp\] confirm stage=' "$logfile" \
  || ! grep -Fq "$map_path" "$logfile"; then
  echo 'FAIL: Continue-to-battle transition did not complete; inspect run.log' | tee -a "$out/summary.txt"
  exit 1
fi
if [[ ${U_HEADLESS:-0} != 1 ]]; then
  if ! grep -q '\[rsx\] Metal backend init OK' "$logfile" || ! compgen -G "$out/frames/f*.ppm" > /dev/null; then
    echo 'FAIL: real Metal/frame dumps unavailable; run U_HEADLESS=1 for guest-only evidence' | tee -a "$out/summary.txt"
    exit 1
  fi
fi
echo 'PASS: guest entered the requested battle. Inspect frames after warp; this does not assert visual correctness.' | tee -a "$out/summary.txt"
