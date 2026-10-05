#!/bin/sh
# Diagnostic session: play normally, reproduce the problem, then close the window (Cmd+Q).
# Uses a COPY of port/hdd0 saves (your saves are never modified). Output: port/runs/capture.XXXX/
cd "$(dirname "$0")/.." || exit 1
. ./port/script-common.sh
d2_prepare || exit $?
source_hdd=${D2_CAPTURE_HDD0:-port/hdd0}
test -d "$source_hdd/home/00000001/savedata" || {
    echo "Missing saves: $source_hdd/home/00000001/savedata" >&2; exit 1;
}
set -- "$source_hdd"/home/00000001/savedata/*/SAVEDATA.DAT
test -s "$1" || { echo "No saves available to capture: $source_hdd" >&2; exit 1; }
out=$(mktemp -d "$runs/capture.XXXXXX") || exit 1
mkdir -p "$out/hdd0" "$out/hdd1" "$out/frames" || exit 1
cp -R "$source_hdd/." "$out/hdd0/" || {
    echo "Save copy failed; capture cancelled: $out" >&2; exit 1;
}
echo "Capturing to $out — reproduce the issue, then quit the game window."
D2_MOVIE_SKIP="${D2_MOVIE_SKIP:-1}" PS3_TITLE="Disgaea D2 (capture)" \
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$out/hdd0" PS3_HDD1_ROOT="$out/hdd1" \
D2_BOOT_TRACE=1 PS3RECOMP_TRACE_HOTREAD=1 PAD_TRACE=1 AUDIO_PEAK=1 AUDIO_RATE=1 AUDIO_WAV="$out/mix.f32le" \
PS3RECOMP_METAL_FRAME_DUMP="$out/frames/f%u.ppm" PS3RECOMP_METAL_FRAME_DUMP_EVERY=600 \
  perl -e 'alarm shift; exec @ARGV' "${D2_CAPTURE_SECONDS:-0}" "$build/DisgaeaD2Recomp" "$elf" > "$out/run.log" 2>&1
status=$?
d2_result "$status" "$out"
exit "$status"
