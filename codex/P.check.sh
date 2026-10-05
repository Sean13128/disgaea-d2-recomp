#!/bin/bash
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p port/build-p port/runs
flags=(-std=gnu17 -O1 -g -I ps3recomp/include -I/opt/homebrew/include)
if [ "${P_SANITIZE:-1}" = 1 ]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang "${flags[@]}" ps3recomp/libs/system/tests/test_sys_overlay.c \
    ps3recomp/libs/system/sys_overlay.c ps3recomp/libs/system/cellMsgDialog.c \
    ps3recomp/libs/system/cellSysutil.c -Wl,-dead_strip -pthread \
    -o port/build-p/P-model-test
./port/build-p/P-model-test
clang "${flags[@]}" -fobjc-arc ps3recomp/libs/input/tests/test_pad_overlay.m \
    ps3recomp/libs/input/cellPad.c ps3recomp/libs/input/pad_macos.m \
    ps3recomp/libs/system/sys_overlay.c -framework AppKit -framework Foundation \
    -L/opt/homebrew/lib -lSDL2 -o port/build-p/P-pad-test
./port/build-p/P-pad-test "${1:-}"
clang "${flags[@]}" -fobjc-arc ps3recomp/libs/video/tests/test_metal_overlay.m \
    ps3recomp/libs/video/rsx_metal_overlay.m ps3recomp/libs/system/sys_overlay.c \
    -framework Metal -framework QuartzCore -framework CoreText -framework CoreGraphics -framework Foundation \
    -o port/build-p/P-metal-test
./port/build-p/P-metal-test "${2:-}"
clang "${flags[@]}" ps3recomp/libs/system/tests/test_savedata_overlay.c \
    ps3recomp/libs/system/sys_overlay.c -Wl,-dead_strip -pthread -o port/build-p/P-save-ui-test
P_TEST_ROOT="$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-P-save-ui.XXXXXX)" ./port/build-p/P-save-ui-test
clang "${flags[@]}" ps3recomp/libs/system/tests/test_dialog_callbacks.c \
    ps3recomp/libs/system/cellSysutil.c -Wl,-dead_strip -pthread -o port/build-p/P-dialog-regression
./port/build-p/P-dialog-regression
