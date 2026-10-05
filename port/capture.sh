#!/bin/sh
# Diagnostic session: play normally, reproduce the problem, then close the window (Cmd+Q).
# Uses a COPY of port/hdd0 saves (your saves are never modified). Output: port/runs/capture.XXXX/
cd "$(dirname "$0")/.."
cmake --build port/build -j6 > port/runs/build.log 2>&1 || { tail -30 port/runs/build.log; exit 1; }
out=$(mktemp -d "$PWD/port/runs/capture.XXXX")
mkdir -p "$out/hdd0" "$out/hdd1" "$out/frames"
cp -R port/hdd0/. "$out/hdd0/"
echo "Capturing to $out — reproduce the issue, then quit the game window."
D2_MOVIE_SKIP="${D2_MOVIE_SKIP:-1}" PS3_TITLE="Disgaea D2 (capture)" \
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$out/hdd0" PS3_HDD1_ROOT="$out/hdd1" \
D2_BOOT_TRACE=1 PS3RECOMP_TRACE_HOTREAD=1 PAD_TRACE=1 \
PS3RECOMP_METAL_FRAME_DUMP="$out/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=120 \
  ./port/build/DisgaeaD2Recomp work/EBOOT.elf > "$out/run.log" 2>&1
echo "Done: $out"
