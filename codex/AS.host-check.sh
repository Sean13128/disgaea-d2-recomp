#!/bin/bash
# AS: real-game check of the native Cheats window/menu (no in-game overlay).
# Run 1 types a new HL into the native General field, toggles Infinite HP from
# the Cheats menu, captures the window/menu, then saves through D2's own
# callbacks. Run 2 reloads the same HDD copy and must read the new HL.
# Uses private copies of port/hdd0/hdd1 under /Volumes/Data/ai-tmp/claude/AS-*.
# AS_VERSION=140 (default, port/build-as) or 100 (port/build-as100).
set -euo pipefail
cd "$(dirname "$0")/.."
pgrep -x DisgaeaD2Recomp > /dev/null && { echo 'Another DisgaeaD2Recomp is running; not starting.'; exit 1; }
version=${AS_VERSION:-140}
case "$version" in 100) elf=work/EBOOT.elf; build=port/build-as100;; 140) elf=work/v140/EBOOT.elf; build=port/build-as;; *) exit 2;; esac
grep -q "D2_GAME_VERSION:STRING=$version" "$build/CMakeCache.txt" || { echo "$build is not a $version build"; exit 1; }
seconds=${AS_SECONDS:-55}
scratch=$(mktemp -d /Volumes/Data/ai-tmp/claude/AS-host.XXXXXX)
trap 'if [[ ${AS_KEEP_HDD:-0} != 1 ]]; then rm -rf "$scratch"; fi' EXIT
out=$(mktemp -d "$PWD/port/runs/AS-host-$version.XXXXXX")
mkdir -p "$out/shots"
cp -R port/hdd0 "$scratch/hdd0"
[[ ! -d port/hdd1 ]] || cp -R port/hdd1 "$scratch/hdd1"
if [[ $version == 140 ]]; then port/install-content.sh --into "$scratch/hdd0" > "$out/install.log"; fi
slot=NPUB31321_NORMAL_01
base=$(.venv/bin/python -c "import sys;d=open(sys.argv[1],'rb').read();print(int.from_bytes(d[0x568:0x570],'big'))" "port/hdd0/home/00000001/savedata/$slot/SAVEDATA.DAT")
target=$((base + 1000))
unset PAD_FILE D2_WARP_STAGE D2_CHEATS_TEST_HL D2_CHEATS_TEST_SAVE D2_CHEATS_TEST_EDIT PS3RECOMP_METAL_FRAME_DUMP
export PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]"
export PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" D2_CHEATS_PRESET_DIR="$scratch/presets"
export D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=$slot SDL_AUDIODRIVER=dummy
export PAD_SCRIPT='10:0x4000,14:0x4000' D2_SETTINGS_PATH="$scratch/settings.json"
run() { # name, extra env...
    local name=$1; shift
    local status=0
    env "$@" perl -e 'alarm shift; exec @ARGV' "$seconds" "./$build/DisgaeaD2Recomp" "$elf" > "$out/$name.log" 2>&1 &
    local pid=$!
    if [[ $name == edit ]]; then # real window-server capture of the native window, by id
        for _ in $(seq 1 $((seconds * 2))); do
            id=$(sed -n 's/.*\[D2 cheats UI\] shot .*general.png window=\([0-9]*\).*/\1/p' "$out/$name.log" | head -1)
            if [[ -n $id ]]; then screencapture -x -o -l "$id" "$out/shots/window-general-screencapture.png" 2>/dev/null || true; break; fi
            sleep 0.5
        done
    fi
    wait "$pid" || status=$?
    [[ $status == 142 ]] || { echo "FAIL $name: exit $status ($out/$name.log)"; exit 1; }
    if grep -qE 'FAULT|Bus error|OOB access|HOST CORRUPTION' "$out/$name.log"; then echo "FAIL $name: fault ($out/$name.log)"; exit 1; fi
    grep -q "LOAD complete for '$slot'" "$out/$name.log" || { echo "FAIL $name: save not loaded"; exit 1; }
}
run edit D2_CHEATS_UI_OPEN=general D2_CHEATS_UI_WAIT_UNITS=118 D2_CHEATS_UI_TEST_HL="$target" D2_CHEATS_UI_TEST_MENU=1 \
    D2_CHEATS_UI_SHOT_DIR="$out/shots" D2_CHEATS_TEST_SAVE_WHEN_HL="$target"
grep -q "\[D2 cheats\] write hl offset=000568 $base -> $target" "$out/edit.log" || { echo 'FAIL: native HL edit not written by the PPU'; exit 1; }
grep -q "test: snapshot HL=$target hp_lock=1" "$out/edit.log" || { echo 'FAIL: snapshot did not reflect HL/menu toggle'; exit 1; }
grep -q "SAVE complete for '$slot'" "$out/edit.log" || { echo 'FAIL: save did not complete'; exit 1; }
saved=$(.venv/bin/python -c "import sys;d=open(sys.argv[1],'rb').read();print(int.from_bytes(d[0x568:0x570],'big'))" "$scratch/hdd0/home/00000001/savedata/$slot/SAVEDATA.DAT")
[[ $saved == "$target" ]] || { echo "FAIL: saved HL $saved != $target"; exit 1; }
run reload
grep -q "\[D2 cheats\] resolved .*HL=$target " "$out/reload.log" || { echo 'FAIL: reload did not read the edited HL'; exit 1; }
grep -q 'sys overlay.*D2 cheats' "$out/edit.log" && { echo 'FAIL: in-game cheat overlay still opened'; exit 1; }
grep -nE '\[D2 cheats( UI)?\]' "$out/edit.log" | grep -vE 'unit=[0-9]+ name' > "$out/evidence.txt" || true
grep -nE 'SAVE complete|LOAD complete' "$out/edit.log" >> "$out/evidence.txt" || true
grep -nE '\[D2 cheats\] resolved|LOAD complete' "$out/reload.log" >> "$out/evidence.txt" || true
printf 'PASS %s: HL %s -> %s typed in the native window, saved (SAVEDATA.DAT) and reloaded.\nEvidence: %s\nShots: %s\n' \
    "$version" "$base" "$target" "$out/evidence.txt" "$out/shots"
