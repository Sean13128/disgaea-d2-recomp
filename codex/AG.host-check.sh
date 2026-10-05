#!/bin/bash
# Real-host validation: only build-ag, copied saves, isolated test settings.
set -euo pipefail
cd "$(dirname "$0")/.."
out=$(mktemp -d "$PWD/port/runs/AG-host.XXXXXX")
printf 'Evidence: %s\n' "$out"
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-AG-host.XXXXXX)
printf '%s\n' "$scratch" > "$out/scratch.txt"
mkdir -p "$scratch/hdd0" "$scratch/hdd1"
cp -R port/hdd0/. "$scratch/hdd0/"
if [[ ${AG_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-ag -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
    -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-ag --target DisgaeaD2Recomp -j 4 > "$out/build.log" 2>&1
fi
D2_SETTINGS_PATH="$scratch/settings-test.json" D2_SETTINGS_TEST_UI=1 \
  ./port/build-ag/DisgaeaD2Recomp --settings-test > "$out/unit.log" 2>&1
clang -std=gnu17 -O2 -I ps3recomp/include -I ps3recomp/libs/video \
  codex/AG2.engine-test.c ps3recomp/libs/video/rsx_draw_engine.c ps3recomp/libs/video/rsx_dispatch.c \
  ps3recomp/libs/video/rsx_vertex_compact.c ps3recomp/libs/video/rsx_texture_layout.c \
  ps3recomp/libs/video/rsx_vp_decompiler.c ps3recomp/libs/video/rsx_fp_decompiler.c \
  -o port/build-ag/AG2-engine-test > "$out/engine-test-build.log" 2>&1
./port/build-ag/AG2-engine-test > "$out/engine-test.log" 2>&1
clang -std=c17 -O2 -ffunction-sections -fdata-sections \
  -I ps3recomp/include -I ps3recomp/libs/video -I ps3recomp/runtime/platform \
  codex/AG2.fifo-test.c ps3recomp/libs/video/cellResc.c \
  ps3recomp/runtime/platform/win32_compat.c ps3recomp/runtime/platform/guest_poll.c \
  -Wl,-dead_strip -pthread -o port/build-ag/AG2-fifo-test > "$out/fifo-test-build.log" 2>&1
./port/build-ag/AG2-fifo-test > "$out/fifo-test.log" 2>&1
clang -std=c17 -fobjc-arc -I ps3recomp/include -I ps3recomp/libs/video \
  codex/AG.metal-test.m ps3recomp/libs/video/rsx_texture_layout.c -Wl,-dead_strip \
  -framework Metal -framework Cocoa -framework QuartzCore -framework CoreText -o port/build-ag/AG-metal-test \
  > "$out/metal-test-build.log" 2>&1
if ! ./port/build-ag/AG-metal-test "$out/metal-f%u.ppm" > "$out/metal-test.log" 2>&1; then
  echo "FAIL: GPU harness failed or Metal is unavailable; inspect $out/metal-test.log"; exit 1
fi
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY PAD_FILE PAD_STICK PAD_SWEEP
unset D2_WARP_STAGE D2_DRAW_TRACE PS3RECOMP_METAL_OVERLAY_CAPTURE D2_SETTINGS_LIVE_OVERRIDE
pad='10:0x4000,14:0x4000,18:0x4000,24:0x0040,24.25:0x0040,24.5:0x0040,26:0x0080,26.25:0x0080,26.5:0x0080,28:0x0080,28.25:0x0080,28.5:0x0080,30:0x0040,30.25:0x0040,30.5:0x0040,30.75:0x0040,31:0x0040'
seconds=${AG_SECONDS:-70}
[[ "$seconds" =~ ^[0-9]+$ ]] && (( seconds >= 50 )) || { echo 'AG_SECONDS must be >=50'; exit 1; }
for scale in 1 2; do
  mkdir -p "$out/${scale}x"
  status=0
  PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
  PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
  D2_SETTINGS_PATH="$scratch/${scale}x.json" \
  D2_SETTINGS_OVERRIDE="{\"scale\":$scale,\"show_fps\":true,\"volume\":0.5,\"frame_cap\":60}" \
  D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
  GCM_FLIP_TRACE=1 GCM_RECYCLE_TRACE=1 GCM_FLIPCOUNT=1 D2_WARP_TRACE=1 PS3_HOST_CPU=1 \
  PAD_SCRIPT="${AG_PAD_SCRIPT:-$pad}" PS3RECOMP_METAL_FRAME_DUMP="$out/${scale}x/f%u.ppm" \
  PS3RECOMP_METAL_FRAME_DUMP_EVERY=1200 \
    perl -e 'alarm shift; exec @ARGV' "$seconds" ./port/build-ag/DisgaeaD2Recomp work/EBOOT.elf \
    > "$out/${scale}x/run.log" 2>&1 || status=$?
  [[ $status == 142 ]] || { echo "FAIL: ${scale}x exited early ($status): $out"; exit 1; }
  grep -q '\[rsx\] Metal backend init OK' "$out/${scale}x/run.log" || { echo 'FAIL: no real Metal'; exit 1; }
  grep -nE 'D2 settings|internal resolution|captured frame|map30001|LOAD complete|gcm-rate|HOSTCPU' \
    "$out/${scale}x/run.log" > "$out/${scale}x/metrics.txt" || true
  if grep -qE 'transfer pipeline failed:|scale copy pipeline:|resolution allocation failed|command buffer failed|pipeline state failed|HOST CORRUPTION' \
      "$out/${scale}x/run.log"; then echo "FAIL: render/runtime error in $out/${scale}x/run.log"; exit 1; fi
  python3 codex/Y.analyze.py "$out/${scale}x/run.log" | tee "$out/${scale}x/fps.txt"
  python3 - "$out/${scale}x/fps.txt" <<'PYFPS'
import re, sys
fps = float(re.search(r'Castle Hallway: ([\d.]+)', open(sys.argv[1]).read()).group(1))
assert fps >= 58.5, f'hallway below 60 fps target: {fps}'
PYFPS
done
python3 - "$out" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
# The GPU harness exercises the actual presenter/compositor at all supported scales.
for frame, size in enumerate(((1280,720), (1920,1080), (2560,1440), (3840,2160)), 1):
    with (root / f'metal-f{frame}.ppm').open('rb') as f:
        assert f.readline().strip() == b'P6'
        assert tuple(map(int, f.readline().split())) == size
        assert f.readline().strip() == b'255'
        pixels = f.read()
        assert len(pixels) == size[0]*size[1]*3
        reds = [pixels[3*x] for x in range(64)]
        assert all(abs(reds[x] - reds[x+1]) >= 253 for x in range(63)), 'present/capture lost physical-pixel stripes'
print('GPU presentation captures: 1x/1.5x/2x/3x dimensions PASS')
for scale in (1, 2):
    images = sorted((root / f'{scale}x').glob('f*.ppm'), key=lambda p: int(p.stem[1:]))
    assert images, f'no {scale}x captures'
    for path in images:
        with path.open('rb') as f:
            assert f.readline().strip() == b'P6'
            w, h = map(int, f.readline().split())
            assert (w, h) == (1280*scale, 720*scale), (path, w, h)
            assert f.readline().strip() == b'255'
            pixels = f.read()
            assert len(pixels) == w*h*3
        if path == images[-1] and scale == 2:
            different = total = 0
            for y in range(0, h, 8):
                for x in range(0, w, 8):
                    a = (y*w+x)*3
                    color = pixels[a:a+3]
                    different += any(pixels[b:b+3] != color for b in (a+3, a+w*3, a+w*3+3))
                    total += 1
            fraction = different / total
            print(f'2x subpixel detail: {fraction:.1%} of sampled 2x2 blocks vary')
            assert fraction > .001, '2x appears to duplicate native pixels; inspect captures'
    print(f'{scale}x: {len(images)} frames at {1280*scale}x{720*scale}; last: {images[-1]}')
# Match frame numbers in the settled hallway and crop the same native rectangle.
import re, struct, zlib
settled = []
for scale in (1, 2):
    log = (root / f'{scale}x/run.log').read_text()
    hallway = log.index('map30001')
    settled.append({int(m.group(1)) for m in re.finditer(r'captured frame (\d+)', log[hallway:])})
common = settled[0] & settled[1]
assert common, 'no matching settled hallway captures'
frame = max(common)
def png(path, width, height, pixels):
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    rows = b''.join(b'\0' + pixels[y*width*3:(y+1)*width*3] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                    + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
for scale in (1, 2):
    with (root / f'{scale}x/f{frame}.ppm').open('rb') as f:
        f.readline(); w, h = map(int, f.readline().split()); f.readline(); pixels = f.read()
    x, y, cw, ch = 448*scale, 232*scale, 384*scale, 256*scale
    crop = b''.join(pixels[((y+row)*w+x)*3:((y+row)*w+x+cw)*3] for row in range(ch))
    # Enlarge 1x with nearest sampling so the pair has the same comparison size.
    if scale == 1:
        rows = [b''.join(crop[(row*cw+col)*3:(row*cw+col+1)*3]*2 for col in range(cw)) for row in range(ch)]
        crop = b''.join(row*2 for row in rows); cw *= 2; ch *= 2
    png(root / f'hallway-f{frame}-{scale}x-crop.png', cw, ch, crop)
print(f'Paired hallway crops saved from frame {frame}; 1x enlarged with nearest sampling')
print('Inspect paired Castle Hallway frames for geometry edges, HUD, sprites, movies and RTT effects. Pixel detail is evidence of scaling, not a visual-quality verdict.')
PY
# Explicitly test live replacement plus a presentation-only 30 FPS cap.
status=0
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
D2_SETTINGS_PATH="$scratch/live.json" D2_SETTINGS_OVERRIDE='{"scale":1,"frame_cap":60}' \
D2_SETTINGS_LIVE_OVERRIDE='{"scale":2,"frame_cap":30,"filter":"nearest","mute":true}' \
D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
GCM_FLIP_TRACE=1 GCM_RECYCLE_TRACE=1 D2_WARP_TRACE=1 PAD_SCRIPT="${AG_PAD_SCRIPT:-$pad}" \
  perl -e 'alarm shift; exec @ARGV' 55 ./port/build-ag/DisgaeaD2Recomp work/EBOOT.elf \
  > "$out/live.log" 2>&1 || status=$?
[[ $status == 142 ]] || { echo 'FAIL: live test exited early'; exit 1; }
grep -q 'internal resolution 2.0x' "$out/live.log" || { echo 'FAIL: live scale did not apply'; exit 1; }
python3 codex/Y.analyze.py "$out/live.log" | tee "$out/live-fps.txt"
if grep -qE 'transfer pipeline failed:|scale copy pipeline:|resolution allocation failed|command buffer failed|HOST CORRUPTION' "$out/live.log"; then
  echo 'FAIL: live scale error'; exit 1
fi
printf 'PASS: automated host checks. Evidence: %s\n' "$out"
printf 'Manual: click every menu; Cmd+M, Cmd+Ctrl+F, borderless, topmost, focus mute, volume, filter/aspect, FPS, reset; move/resize then relaunch to check persistence. Import into copied HDD0 and export a slot.\n'
printf 'Bundle: cmake --build port/build-ag --target DisgaeaD2Dist; launch port/dist/Disgaea D2.app and check the same menus. Personal settings: ~/Library/Application Support/DisgaeaD2Recomp/settings.json.\n'
