#!/bin/bash
# USB Camera Preview Script
# Fixes the white-screen issue by setting brightness and launches preview
set -e

# --- Config ---
WIDTH=1280
HEIGHT=720
FPS=30
BRIGHTNESS=-20
CONTRAST=3

# --- Find USB camera device ---
echo "🔍 Looking for USB camera..."
DEVICE=""
for dev in /dev/video*; do
    name=$(v4l2-ctl -d "$dev" --all 2>/dev/null | grep "Card type" | head -1)
    if echo "$name" | grep -qiE "USB|Live|Camera|CAME"; then
        # Check if it supports video capture (not metadata)
        if v4l2-ctl -d "$dev" --list-formats 2>/dev/null | grep -q "MJPG\|YUYV"; then
            DEVICE="$dev"
            echo "✅ Found: $dev ($name)"
            break
        fi
    fi
done

if [ -z "$DEVICE" ]; then
    echo "❌ No USB camera found!"
    echo "   Available devices:"
    v4l2-ctl --list-devices 2>/dev/null | head -20
    exit 1
fi

# --- Set controls to fix white screen ---
echo "🎛️  Setting brightness=$BRIGHTNESS, contrast=$CONTRAST..."
v4l2-ctl -d "$DEVICE" --set-ctrl=exposure_auto=3 2>/dev/null || true
v4l2-ctl -d "$DEVICE" --set-ctrl=brightness=$BRIGHTNESS 2>/dev/null || true
v4l2-ctl -d "$DEVICE" --set-ctrl=contrast=$CONTRAST 2>/dev/null || true

# --- Launch preview ---
echo "📷 Starting camera preview (${WIDTH}x${HEIGHT} @ ${FPS}fps)..."
echo "   Press Ctrl+C to stop."

gst-launch-1.0 \
    v4l2src device="$DEVICE" \
        extra-controls="c,brightness=$BRIGHTNESS,contrast=$CONTRAST" \
        ! image/jpeg,width=$WIDTH,height=$HEIGHT,framerate=$FPS/1 \
        ! jpegdec \
        ! videoconvert \
        ! xvimagesink sync=false

echo "👋 Camera preview stopped."
