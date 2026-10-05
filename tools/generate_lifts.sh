#!/bin/bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
exec "${PYTHON:-python3}" "$root/tools/generate_lifts.py" "$@"
