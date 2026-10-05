#!/bin/bash
# Read-only source -> importer makes a COPY -> headless Continue/load check.
# Uses only port/build-ac. AC_FAST=1 skips movies and tests with 40 s alarm.
set -euo pipefail
cd "$(dirname "$0")/.."
source=${1:?Usage: bash codex/AC.host-check.sh path/to/console/save}
out=$(mktemp -d "$PWD/port/runs/AC-load.XXXXXX")
.venv/bin/python tools/d2_save_import.py "$source" > "$out/import.log"
hdd0=$(sed -n 's/^HDD0=//p' "$out/import.log")
slot=$(sed -n 's/^SLOT=//p' "$out/import.log")
mkdir -p "$out/frames"
seconds=115
pad='75:0x4000'
if [[ ${AC_FAST:-0} == 1 ]]; then
    seconds=40
    pad='10:0x4000,14:0x4000'
fi
status=0
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$hdd0" PS3_HDD1_ROOT="$out/hdd1" \
PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR="$slot" \
PS3RECOMP_METAL_HEADLESS=1 D2_MOVIE_SKIP="${AC_MOVIE_SKIP:-1}" \
PS3RECOMP_RSX_FIFO_ONLY=1 D2_WARP_TRACE=1 D2_BOOT_TRACE=1 PAD_TRACE=1 \
PAD_SCRIPT="${AC_PAD_SCRIPT:-$pad}" \
PS3RECOMP_METAL_FRAME_DUMP="$out/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=300 \
perl -e 'alarm shift; exec @ARGV' "$seconds" \
./port/build-ac/DisgaeaD2Recomp work/EBOOT.elf > "$out/run.log" 2>&1 || status=$?
grep -nE 'cellSaveData|cellMsgDialog|no Metal|Metal backend|PAD_SCRIPT|\[D2-warp\].*map_id|FAULT|SIGNAL' \
    "$out/run.log" > "$out/evidence.txt" || true
printf 'Capture: %s\nHDD0: %s\nSlot: %s\nExit: %s\n' "$out" "$hdd0" "$slot" "$status" > "$out/summary.txt"
last_map=$(sed -n 's/.*\[D2-warp\].*map_id=\([0-9]*\).*/\1/p' "$out/run.log" | tail -1)
if [[ $status != 142 ]] || ! grep -q "LOAD complete for '$slot'" "$out/run.log" \
    || ! grep -q 'file op=0 type=0.*SAVEDATA.DAT.*size=1498152.* -> 1498152' "$out/run.log" \
    || [[ ! "$last_map" =~ ^300[0-9]{2}$ ]]; then
    echo "FAIL: load/hub evidence incomplete. $out/summary.txt"
    exit 1
fi
printf 'PASS: secure-file READ complete; final gameplay map=%s.\n' "$last_map" >> "$out/summary.txt"
printf 'PASS: %s\n' "$out/summary.txt"
