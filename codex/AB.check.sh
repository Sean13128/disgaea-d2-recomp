#!/bin/bash
# Compatibility entry point for the maintained asset-free CTest suite.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d "${TMPDIR:-/Volumes/Data/ai-tmp/codex}/D2-tests.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
PYTHON="${PYTHON:-$root/.venv/bin/python}" "$root/port/tests/run.sh" "${PS3RECOMP_DIR:-$root/ps3recomp}" "$scratch"
