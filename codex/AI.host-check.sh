#!/bin/bash
# Real-Metal slot-01 battle/Cross and AG2/AH regressions. Only build-ai.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p port/runs
out=$(mktemp -d "$PWD/port/runs/AI-host.XXXXXX")
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/AI-host.XXXXXX)
root="$PWD"
printf 'Evidence: %s\nPrivate saves/cache: %s\n' "$out" "$scratch"
printf '%s\n' "$scratch" > "$out/scratch.txt"
seconds=${AI_SECONDS:-120}
[[ $seconds =~ ^[0-9]+$ ]] && (( seconds >= 120 ))
if [[ ${AI_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-ai -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp -DD2_GAME_VERSION=140 \
    -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-ai --target DisgaeaD2Recomp -j 3 > "$out/build.log" 2>&1
fi
grep -q 'D2_GAME_VERSION:STRING=140' port/build-ai/CMakeCache.txt
clang -std=c17 -fobjc-arc -I ps3recomp/include -I ps3recomp/libs/video \
  codex/AG.metal-test.m ps3recomp/libs/video/rsx_texture_layout.c -Wl,-dead_strip \
  -framework Metal -framework Cocoa -framework QuartzCore -framework CoreText \
  -o port/build-ai/AI-metal-test > "$out/metal-build.log" 2>&1
set +e
./port/build-ai/AI-metal-test "$out/scale-f%u.ppm" > "$out/metal-test.log" 2>&1
metal_rc=$?
set -e
if (( metal_rc != 0 )); then
  if [[ ${AI_HEADLESS:-0} == 1 && $metal_rc == 77 ]]; then
    echo 'SKIP: GPU pixels unavailable in sandbox; checking guest execution only'
  else
    tail -8 "$out/metal-test.log"; echo "FAIL: GPU harness exit $metal_rc"; exit 1
  fi
fi
clang -std=gnu17 -fobjc-arc -I ps3recomp/include \
  ps3recomp/libs/video/tests/test_metal_overlay.m ps3recomp/libs/video/rsx_metal_overlay.m \
  ps3recomp/libs/system/sys_overlay.c -framework Metal -framework AppKit -framework QuartzCore \
  -framework CoreText -o port/build-ai/AI-overlay-test > "$out/overlay-build.log" 2>&1
mkdir -p "$out/port/runs"
set +e
(cd "$out"; "$root/port/build-ai/AI-overlay-test" --metal) > "$out/overlay-test.log" 2>&1
overlay_rc=$?
set -e
if (( overlay_rc != 0 )) && ! [[ ${AI_HEADLESS:-0} == 1 && $overlay_rc == 77 ]]; then
  tail -8 "$out/overlay-test.log"; echo "FAIL: overlay harness exit $overlay_rc"; exit 1
fi
cp -R port/hdd0 "$scratch/hdd0"
if [[ -d port/hdd1 ]]; then cp -R port/hdd1 "$scratch/hdd1"; fi
test -f "$scratch/hdd0/home/00000001/savedata/NPUB31321_NORMAL_01/SAVEDATA.DAT"
mkdir -p "$scratch/hdd1" "$out/frames"
pad="$scratch/pad.txt"
: > "$pad"
unset PAD_SCRIPT PAD_STICK PAD_SWEEP D2_CHEATS_OPEN_PAGE D2_CHEATS_TEST_HL D2_CHEATS_TEST_SAVE
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY
if [[ ${AI_HEADLESS:-0} == 1 ]]; then
  export PS3RECOMP_METAL_HEADLESS=1 PS3RECOMP_RSX_FIFO_ONLY=1
fi
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
D2_SETTINGS_PATH="$scratch/settings.json" D2_SETTINGS_OVERRIDE='{"scale":1,"frame_cap":60}' \
PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_01 D2_WARP_STAGE=1 D2_MOVIE_SKIP=1 \
PAD_FILE="$pad" PAD_TRACE=1 PAD_NO_KEYBOARD=1 \
PS3RECOMP_METAL_FRAME_DUMP="$out/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=600 \
  perl -e 'alarm shift; exec @ARGV' "$seconds" ./port/build-ai/DisgaeaD2Recomp work/v140/EBOOT.elf \
  > "$out/run.log" 2>&1 &
runner=$!
trap 'kill "$runner" 2>/dev/null || true' EXIT
python3 - "$out" "$pad" "$seconds" <<'PYDRIVER' > "$out/driver.log" 2>&1
import re
import sys
import time
from pathlib import Path
out, pad = map(Path, sys.argv[1:3])
seconds = int(sys.argv[3])
start = time.monotonic()
last_press = 0
warp_at = None
battle_cross = 0
loaded = False
frames = []
with (out / 'run.log').open(errors='replace') as log:
    while time.monotonic() - start < seconds - 1:
        time.sleep(.1)
        now = time.monotonic()
        chunk = log.read()
        load_marker = "LOAD complete for 'NPUB31321_NORMAL_01'"
        after_load = chunk
        if not loaded and load_marker in chunk:
            loaded = True
            after_load = chunk.split(load_marker, 1)[1]
        if any(x in chunk for x in ('OOB access', 'HOST CORRUPTION', 'FAULT', 'Bus error')):
            raise SystemExit('FAIL: runtime fault; inspect run.log')
        # The pre-CRT weak-symbol read at NULL+4 is already present at boot.
        # Every null read after save load, including 002EF390/1004, is fatal.
        if loaded and '[null-read]' in after_load:
            raise SystemExit('FAIL: null read after save load')
        if warp_at is None and 'confirm stage=101' in chunk:
            warp_at = now
            print(f'[AI-driver] battle confirmed at {now-start:.1f}s', flush=True)
        for value in re.findall(r'presented guest frame (\d+)', chunk):
            frames.append((now-start, int(value)))
        interval = .5 if loaded else 4
        if now-start < 10 or now-last_press < interval or pad.read_text().strip():
            continue
        if warp_at is not None and now-warp_at < 3:
            continue
        pad.write_text('0x4000 4\n')
        last_press = now
        if warp_at is not None:
            battle_cross += 1
        print(f'[AI-pad] {now-start:.1f}s Cross battle={battle_cross}', flush=True)
    assert loaded and warp_at is not None, 'slot 01/battle not reached'
    assert battle_cross >= 80, f'only {battle_cross} battle Cross presses'
    late = [(t, n) for t, n in frames if t > seconds-12]
    assert len(late) >= 2 and late[-1][1] > late[0][1], 'flips stopped before timeout'
    print(f'[AI-driver] PASS: {battle_cross} battle Cross presses; late flips {late[0][1]}..{late[-1][1]}', flush=True)
PYDRIVER
set +e
wait "$runner"
run_rc=$?
set -e
trap - EXIT
(( run_rc == 142 )) || { echo "FAIL: runner exit $run_rc, expected alarm 142"; exit 1; }
if [[ ${AI_HEADLESS:-0} != 1 ]]; then grep -q 'Metal backend init OK' "$out/run.log"; fi
grep -q "LOAD complete for 'NPUB31321_NORMAL_01'" "$out/run.log"
grep -q 'D2-warp.*confirm stage=101' "$out/run.log"
grep -q 'stage=5011 map_id=101' "$out/run.log"
# Retain a battle-only log so the assertion excludes only the known boot read.
sed -n '/LOAD complete/,$p' "$out/run.log" > "$out/battle.log"
if grep -qE 'OOB access|HOST CORRUPTION|FAULT|Bus error|command buffer failed|pipeline state failed' "$out/run.log" \
   || grep -q '\[null-read\]' "$out/battle.log"; then
  echo "FAIL: runtime/render error ($out/run.log)"; exit 1
fi
grep -nE 'PASS|AG2.*RESC' "$out/metal-test.log" "$out/overlay-test.log" "$out/driver.log"
grep -nE 'LOAD complete|draining hub messages|confirm stage=101|D2-warp.*frame=' "$out/run.log" | tail -10
if [[ ${AI_HEADLESS:-0} == 1 ]]; then
  echo "PASS: 120s guest battle/Cross execution; GPU verification SKIPPED ($out)"
else
  echo "PASS: 120s real-Metal battle/Cross, continued flips, AG2/AH GPU checks ($out)"
fi
