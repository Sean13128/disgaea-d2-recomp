#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p port/build-af port/runs
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/AF-test.XXXXXX)
trap 'rm -rf "$scratch"' EXIT
flags=(-O1 -g -I ps3recomp/include -I/opt/homebrew/include)
if [[ ${AF_SANITIZE:-1} == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang -std=gnu17 "${flags[@]}" codex/AF.overlay-test.c ps3recomp/libs/system/sys_overlay.c -pthread -o port/build-af/AF-overlay-test
./port/build-af/AF-overlay-test > port/runs/AF.overlay-test.log 2>&1
clang -std=gnu17 "${flags[@]}" -c ps3recomp/libs/system/sys_overlay.c -o port/build-af/AF-overlay-test.o
version=$(sed -n 's/^D2_GAME_VERSION:STRING=//p' port/build-af/CMakeCache.txt)
lift=port/src/recomp
[[ $version != 140 ]] || lift=port/src/recomp-140
clang++ -std=c++20 "${flags[@]}" -DD2_CHEATS_VERSION="$version" -I"$lift" -Iport/build-af codex/AF.editor-test.cpp port/build-af/AF-overlay-test.o -pthread -o port/build-af/AF-editor-test
./port/build-af/AF-editor-test "$scratch" > port/runs/AF.editor-test.log 2>&1
clang -std=gnu17 "${flags[@]}" ps3recomp/libs/system/tests/test_sys_overlay.c ps3recomp/libs/system/sys_overlay.c \
    ps3recomp/libs/system/cellMsgDialog.c ps3recomp/libs/system/cellSysutil.c -Wl,-dead_strip -pthread -o port/build-af/AF-system-regression
./port/build-af/AF-system-regression > port/runs/AF.system-test.log 2>&1
clang -std=gnu17 "${flags[@]}" -fobjc-arc codex/AF.hotkey-test.m ps3recomp/libs/input/cellPad.c ps3recomp/libs/input/pad_macos.m \
    -framework AppKit -framework Foundation -L/opt/homebrew/lib -lSDL2 -o port/build-af/AF-hotkey-test
./port/build-af/AF-hotkey-test > port/runs/AF.hotkey-test.log 2>&1
save=${AF_RASTER_SAVE:-port/hdd0/home/00000001/savedata/NPUB31321_NORMAL_01/SAVEDATA.DAT}
if [[ -f "$save" ]]; then
    clang "${flags[@]}" -fobjc-arc -c ps3recomp/libs/video/rsx_metal_overlay.m -o port/build-af/AF-raster.o
    clang++ -std=c++20 "${flags[@]}" -DD2_CHEATS_VERSION="$version" -I"$lift" -Iport/build-af \
        codex/AF.raster-test.cpp port/build-af/AF-raster.o port/build-af/AF-overlay-test.o \
        -framework Metal -framework QuartzCore -framework CoreText -framework CoreGraphics -framework Foundation \
        -Wl,-dead_strip -pthread -o port/build-af/AF-raster-test
    ./port/build-af/AF-raster-test "$save" port/runs/AF-raster > port/runs/AF.raster-test.log 2>&1
    for frame in port/runs/AF-raster/*.ppm; do sips -s format png "$frame" --out "${frame%.ppm}.png"; done > port/runs/AF.raster-convert.log 2>&1
fi
rg PASS port/runs/AF.{overlay,editor,system,hotkey}-test.log
[[ ! -f port/runs/AF.raster-test.log ]] || rg PASS port/runs/AF.raster-test.log
