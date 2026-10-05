#!/bin/bash
# Install user-owned update/DLC into an external hdd0.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
exec "${D2_PYTHON:-python3}" "$root/port/src/d2_install_content.py" "$root/dlc" "$@"
