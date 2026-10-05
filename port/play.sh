#!/bin/sh
# Play Disgaea D2 natively. Builds if needed; saves live in port/hdd0 + port/hdd1.
# Controls: see "Controls" in OPERATIONS.md (arrows, Z/Enter = Cross, X/Esc = Circle, ...).
cd "$(dirname "$0")/.." || exit 1
. ./port/script-common.sh
d2_prepare || exit $?
mkdir -p port/hdd0 port/hdd1
PS3_TITLE="Disgaea D2" \
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$PWD/port/hdd0" PS3_HDD1_ROOT="$PWD/port/hdd1" \
  exec "$build/DisgaeaD2Recomp" "$elf" > "$runs/play-latest.log" 2>&1
