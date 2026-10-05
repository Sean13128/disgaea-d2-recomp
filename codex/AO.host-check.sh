#!/bin/bash
# Compare synth2 CPU on real Metal using AO's preserved baseline/current binary.
# Run when other builds are idle. Copies saves and retains all evidence; no rm.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -d /Volumes/Data/ai-tmp/codex ]] || { echo '/Volumes/Data scratch unavailable'; exit 1; }
out=$(mktemp -d "$PWD/port/runs/AO-host.XXXXXX")
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-AO-host.XXXXXX)
printf '%s\n' "$scratch" > "$out/scratch.txt"
if [[ ${AO_SKIP_BUILD:-0} != 1 ]]; then
    cmake -S port -B port/build-ao -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp-140 -DD2_GAME_VERSION=140 \
        -DPython3_EXECUTABLE="$PWD/.venv/bin/python" \
        -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include > "$out/configure.log" 2>&1
    cmake --build port/build-ao -j 4 > "$out/build.log" 2>&1
    ctest --test-dir port/build-ao --output-on-failure -j 4 > "$out/ctest.log" 2>&1
fi
unset PAD_FILE PAD_SCRIPT PAD_STICK PAD_SWEEP D2_WARP_STAGE
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY PS3RECOMP_METAL_FRAME_DUMP
unset SPU_LS_LOWREAD SPU_LS_WATCH SPU_SMC_WATCH SPU_STEPTRACE SPU_EXITTRACE
if [[ ${AO_HEADLESS:-0} == 1 ]]; then export PS3RECOMP_METAL_HEADLESS=1; fi
for mode in before after; do
    binary=./port/build-ao/DisgaeaD2Recomp
    [[ $mode != before ]] || binary=./port/build-ao/reference/DisgaeaD2Recomp
    [[ -x "$binary" ]] || { echo "Missing AO binary: $binary"; exit 1; }
    mkdir -p "$scratch/$mode" "$out/$mode"
    cp -R port/hdd0 "$scratch/$mode/hdd0"
    echo "$mode: leave the loaded hub steady through the sample ($out/$mode)"
    PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
    PS3_HDD0_ROOT="$scratch/$mode/hdd0" PS3_HDD1_ROOT="$scratch/$mode/hdd1" \
    D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
    PAD_SCRIPT='12:0x4000,18:0x4000,24:0x4000' PAD_TRACE=1 \
    AUDIO_WAV="$out/$mode/mix.f32" AUDIO_RATE=1 PS3_HOST_CPU=1 \
    GCM_FLIP_TRACE=1 GCM_FLIPCOUNT=1 \
        perl -e 'alarm shift; exec @ARGV' 40 "$binary" work/v140/EBOOT.elf > "$out/$mode/game.log" 2>&1 &
    pid=$!
    sleep 30
    if kill -0 "$pid" 2>/dev/null; then
        sample "$pid" 5 -file "$out/$mode/sample.txt" > "$out/$mode/sample.log" 2>&1 || true
    fi
    status=0; wait "$pid" || status=$?
    printf '%s exit=%s (142 expected)\n' "$mode" "$status" | tee -a "$out/summary.txt"
    [[ $status == 142 ]] || { echo 'Game exited early'; exit 1; }
    if [[ ${AO_HEADLESS:-0} != 1 ]]; then
        grep -q 'Metal backend init OK' "$out/$mode/game.log" || { echo 'Real Metal unavailable'; exit 1; }
    fi
    grep -nE 'LOAD complete|audio-rate|gcm-rate|HOSTCPU|FAULT|OOB access|HOST CORRUPTION' \
        "$out/$mode/game.log" > "$out/$mode/metrics.txt" || true
    grep -q "LOAD complete for 'NPUB31321_NORMAL_00'" "$out/$mode/game.log" || { echo 'Save did not load'; exit 1; }
done
"$PWD/.venv/bin/python" port/tests/AO.audio-compare.py "$out/before/mix.f32" "$out/after/mix.f32" | tee "$out/audio-compare.txt"
echo "Evidence: $out; copied saves retained: $scratch"
echo 'Compare _synth2 Group busy/total samples at steady 60 fps; target <25% busy.'
