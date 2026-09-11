#!/bin/bash
# Set USB camera exposure/brightness/contrast at boot
# Called from /etc/rc.local

BRIGHTNESS=-15
CONTRAST=3
MAX_WAIT=15

log() {
    echo "[camera_init] $(date '+%H:%M:%S') $1"
}

log "Waiting for USB camera device..."

# Wait for a USB camera /dev/video device to appear
ELAPSED=0
DEVICE=""
while [ $ELAPSED -lt $MAX_WAIT ]; do
    for dev in /dev/video*; do
        [ -e "$dev" ] || continue
        name=$(v4l2-ctl -d "$dev" --all 2>/dev/null | grep "Card type" | head -1)
        if echo "$name" | grep -qiE "USB|Live|Camera|CAME"; then
            if v4l2-ctl -d "$dev" --list-formats 2>/dev/null | grep -q "MJPG\|YUYV"; then
                DEVICE="$dev"
                log "Found: $dev ($name)"
                break 2
            fi
        fi
    done
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

if [ -z "$DEVICE" ]; then
    log "No USB camera found after ${MAX_WAIT}s — giving up"
    exit 0
fi

log "Setting exposure_auto=3, brightness=$BRIGHTNESS, contrast=$CONTRAST on $DEVICE"
v4l2-ctl -d "$DEVICE" --set-ctrl=exposure_auto=3 2>/dev/null || true
v4l2-ctl -d "$DEVICE" --set-ctrl=brightness=$BRIGHTNESS 2>/dev/null || true
v4l2-ctl -d "$DEVICE" --set-ctrl=contrast=$CONTRAST 2>/dev/null || true

log "Done."
