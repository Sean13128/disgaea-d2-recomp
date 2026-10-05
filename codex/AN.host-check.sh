#!/bin/bash
# Real-Mac verification: no profiling, packaging, cleanup, or save deletion.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
build="$root/port/build-an"
run_dir="$(mktemp -d "$root/port/runs/AN-host.XXXXXX")"
cmake -S port -B port/build-an -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp-140 \
    -DCMAKE_C_FLAGS=-I/opt/homebrew/include -DCMAKE_CXX_FLAGS=-I/opt/homebrew/include \
    -DCMAKE_OBJC_FLAGS=-I/opt/homebrew/include -DCMAKE_OBJCXX_FLAGS=-I/opt/homebrew/include \
    -DD2_GAME_VERSION=140 -DPython3_EXECUTABLE="$root/.venv/bin/python" > "$run_dir/configure.log" 2>&1
cmake --build "$build" --target DisgaeaD2Recomp -j 4 > "$run_dir/build.log" 2>&1
ctest --test-dir "$build" -R 'd2.AN-' --output-on-failure > "$run_dir/tests.log" 2>&1
printf 'Focus the game and press F2 (or Game → Flag Issue…). Type a note and Return; try Escape on another flag.\nCheck that the Flagged #N toast appears and animation/audio continue. F1 should still open cheats.\nLog directory: %s\n' "$run_dir"
# auto mode makes one timed bookmark; interactive mode exercises the real key/menu.
automatic=0
if [[ "${1:-}" == auto ]]; then automatic=15; fi
set +e
PS3_VFS_ROOT="$root/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$root/port/hdd0" D2_SETTINGS_PATH="$run_dir/settings.json" \
D2_STOP_AFTER_SECONDS=35 D2_FLAG_TEST_AFTER_SECONDS="$automatic" \
perl -e 'alarm shift; exec @ARGV' 40 "$build/DisgaeaD2Recomp" "$root/work/v140/EBOOT.elf" > "$run_dir/game.log" 2>&1
status=$?
set -e
if [[ "$status" != 0 ]]; then
    printf 'Runner exited %s; inspect %s\n' "$status" "$run_dir/game.log"
    exit "$status"
fi
"$root/.venv/bin/python" - "$run_dir/game.log" "$root/port/flags/flags.jsonl" <<'PY'
import importlib.util
import json
from pathlib import Path
import struct
import sys
spec = importlib.util.spec_from_file_location("flags", "tools/d2_flags.py")
flags = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flags)
bookmarks = []
with Path(sys.argv[1]).open() as log:
    for line in log:
        if line.startswith('{'):
            try:
                event = json.loads(line)
                if event.get('type') == 'flag': bookmarks.append(event)
            except ValueError: pass
assert bookmarks, 'No flags created: rerun and press F2, or pass auto.'
session = bookmarks[-1]['session']
records = [r for r in flags.load_flags(sys.argv[2]) if r['session'] == session]
for r in records:
    assert r['cpu_available'] and r['cpu_window_seconds'] >= 1.5
    assert r['rss_bytes'] > 0 and r['threads']
    assert r['frame_metrics_available'], 'No Metal telemetry: run outside the sandbox.'
    assert r['guest_fps_1s'] > 0 and r['display_fps_1s'] > 0
    assert r.get('screenshot_status') == 'saved', r.get('screenshot_status')
    with Path(r['screenshot']).open('rb') as png:
        header = png.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n'
    width, height = struct.unpack('>II', header[16:24])
    assert width > 0 and height > 0
print(flags.table(records))
print('[AN host] live Metal counters, ~2s CPU, RSS and PNG files: PASS')
PY
printf 'Evidence retained in %s\n' "$run_dir"
