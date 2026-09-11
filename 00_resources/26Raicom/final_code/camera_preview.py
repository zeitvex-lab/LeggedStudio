#!/usr/bin/env python3
"""USB Camera Preview using OpenCV"""
import cv2
import sys

# ============================================================
# 🔧 可调参数 — 在这里改参数即可
# ============================================================

CAMERA_DEV = "/dev/video0"      # 摄像头设备路径
WIDTH = 1280                    # 画面宽度
HEIGHT = 720                    # 画面高度

# --- 曝光控制 ---
# AUTO_EXPOSURE: 1 = 手动曝光, 3 = 自动曝光 (默认)
EXPOSURE_AUTO = 1               # 1=手动  3=自动
EXPOSURE_VALUE = 500             # 手动曝光值 (范围 3~2047, 越小越暗, 默认166, 仅 AUTO=1 时生效)

# ============================================================

# Open camera with V4L2 backend
cap = cv2.VideoCapture(CAMERA_DEV, cv2.CAP_V4L2)
if not cap.isOpened():
    print(f"❌ Cannot open {CAMERA_DEV}")
    sys.exit(1)

# Set MJPEG format and resolution
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, 30)

# 设置曝光
cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, EXPOSURE_AUTO)
if EXPOSURE_AUTO == 1:
    cap.set(cv2.CAP_PROP_EXPOSURE, EXPOSURE_VALUE)

actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
actual_fps = cap.get(cv2.CAP_PROP_FPS)
actual_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
fourcc_str = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
expo_mode = "手动" if EXPOSURE_AUTO == 1 else "自动"
expo_info = f"曝光={EXPOSURE_VALUE}" if EXPOSURE_AUTO == 1 else "曝光=自动"
actual_expo = cap.get(cv2.CAP_PROP_EXPOSURE)
expo_readback = f"(实际={actual_expo:.0f})" if EXPOSURE_AUTO == 1 else ""
print(f"✅ Camera opened: {actual_w:.0f}x{actual_h:.0f} @ {actual_fps:.0f}fps [{fourcc_str}] | {expo_info} {expo_readback}")

cv2.namedWindow("USB Camera", cv2.WINDOW_NORMAL)
cv2.resizeWindow("USB Camera", WIDTH, HEIGHT)

print("📷 Streaming... Press 'q' or ESC to quit.")
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️  Frame read failed, retrying...")
            continue
        cv2.imshow("USB Camera", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):  # 'q' or ESC
            break
finally:
    cap.release()
    cv2.destroyAllWindows()
    print("👋 Camera closed.")
