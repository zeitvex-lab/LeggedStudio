#!/bin/bash
# Renders the app icon from the duck's own vector drawing code.
# Usage: Scripts/make-icon.sh <Micropal-binary> <output.icns>
set -euo pipefail

BIN="${1:?usage: make-icon.sh <binary> <output.icns>}"
OUT="${2:?usage: make-icon.sh <binary> <output.icns>}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ICONSET="$TMP/AppIcon.iconset"
mkdir -p "$ICONSET"

"$BIN" --render-icon "$TMP/icon-1024.png" 1024 0

for SIZE in 16 32 128 256 512; do
    DOUBLE=$((SIZE * 2))
    sips -z "$SIZE" "$SIZE" "$TMP/icon-1024.png" --out "$ICONSET/icon_${SIZE}x${SIZE}.png" >/dev/null
    sips -z "$DOUBLE" "$DOUBLE" "$TMP/icon-1024.png" --out "$ICONSET/icon_${SIZE}x${SIZE}@2x.png" >/dev/null
done

iconutil -c icns "$ICONSET" -o "$OUT"
echo "    icon -> $OUT"
