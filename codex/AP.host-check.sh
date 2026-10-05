#!/bin/bash
# Real Mac check, settings-only mute/volume; copies saves and retains all logs.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -d /Volumes/Data ]] || { echo '/Volumes/Data is not mounted'; exit 1; }
task_scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/AP-host.XXXXXX)
run_dir=$(mktemp -d "$PWD/port/runs/AP-host.XXXXXX")
cmake -S port -B port/build-ap -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp-140 -DD2_GAME_VERSION=140 \
  -DPython3_EXECUTABLE="$PWD/.venv/bin/python" \
  -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
  -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include > "$run_dir/configure.log" 2>&1
cmake --build port/build-ap -j 4 > "$run_dir/build.log" 2>&1
save_source="$HOME/Library/Application Support/DisgaeaD2Recomp/hdd0"
[[ -d $save_source ]] || save_source="$PWD/port/hdd0"
cp -R "$save_source" "$task_scratch/hdd0"
printf '%s\n' '{"mute":true,"volume":0,"mute_unfocused":false}' > "$task_scratch/settings.json"
export SDL_AUDIODRIVER=coreaudio
export PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]"
export PS3_HDD0_ROOT="$task_scratch/hdd0" PS3_HDD1_ROOT="$task_scratch/hdd1"
export D2_SETTINGS_PATH="$task_scratch/settings.json" D2_MOVIE_SKIP=1
export D2_AUDIO_INIT_DELAY_MS=150 PS3RECOMP_ATRAC_TRACE=1 AUDIO_RATE=1
# After silent boot, restore sound, mute, restore, zero, lower volume, focus mute,
# focus restore. These call the same settings/gain path as the menu.
export D2_AUDIO_SETTINGS_SCRIPT='25:1:0:0,30:1:1:0,35:1:0:0,40:0:0:0,45:0.4:0:0,50:1:0:1:0,55:1:0:1:1,60:1:0:0'
export PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_01
export PAD_SCRIPT='10:0x4000,14:0x4000'
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY PAD_FILE D2_WARP_STAGE D2_SETTINGS_OVERRIDE D2_SETTINGS_LIVE_OVERRIDE
printf 'Run: %s\nCopied saves: %s\n' "$run_dir" "$task_scratch"
echo 'After 60 s, play hub -> map30005 area -> hub, then idle for two music loops.'
status=0
perl -e 'alarm shift; exec @ARGV' "${AP_SECONDS:-230}" ./port/build-ap/DisgaeaD2Recomp work/v140/EBOOT.elf > "$run_dir/run.log" 2>&1 || status=$?
[[ $status == 142 ]] || { echo "Unexpected runner exit $status"; exit 1; }
grep -q 'SDL output driver=coreaudio' "$run_dir/run.log"
grep -q 'waited for SurMixer queue publication: key=0x8000CAFE02460300' "$run_dir/run.log"
grep -q 'settings=50:1:0:1:0 effective_gain=0.000' "$run_dir/run.log"
grep -q 'remain=-3' "$run_dir/run.log"
if grep -qE '\[cellAtrac\] WARNING|SetNotifyEventQueue\(key=0x0\)|OOB access|HOST CORRUPTION' "$run_dir/run.log"; then
  grep -nE '\[cellAtrac\] WARNING|SetNotifyEventQueue\(key=0x0\)|OOB access|HOST CORRUPTION' "$run_dir/run.log" | head -20
  exit 1
fi
grep -nE 'D2 audio\]|D2 audio test|SetData|Decode handle|audio-rate' "$run_dir/run.log" | tail -16
echo "PASS automated audio checks. Confirm audible output and area transitions; logs: $run_dir"
