#!/bin/bash
set -euo pipefail
source_icon="$1"
output="$2"
scratch="$(mktemp -d "$(dirname "$output")/d2-icon.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
mkdir "$scratch/DisgaeaD2.iconset"
# ICON0 is a landscape PS3 tile; pad it instead of stretching the artwork.
sips --padToHeightWidth 320 320 --padColor 191A20 "$source_icon" \
    --out "$scratch/square.png" >/dev/null
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$scratch/square.png" \
        --out "$scratch/DisgaeaD2.iconset/icon_${size}x${size}.png" >/dev/null
    pixels=$((size * 2))
    sips -z "$pixels" "$pixels" "$scratch/square.png" \
        --out "$scratch/DisgaeaD2.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
if ! iconutil -c icns "$scratch/DisgaeaD2.iconset" -o "$output"; then
    # Some restricted hosts reject iconutil's image encoder. sips can still
    # produce a valid 512-pixel ICNS without that service.
    echo 'iconutil unavailable; using the sips 512-pixel ICNS encoder' >&2
    sips -s format icns "$scratch/DisgaeaD2.iconset/icon_512x512.png" \
        --out "$output" >/dev/null
fi
