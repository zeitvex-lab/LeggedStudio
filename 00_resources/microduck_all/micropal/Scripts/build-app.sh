#!/bin/bash
# Builds Micropal.app into build/.
# Usage: Scripts/build-app.sh [--universal]
set -euo pipefail
cd "$(dirname "$0")/.."

# macOS ships bash 3.2, where "${EMPTY_ARRAY[@]}" trips `set -u`; use a plain string.
ARCH_FLAGS=""
if [[ "${1:-}" == "--universal" ]]; then
    ARCH_FLAGS="--arch arm64 --arch x86_64"
fi

echo "==> swift build -c release $ARCH_FLAGS"
# shellcheck disable=SC2086
swift build -c release $ARCH_FLAGS

# shellcheck disable=SC2086
BIN="$(swift build -c release $ARCH_FLAGS --show-bin-path)/Micropal"
APP="build/Micropal.app"

echo "==> Assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/Micropal"
cp Support/Info.plist "$APP/Contents/Info.plist"

echo "==> Generating icon"
Scripts/make-icon.sh "$APP/Contents/MacOS/Micropal" "$APP/Contents/Resources/AppIcon.icns"

# Ad-hoc signing: without it, Apple-silicon Macs report transferred binaries
# as "damaged". Recipients still use right-click -> Open the first time.
echo "==> Ad-hoc code signing"
codesign --force --deep --sign - "$APP"

echo "==> Done: $APP"
