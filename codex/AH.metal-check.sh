#!/bin/bash
# Real-Metal regressions; only build-ah. No shared bundle/build writes.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p port/runs port/build-ah
root="$PWD"
out=$(mktemp -d "$PWD/port/runs/AH-metal.XXXXXX")
printf 'GPU evidence: %s\n' "$out"
clang -std=c17 -fobjc-arc -I ps3recomp/include -I ps3recomp/libs/video \
  codex/AG.metal-test.m ps3recomp/libs/video/rsx_texture_layout.c -Wl,-dead_strip \
  -framework Metal -framework Cocoa -framework QuartzCore -framework CoreText \
  -o port/build-ah/AG-metal-test > "$out/metal-build.log" 2>&1
./port/build-ah/AG-metal-test "$out/scale-f%u.ppm" > "$out/metal-test.log" 2>&1
clang -std=gnu17 -fobjc-arc -I ps3recomp/include \
  ps3recomp/libs/video/tests/test_metal_overlay.m ps3recomp/libs/video/rsx_metal_overlay.m \
  ps3recomp/libs/system/sys_overlay.c -framework Metal -framework AppKit -framework QuartzCore \
  -framework CoreText -o port/build-ah/AH-overlay-test > "$out/overlay-build.log" 2>&1
mkdir -p "$out/port/runs"
(cd "$out"; "$root/port/build-ah/AH-overlay-test" --metal) > "$out/overlay-test.log" 2>&1
grep -n PASS "$out/metal-test.log" "$out/overlay-test.log"
echo "PASS: RESC/presenter, 1/1.5/2/3x partial transfers, independent clears, opaque panel/page changes ($out)"
