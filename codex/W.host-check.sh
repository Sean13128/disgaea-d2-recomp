#!/bin/bash
# Real Mac: bash codex/W.host-check.sh [seconds, default 40]
# Leave the title menu open for the default BGM analysis (25 seconds onward).
set -eu
cd "$(dirname "$0")/.."
mkdir -p port/runs
out=$(mktemp -d "$PWD/port/runs/W-host.XXXXXX")
task_scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/W-host.XXXXXX)
mkdir -p "$task_scratch/hdd1"
(
  cd port
  cmake -B build-w -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
    -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include
) > "$out/configure.log" 2>&1
cmake --build port/build-w -j4 > "$out/build.log" 2>&1
echo "Audio capture: $out; leave the title BGM playing."
status=0
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$PWD/port/hdd0" PS3_HDD1_ROOT="$task_scratch/hdd1" \
SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-coreaudio}" D2_MOVIE_SKIP=1 \
AUDIO_PEAK=1 AUDIO_RATE=1 AUDIO_WAV="$out/mix.f32le" \
perl -e 'alarm shift; exec @ARGV' "${1:-40}" \
  ./port/build-w/DisgaeaD2Recomp work/EBOOT.elf > "$out/run.log" 2>&1 || status=$?
grep -nE 'SDL output|Audio backend init failed|audio-rate|audio-peak|audio-ring|decode error' \
  "$out/run.log" | tail -35 || true
if [[ "$status" != 0 && "$status" != 142 ]]; then
  echo "Unexpected game exit: $status; inspect $out/run.log" >&2
  exit "$status"
fi
python3 codex/W.analyze.py "$out/mix.f32le" --start "${W_BGM_START:-25}" \
  --wav "$out/mix.wav" | tee "$out/analysis.log"
echo "Listen to $out/mix.wav. Scratch cache retained at $task_scratch."
