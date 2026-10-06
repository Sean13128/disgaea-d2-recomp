#!/bin/bash
# The in-game cheat overlay was replaced by the native Cheats menu/window (AS).
# Real-game check (edit via the native window, save, reload): codex/AS.host-check.sh.
# AF_VERSION=100|140 maps to AS_VERSION.
exec env AS_VERSION="${AF_VERSION:-${AS_VERSION:-140}}" bash "$(dirname "$0")/AS.host-check.sh"
