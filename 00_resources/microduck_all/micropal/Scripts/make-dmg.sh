#!/bin/bash
# Packages build/Micropal.app into dist/Micropal.dmg (+ .zip).
# Run Scripts/build-app.sh first (this script calls it if the app is missing).
set -euo pipefail
cd "$(dirname "$0")/.."

APP="build/Micropal.app"
[[ -d "$APP" ]] || Scripts/build-app.sh

mkdir -p dist
rm -f dist/Micropal.dmg dist/Micropal.zip

STAGE="$(mktemp -d)"
TMP="$(mktemp -d)"
trap 'rm -rf "$STAGE" "$TMP"' EXIT

cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/HOW TO OPEN.txt" <<'EOF'
Micropal
=================

1. Drag "Micropal" into the Applications folder.
2. FIRST LAUNCH: right-click (or Control-click) the app and choose "Open",
   then click "Open" in the dialog. This is needed once because the app
   isn't notarized by Apple (it's a free community build).
   On macOS 15+, if that is refused: open System Settings > Privacy &
   Security, scroll down, and click "Open Anyway".
3. A little pal appears at the bottom of your screen, and its icon
   appears in the menu bar. Use the menu bar icon for settings (colors,
   size, behaviors) or to quit.

Enjoy your Micropal!
EOF

echo "==> Creating dist/Micropal.dmg"
# Give the mounted volume the app icon: bundle a .VolumeIcon.icns, then flip
# the custom-icon Finder bit on the volume root (needs a read-write image,
# so build UDRW first and compress to UDZO after).
cp "$APP/Contents/Resources/AppIcon.icns" "$STAGE/.VolumeIcon.icns"
hdiutil create -volname "Micropal" -srcfolder "$STAGE" -ov -format UDRW \
    "$TMP/Micropal-rw.dmg"
MOUNT="$(hdiutil attach "$TMP/Micropal-rw.dmg" -readwrite -noverify -noautoopen \
    | grep -o '/Volumes/.*')"
SetFile -a C "$MOUNT"
hdiutil detach "$MOUNT" >/dev/null
hdiutil convert "$TMP/Micropal-rw.dmg" -format UDZO -ov -o dist/Micropal.dmg

echo "==> Creating dist/Micropal.zip"
ditto -c -k --keepParent "$APP" dist/Micropal.zip

echo "==> Done:"
ls -lh dist/
