#!/bin/sh
# Build and run the D2 port. usage: port/run.sh [seconds=40] [log name=run]
set -e
cd "$(dirname "$0")/.."
cmake --build port/build -j6 > port/runs/build.log 2>&1 || { tail -30 port/runs/build.log; exit 1; }
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" PS3_HDD0_ROOT="$PWD/port/hdd0" \
  perl -e 'alarm shift; exec @ARGV' "${1:-40}" ./port/build/DisgaeaD2Recomp work/EBOOT.elf \
  > "port/runs/${2:-run}.log" 2>&1 || echo "exit $?"
