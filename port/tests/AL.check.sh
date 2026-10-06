#!/bin/bash
# AL lifecycle/scripts/content checks; build argument must be a configured v140 build.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
build=${1:-port/build-al}
scratch=$(mktemp -d "${D2_TEST_TMPDIR:-${TMPDIR:-/tmp}}/AL-check.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
python3 port/tests/AL.scripts-test.py
clang -std=gnu17 -fsanitize=address,undefined -g -I ps3recomp -I ps3recomp/include \
    port/tests/AL.lifecycle-test.c ps3recomp/runtime/platform/guest_poll.c -o "$scratch/lifecycle"
"$scratch/lifecycle"
clang -std=gnu17 -O1 -fsanitize=address,undefined -ffunction-sections -fdata-sections -Wl,-dead_strip \
    -I ps3recomp -I ps3recomp/include port/tests/AL.save-stop-test.c -o "$scratch/save-stop"
"$scratch/save-stop" "$scratch"
clang -std=gnu17 -I ps3recomp/include -c ps3recomp/runtime/platform/win32_compat.c -o "$scratch/compat.o"
clang++ -std=c++20 -DD2_GAME_VERSION=140 -O1 -ffunction-sections -fdata-sections -Wl,-dead_strip \
    -I port/src/recomp-140 -I ps3recomp/include -I ps3recomp/runtime/platform \
    -I ps3recomp/runtime/memory -I ps3recomp/libs/system -I "$build" \
    port/tests/AL.frame-clock-test.cpp "$scratch/compat.o" -o "$scratch/frame-clock"
"$scratch/frame-clock"
clang -std=gnu17 -O1 -fsanitize=address,undefined -ffunction-sections -fdata-sections -Wl,-dead_strip \
    -I ps3recomp -I ps3recomp/include port/tests/AL.dialog-stop-test.c ps3recomp/libs/system/sys_overlay.c \
    -o "$scratch/dialog-stop"
"$scratch/dialog-stop"
python3 port/tests/AL.fixture-setup.py "$scratch"
clang -O1 -fobjc-arc -ffunction-sections -fdata-sections -Wl,-dead_strip -I "$build" \
    port/tests/AL.launcher-test.m -framework AppKit -o "$scratch/launcher"
AL_TEST_ROOT="$scratch" "$scratch/launcher"
clang -std=gnu17 -O1 -fobjc-arc -ffunction-sections -fdata-sections -Wl,-dead_strip \
    -I ps3recomp -I ps3recomp/include -I ps3recomp/libs/video -I ps3recomp/libs/system -I /opt/homebrew/include \
    port/tests/AL.metal-test.m ps3recomp/libs/video/rsx_texture_layout.c \
    -framework Metal -framework Cocoa -framework QuartzCore -framework CoreText -o "$scratch/metal"
set +e
"$scratch/metal"
status=$?
set -e
if [ "$status" != 0 ] && [ "$status" != 77 ]; then exit "$status"; fi
