#!/bin/bash
# Real Metal title, then Continue slot 01 -> hub -> battle, each on copied hdd0.
# AD_HEADLESS=1 verifies guest flow without Metal. No save/dump writes.
set -euo pipefail
cd "$(dirname "$0")/.."
out=$(mktemp -d "$PWD/port/runs/AD-host.XXXXXX")
if [[ ${AD_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-ad -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp -DD2_GAME_VERSION=140 \
    -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
    -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-ad --target DisgaeaD2Recomp -j 4 > "$out/build.log" 2>&1
fi
unset PAD_SCRIPT PAD_FILE D2_WARP_STAGE PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY
if [[ ${AD_HEADLESS:-0} == 1 ]]; then
  export PS3RECOMP_METAL_HEADLESS=1 PS3RECOMP_RSX_FIFO_ONLY=1
fi
export PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]"
export D2_MOVIE_SKIP=1 D2_BOOT_TRACE=1 PS3_NPDRM_TRACE=1
for mode in title slot01 ${AD_CHECK_SLOT00:+slot00}; do
  mkdir -p "$out/$mode/frames"
  cp -R port/hdd0 "$out/$mode/hdd0"
  port/install-content.sh --into "$out/$mode/hdd0" > "$out/$mode/install.log"
  export PS3_HDD0_ROOT="$out/$mode/hdd0" PS3_HDD1_ROOT="$out/$mode/hdd1"
  export PS3RECOMP_METAL_FRAME_DUMP="$out/$mode/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=240
  unset PAD_SCRIPT D2_WARP_STAGE PS3_SAVEDATA_DIR
  if [[ $mode != title ]]; then
    export PAD_SCRIPT='10:0x4000,14:0x4000'
    export D2_WARP_STAGE=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR="NPUB31321_NORMAL_${mode#slot}"
  fi
  status=0
  perl -e 'alarm shift; exec @ARGV' 40 ./port/build-ad/DisgaeaD2Recomp work/v140/EBOOT.elf > "$out/$mode/run.log" 2>&1 || status=$?
  [[ $status == 142 ]] || { echo "FAIL $mode: exit $status ($out)"; exit 1; }
  accepted=$(grep -c 'NPDRM.*accepted.*Data/flag/flag' "$out/$mode/run.log")
  [[ $accepted == 45 ]] || { echo "FAIL $mode: only $accepted DLC flags accepted ($out)"; exit 1; }
  read_flags=$(grep -c 'NPDRM.*read.*Data/flag/flag' "$out/$mode/run.log")
  [[ $read_flags == 45 ]] || { echo "FAIL $mode: only $read_flags DLC flags read ($out)"; exit 1; }
  if grep -qE 'OOB access|FAULT|Bus error' "$out/$mode/run.log"; then
    echo "FAIL $mode: guest memory fault ($out)"; exit 1
  fi
  grep -q 'START_7.dat.*fd' "$out/$mode/run.log"
  grep -q 'presented guest frame 600' "$out/$mode/run.log"
  if [[ $mode != title ]]; then
    grep -q "LOAD complete for 'NPUB31321_NORMAL_${mode#slot}'" "$out/$mode/run.log"
    grep -q 'D2-warp.*confirm stage=101' "$out/$mode/run.log"
    grep -q 'D2-warp.*stage=5011 map_id=101' "$out/$mode/run.log"
  fi
  if [[ ${AD_HEADLESS:-0} != 1 ]]; then
    grep -q 'Metal backend init OK' "$out/$mode/run.log"
    compgen -G "$out/$mode/frames/f*.ppm" > /dev/null
  fi
  grep -nE 'LOAD complete|D2-warp.*confirm|D2-warp.*stage=5011|NPDRM.*read|d2-boot.*frames=' "$out/$mode/run.log" | tail -8 || true
  echo "PASS $mode: 45 DLC flags; frames in $out/$mode/frames"
done
echo "Logs: $out. Inspect title and battle frames for visual correctness."
