#!/bin/bash
# Run on real Metal. All captures and a private copy of the saves are retained.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
seconds=${V_SECONDS:-180}
mkdir -p port/runs /Volumes/Data/ai-tmp/codex
out=$(mktemp -d "$root/port/runs/V-host.XXXXXX")
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-V-host.XXXXXX)
mkdir -p "$out/frames" "$out/draws" "$scratch/hdd0" "$scratch/hdd1"
cp -R port/hdd0/. "$scratch/hdd0/"
printf 'Captures: %s\nSave copy/cache: %s\n' "$out" "$scratch"
(cd port
 cmake -B build-v -G Ninja -DCMAKE_BUILD_TYPE=Release \
   -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
   -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include
 cmake --build build-v --target DisgaeaD2Recomp -j 3
) > "$out/build.log" 2>&1
unset PS3RECOMP_RSX_FIFO_ONLY PAD_SCRIPT PAD_FILE
if grep -q 'd2_register_debug_warp' port/stubs.cpp && test -f port/src/d2_debug_warp.cpp; then
  export D2_WARP_STAGE="${V_STAGE:-1}"
  echo 'Choose Continue and load the save. The debug warp enters the selected stage automatically.'
else
  unset D2_WARP_STAGE
  echo 'Choose Continue, load the save, and walk to the Dimension Guide to enter the first battle.'
fi
echo 'Skip the stage dialogue with Triangle twice (the second confirms skip).'
echo 'Deploy Laharl from the base panel, select Attack, and queue an attack on an adjacent enemy.'
echo 'Inspect the top-left ATTACK ENTRY portrait: the map should show through its rectangular corners.'
echo 'Other HUD panels, character sprites, and the Bonus gauge should still render correctly.'
if [[ -n ${V_PAD_SCRIPT:-} ]]; then export PAD_SCRIPT="$V_PAD_SCRIPT"; fi
set +e
PS3_VFS_ROOT="$root/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
PS3RECOMP_METAL_HEADLESS="${V_HEADLESS:-0}" PS3RECOMP_RSX_ENGINE=dispatch \
D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
D2_DRAW_TRACE="$out/draws" D2_DRAW_TRACE_MAX_FRAME=0 D2_DRAW_TRACE_TEXTURE_LIMIT=1000 \
D2_DRAW_TRACE_NEW_PIPELINES=1 PAD_TRACE=1 MTL_DEBUG_LAYER=1 \
PS3RECOMP_METAL_FRAME_DUMP="$out/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=120 \
perl -e 'alarm shift; exec @ARGV' "$seconds" \
 ./port/build-v/DisgaeaD2Recomp work/EBOOT.elf > "$out/run.log" 2>&1
status=$?
set -e
printf 'Exit=%s (142 is the expected timer)\n' "$status"
grep -nE 'Metal backend|no Metal device|F-trace|D2-warp|LOAD complete|Data/MAP|V-surface|F-texture|command buffer failed|validation|captured frame|FAILED|FAULT|SIGNAL' \
 "$out/run.log" > "$out/summary.txt" || true
grep -nE '\[(F-draw|V-alpha|V-stencil|V-pipeline)\]' "$out/run.log" > "$out/draw-state.txt" || true
tail -35 "$out/summary.txt"
printf 'Review numbered PPM frames and %s/draw-state.txt; captures retained.\n' "$out"
if [[ "$status" != 0 && "$status" != 142 ]]; then exit "$status"; fi
if ! grep -q '\[F-trace\] Metal' "$out/run.log"; then
 echo 'Metal was unavailable: this capture cannot verify the visual fix.' >&2
 exit 1
fi
if ! grep -q '\[V-stencil\] enabled=1 ref=255.*masks=FF/FF.*ops=1E01/1E01/1E01' "$out/run.log"; then
 echo 'Portrait mask pass was not captured; queue an attack and rerun with a longer V_SECONDS.' >&2
 exit 1
fi
echo 'Portrait stencil mask captured with FF write mask. Confirm the transparent corners in the frames/window.'
