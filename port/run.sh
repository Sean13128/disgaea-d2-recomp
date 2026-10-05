#!/bin/sh
# Build and run. usage: port/run.sh [seconds=40] [log name=run]
cd "$(dirname "$0")/.." || exit 1
. ./port/script-common.sh
d2_prepare || exit $?
mkdir -p port/hdd0 port/hdd1 || exit 1
log="$runs/${2:-run}.log"
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" PS3_HDD0_ROOT="$PWD/port/hdd0" PS3_HDD1_ROOT="$PWD/port/hdd1" \
    perl -e 'alarm shift; exec @ARGV' "${1:-40}" "$build/DisgaeaD2Recomp" "$elf" > "$log" 2>&1
status=$?
d2_result "$status" "$log"
exit "$status"
