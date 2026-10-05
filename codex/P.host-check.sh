#!/bin/bash
# Real Metal + keyboard/SDL regression. Only build-p; grep for logs, no rm.
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
root="$PWD"
mode="${1:-auto}"
case "$mode" in auto|interactive|tests) ;; *) echo 'Usage: bash codex/P.host-check.sh [auto|interactive|tests]'; exit 2 ;; esac
mkdir -p port/runs
run="$(mktemp -d "$root/port/runs/P-host.XXXXXX")"
scratch="$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-P-host.XXXXXX)"
echo "Logs and frames: $run; isolated empty saves/cache: $scratch"
(
    cd port
    cmake -B build-p -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
        -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
        -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include
    cmake --build build-p --target DisgaeaD2Recomp -j 4
) > "$run/build.log" 2>&1
# Disconnect physical pads for deterministic keyboard/virtual-controller tests.
P_SANITIZE=1 bash codex/P.check.sh --native --metal > "$run/tests.log" 2>&1
grep -n 'PASS\|SKIP' "$run/tests.log"
if [ "$mode" = tests ]; then exit 0; fi
unset PS3RECOMP_METAL_HEADLESS PS3_SAVEDATA_UI PS3_SAVEDATA_DIR PS3_SAVEDATA_CONFIRM PS3_SAVEDATA_DELETE_DIR
unset MSGDIALOG_ANSWER PAD_AUTOPRESS PAD_ALWAYS_CHANGE
export PS3_VFS_ROOT="$root/Disgaea D2 A Brighter Darkness - [BLUS31313]"
# A fresh root proves Continue is the empty-save case without touching real saves.
export PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1"
# Keep the title-menu check independent of concurrent movie decoder work.
export D2_MOVIE_SKIP=1
export PAD_TRACE=1
export PS3RECOMP_METAL_FRAME_DUMP="$run/frame-%u.ppm"
export PS3RECOMP_METAL_FRAME_DUMP_EVERY=60
seconds="${P_SECONDS:-70}"
if [ "$mode" = auto ]; then
    export PAD_SCRIPT="${P_PAD_SCRIPT:-10:0x4000,15:0x0008,30:0x0040,33:0x4000}"
    export PAD_FILE="$run/pad.txt"
    : > "$PAD_FILE"
    echo 'Auto: title → Down/Continue → hold empty-save overlay for capture → Cross → Up/New Game.'
else
    unset PAD_SCRIPT PAD_FILE
    echo 'Focus the Metal window. Choose Continue with the pad or arrows/Z.'
    echo 'Confirm the in-window no-save overlay; dismiss with Cross/Z; choose New Game.'
    echo 'Check that focus stays in the same window, and the dismissal does not also select the title menu.'
fi
set +e
perl -e 'alarm shift; exec @ARGV' "$seconds" ./port/build-p/DisgaeaD2Recomp work/EBOOT.elf > "$run/game.log" 2>&1 &
pid=$!
set -e
trap 'kill "$pid" 2>/dev/null || true' EXIT
wait_for() {
    local pattern="$1" deadline=$((SECONDS + "$2"))
    while ! grep -qiE "$pattern" "$run/game.log"; do
        if ! kill -0 "$pid" 2>/dev/null || [ "$SECONDS" -ge "$deadline" ]; then
            echo "Missing milestone: $pattern"
            grep -n -iE 'sys overlay|cellMsgDialog|cellSaveData|Metal|PAD_SCRIPT|FAULT|SIGNAL' "$run/game.log" | tail -35 || true
            return 1
        fi
        sleep 0.2
    done
}
if [ "$mode" = auto ]; then
    wait_for 'cellSaveData.*funcList terminal result=2.*dirNum=0' 30
    wait_for "sys overlay.*open.*(no sav|no saved|not.*save)" 60
    wait_for 'sys overlay/metal.*captured.*overlay=1' 6
    sleep 2
    echo '0x4000 8' > "$PAD_FILE"
    wait_for 'sys overlay.*closed.*result=1' 6
    sleep 1
    echo '0x0010 4' > "$PAD_FILE"
    sleep 1
    echo '0x4000 8' > "$PAD_FILE"
fi
set +e
wait "$pid"
result=$?
set -e
trap - EXIT
if [ "$result" != 0 ] && [ "$result" != 142 ]; then echo "Unexpected game exit: $result"; exit "$result"; fi
grep -n -iE 'sys overlay|cellMsgDialog|cellSaveData.*terminal|PAD_SCRIPT|PAD_FILE|presented guest frame|FAULT|SIGNAL' "$run/game.log" | tail -90 || true
grep -q 'windowed.*path' "$run/game.log" || { echo 'No real Metal window; host validation failed.'; exit 1; }
grep -q 'cellSaveData.*funcList terminal result=2.*dirNum=0' "$run/game.log" || {
    echo 'Title did not report zero saved slots; empty-save validation failed.'; exit 1
}
grep -qiE 'sys overlay.*open.*(no sav|no saved|not.*save)' "$run/game.log"
grep -q 'sys overlay/metal.*captured.*overlay=1' "$run/game.log"
grep -q 'sys overlay.*closed.*result=1' "$run/game.log"
if grep -qE 'FAULT|SIGNAL|command buffer failed|sys overlay/metal.*(error|failed)' "$run/game.log"; then
    echo 'Runtime/render failure; inspect game.log'; exit 1
fi
# Convert captures for convenient visual review, keeping the PPM evidence.
python3 - "$run" <<'PY'
from pathlib import Path
import sys
from PIL import Image
for path in Path(sys.argv[1]).glob('frame-*.ppm'):
    Image.open(path).save(path.with_suffix('.png'))
PY
echo "PASS overlay opened/captured/dismissed by Cross. Review frames for title → notice → New Game/story: $run"
echo 'New Game is a visual host check; guest-frame counts alone do not prove the scene transition.'
