#!/bin/bash
# Standalone entry point; no configured game build or generated lift required.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
if [[ $# != 2 ]]; then echo 'Usage: port/tests/run.sh <sdk-directory> <new-test-build-directory>' >&2; exit 2; fi
sdk=$(cd "$1" && pwd)
work=$2
cmake -S "$root/port/tests" -B "$work" -G Ninja -DPS3RECOMP_DIR="$sdk" -DPython3_EXECUTABLE="${PYTHON:-$(command -v python3)}"
cmake --build "$work"
ctest --test-dir "$work" --output-on-failure
