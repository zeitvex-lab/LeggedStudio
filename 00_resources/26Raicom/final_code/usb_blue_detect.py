#!/usr/bin/env python3
"""
USB 摄像头蓝色区域检测脚本
========================
用 USB 摄像头（非 RealSense）检测画面中的蓝色区域，输出：
  - 物体中心坐标 (x, y)
  - 物体面积 (px²)
  - 外接矩形 bbox
  - 画面下半部分蓝色占比 (Phase 8 蓝色驱动前进用的判定量)
  - 当前 HSV 范围（可 Trackbar 实时调参）

参考: 视觉抓取/color_object_detector.py（原为 RealSense + 深度测距，
本脚本改用 USB 摄像头，去掉深度，加入"下半画面蓝色占比"供 Phase 8 用）。

用法:
    # 实时预览 + HSV Trackbar 调参
    python3 usb_blue_detect.py

    # 单帧检测（打印结果后退出）
    python3 usb_blue_detect.py --once

    # 静态图片检测（无需摄像头）
    python3 usb_blue_detect.py --image test.png

    # 保存检测截图 / 手动指定 HSV 范围
    python3 usb_blue_detect.py --save result.png
    python3 usb_blue_detect.py --h-low 100 --s-low 50 --v-low 50 \
                               --h-high 130 --s-high 255 --v-high 255

    # 指定最小面积（滤噪）
    python3 usb_blue_detect.py --min-area 500

按键: ESC/Q 退出 | S 保存截图 | P 打印当前 HSV 与结果
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from typing import Optional, Tuple

import numpy as np

try:
    import cv2
except ImportError:
    print("[ERROR] OpenCV 未安装，请运行: pip install opencv-python")
    sys.exit(1)

# ============================================================================
# 默认蓝色 HSV 范围  (OpenCV: H∈[0,179], S∈[0,255], V∈[0,255])
# 实测色域 (84,92,40)-(127,255,255)，与 Final1.py P8_BLUE_HSV_* 保持一致
# ============================================================================
DEFAULT_HSV_LOWER: Tuple[int, int, int] = (84, 92, 40)
DEFAULT_HSV_UPPER: Tuple[int, int, int] = (127, 255, 255)

# Phase 8 蓝色驱动前进的判定参数（显示参考线用）
P8_BLUE_RATIO_THRESH = 0.02
P8_BLUE_HSV_LOWER = (84, 92, 40)
P8_BLUE_HSV_UPPER = (127, 255, 255)

# ============================================================================
# 摄像头默认参数（同 3.sh 的调用方式）
# ============================================================================
DEFAULT_WIDTH = 1280        # 3.sh: WIDTH=1280
DEFAULT_HEIGHT = 720        # 3.sh: HEIGHT=720
DEFAULT_FPS = 30            # 3.sh: FPS=30
DEFAULT_BRIGHTNESS = -20    # 3.sh: BRIGHTNESS=-20 (修白屏)
DEFAULT_CONTRAST = 3        # 3.sh: CONTRAST=3
# 蓝色检测取画面底部比例 (0.25=下面1/4, 同 Final1.py P8_BLUE_ROI_BOTTOM_RATIO)
DEFAULT_BLUE_ROI_BOTTOM_RATIO = 0.25


# ============================================================================
# USB 摄像头（按 3.sh 方式调用: v4l2-ctl 找设备 + 设亮度/对比度/曝光）
# ============================================================================
def _find_usb_device() -> Optional[str]:
    """用 v4l2-ctl 查找 USB 摄像头设备（同 3.sh 的判定: 卡名含 USB/Live/Camera）"""
    for idx in (0, 1, 2, 8):
        dev = f"/dev/video{idx}"
        try:
            r = subprocess.run(["v4l2-ctl", "-d", dev, "--all"],
                               capture_output=True, text=True, timeout=3)
            m = re.search(r"Card type\s*:\s*(.+)", r.stdout)
            if m and re.search(r"USB|Live|Camera|CAME", m.group(1), re.I):
                return dev
        except Exception:
            continue
    return None


def _apply_v4l2_controls(dev: str, brightness: int, contrast: int):
    """设曝光/亮度/对比度（同 3.sh 的 v4l2-ctl 调用），失败静默"""
    for ctrl, val in (("exposure_auto", 3),
                      ("brightness", brightness),
                      ("contrast", contrast)):
        try:
            subprocess.run(["v4l2-ctl", "-d", dev, f"--set-ctrl={ctrl}={val}"],
                           capture_output=True, timeout=3)
        except Exception:
            pass


def open_usb_camera(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
                    fps: int = DEFAULT_FPS, brightness: int = DEFAULT_BRIGHTNESS,
                    contrast: int = DEFAULT_CONTRAST) -> cv2.VideoCapture:
    """按 3.sh 的方式调用 USB 摄像头。

    流程: v4l2-ctl 找设备 + 设 exposure_auto=3 / brightness / contrast，
    再用 OpenCV V4L2 打开并配置 MJPG + 分辨率；找不到设备时回退枚举索引。

    Args:
        width/height/fps: 采集分辨率与帧率 (默认 1280x720@30, 同 3.sh)
        brightness/contrast: 摄像头亮度/对比度 (默认 -20/3, 同 3.sh, 修白屏)
    Returns:
        打开的 VideoCapture 对象
    Raises:
        RuntimeError: 打不开摄像头
    """
    dev = _find_usb_device()
    if dev:
        print(f"[CAM] v4l2-ctl 找到 USB 摄像头: {dev}")
        _apply_v4l2_controls(dev, brightness, contrast)
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    else:
        print("[CAM] v4l2-ctl 未识别到设备，回退枚举 /dev/video0,1,2,8")
        cap = None
        for idx in (0, 1, 2, 8):
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                dev = f"/dev/video{idx}"
                print(f"[CAM] 打开 USB 摄像头 {dev}")
                break
        else:
            raise RuntimeError("无法打开 USB 摄像头 "
                               "(尝试了 v4l2-ctl 与 /dev/video0,1,2,8)")

    if not cap.isOpened():
        raise RuntimeError(f"无法打开摄像头 {dev}")

    # 尝试 MJPG，失败则用默认格式
    if not cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')):
        print("[CAM] MJPG 不可用，使用默认像素格式")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    # v4l2-ctl 已设过控制项，OpenCV 侧再镜像一份，双保险
    cap.set(cv2.CAP_PROP_BRIGHTNESS, brightness)
    cap.set(cv2.CAP_PROP_CONTRAST, contrast)
    w_ = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h_ = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAM] 分辨率 {w_}x{h_} @ {fps}fps, "
          f"brightness={brightness} contrast={contrast}")
    return cap


# ============================================================================
# 蓝色检测器
# ============================================================================
class BlueDetector:
    """在 BGR 彩色帧中检测蓝色区域（无深度）"""

    def __init__(self, lower: Tuple[int, int, int] = DEFAULT_HSV_LOWER,
                 upper: Tuple[int, int, int] = DEFAULT_HSV_UPPER,
                 bottom_ratio: float = DEFAULT_BLUE_ROI_BOTTOM_RATIO):
        self.set_hsv_range(lower, upper)
        self.bottom_ratio = bottom_ratio

        # 形态学核（同 color_object_detector.py）
        self._kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self._kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

        self.result: Optional[dict] = None

    # ------------------------------------------------------------------
    def set_hsv_range(self, lower: Tuple[int, int, int],
                      upper: Tuple[int, int, int]):
        """设置蓝色 HSV 范围"""
        self.lower = np.array(lower, dtype=np.uint8)
        self.upper = np.array(upper, dtype=np.uint8)

    # ------------------------------------------------------------------
    def detect(self, bgr: np.ndarray, min_area: int = 200) -> Optional[dict]:
        """
        在 BGR 图像中检测蓝色区域，返回最大蓝色物体的信息。

        Args:
            bgr: BGR 彩色图像 (H×W×3, uint8)
            min_area: 最小轮廓面积 (px²)，滤除噪点
        Returns:
            dict 或 None:
                {
                    "cx": int, "cy": int,        # 最大蓝色区域中心
                    "area": float,               # 面积 (px²)
                    "bbox": (x, y, w, h),        # 外接矩形
                    "contour": np.ndarray,       # 轮廓点
                    "mask": np.ndarray,          # 蓝色二值掩膜 (全图)
                    "blue_ratio_bottom": float,  # 画面下半部分蓝色占比 (0~1)
                }
        """
        h, w = bgr.shape[:2]
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower, self.upper)

        # 形态学去噪：开运算去小噪点 → 闭运算填空洞
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel_open)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel_close)

        # 画面底部 ROI (占比 self.bottom_ratio) 蓝色占比 (Phase 8 蓝色驱动前进用)
        roi_top = h - int(h * self.bottom_ratio)
        bottom = mask[roi_top:, :]
        blue_ratio_bottom = float(cv2.countNonZero(bottom)) / bottom.size

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        valid = [c for c in contours if cv2.contourArea(c) >= min_area]
        if not valid:
            self.result = None
            return None

        largest = max(valid, key=cv2.contourArea)
        area = cv2.contourArea(largest)

        # 计算中心（矩方法）
        M = cv2.moments(largest)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            # 退化为外接矩形中心
            x, y, bw, bh = cv2.boundingRect(largest)
            cx, cy = x + bw // 2, y + bh // 2
        cx = np.clip(cx, 0, w - 1)
        cy = np.clip(cy, 0, h - 1)

        self.result = {
            "cx": cx,
            "cy": cy,
            "area": area,
            "bbox": cv2.boundingRect(largest),
            "contour": largest,
            "mask": mask,
            "blue_ratio_bottom": blue_ratio_bottom,
        }
        return self.result

    # ------------------------------------------------------------------
    def draw(self, image: np.ndarray) -> np.ndarray:
        """在图像上绘制检测结果"""
        if self.result is None:
            # 仍画底部 ROI 分界线，方便观察
            h = image.shape[0]
            roi_top = h - int(h * self.bottom_ratio)
            cv2.line(image, (0, roi_top), (image.shape[1], roi_top),
                     (255, 0, 255), 1)
            return image

        r = self.result
        x, y, bw, bh = r["bbox"]

        # 轮廓框 (绿色)
        cv2.rectangle(image, (x, y), (x + bw, y + bh), (0, 255, 0), 2)

        # 中心十字 (红色)
        cx, cy = r["cx"], r["cy"]
        cv2.line(image, (cx - 15, cy), (cx + 15, cy), (0, 0, 255), 2)
        cv2.line(image, (cx, cy - 15), (cx, cy + 15), (0, 0, 255), 2)
        cv2.circle(image, (cx, cy), 4, (0, 0, 255), -1)

        # 画面底部 ROI 分界线 (紫色虚线, 占比 self.bottom_ratio)
        h = image.shape[0]
        roi_top = h - int(h * self.bottom_ratio)
        for yy in range(roi_top, h, 8):
            cv2.line(image, (0, yy), (image.shape[1], yy), (255, 0, 255), 1)

        # 信息标注（白色背景黑字）
        lines = [
            f"Center: ({cx}, {cy})",
            f"Area: {r['area']:.0f} px",
            f"BottomBlue: {r['blue_ratio_bottom']:.3f} "
            f"(>{P8_BLUE_RATIO_THRESH} "
            f"{'Y' if r['blue_ratio_bottom'] > P8_BLUE_RATIO_THRESH else 'N'})",
        ]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        thickness = 1
        line_h = 22

        text_y0 = y - 10 - len(lines) * line_h
        if text_y0 < 0:
            text_y0 = y + bh + 10

        for i, line in enumerate(lines):
            ty = text_y0 + i * line_h
            (tw, th), _ = cv2.getTextSize(line, font, font_scale, thickness)
            # 半透明背景
            overlay = image.copy()
            cv2.rectangle(overlay,
                          (x - 2, ty - th - 4),
                          (x + tw + 4, ty + 4),
                          (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, image, 0.4, 0, image)
            cv2.putText(image, line, (x, ty),
                        font, font_scale, (255, 255, 255), thickness)

        # 轮廓叠加
        cv2.drawContours(image, [r["contour"]], -1, (255, 255, 0), 1)

        return image

    # ------------------------------------------------------------------
    def draw_mask_preview(self, mask: np.ndarray) -> np.ndarray:
        """将二值 mask 转为三通道预览图"""
        return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)


# ============================================================================
# 实时预览 + Trackbar 调参
# ============================================================================

def _nothing(_):
    pass


def live_detect(cap: cv2.VideoCapture, detector: BlueDetector):
    """实时预览 + HSV Trackbar 调参"""
    WIN_MAIN = "USB Blue Detector"
    WIN_MASK = "Blue Mask"
    WIN_TRACK = "HSV Trackbar"

    cv2.namedWindow(WIN_MAIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_MAIN, 960, 720)
    cv2.namedWindow(WIN_MASK, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_MASK, 480, 360)
    cv2.namedWindow(WIN_TRACK, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_TRACK, 500, 280)

    h_l, s_l, v_l = (int(v) for v in detector.lower)
    h_h, s_h, v_h = (int(v) for v in detector.upper)

    cv2.createTrackbar("H Low", WIN_TRACK, h_l, 179, _nothing)
    cv2.createTrackbar("H High", WIN_TRACK, h_h, 179, _nothing)
    cv2.createTrackbar("S Low", WIN_TRACK, s_l, 255, _nothing)
    cv2.createTrackbar("S High", WIN_TRACK, s_h, 255, _nothing)
    cv2.createTrackbar("V Low", WIN_TRACK, v_l, 255, _nothing)
    cv2.createTrackbar("V High", WIN_TRACK, v_h, 255, _nothing)

    print("[INFO] 实时检测蓝色区域 … 按 ESC/Q 退出 | S=截图 | P=打印当前值")
    print(f"[INFO] 默认 HSV: H[{h_l}-{h_h}] S[{s_l}-{s_h}] V[{v_l}-{v_h}]")
    print(f"[INFO] 下半画面蓝色占比阈值参考: >{P8_BLUE_RATIO_THRESH} "
          f"(Phase 8 蓝色驱动前进触发)")

    while True:
        t0 = time.time()
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        # 读取 trackbar 值并更新检测器
        h_l = cv2.getTrackbarPos("H Low", WIN_TRACK)
        h_h = cv2.getTrackbarPos("H High", WIN_TRACK)
        s_l = cv2.getTrackbarPos("S Low", WIN_TRACK)
        s_h = cv2.getTrackbarPos("S High", WIN_TRACK)
        v_l = cv2.getTrackbarPos("V Low", WIN_TRACK)
        v_h = cv2.getTrackbarPos("V High", WIN_TRACK)
        detector.set_hsv_range((h_l, s_l, v_l), (h_h, s_h, v_h))

        result = detector.detect(frame)

        display = frame.copy()
        if result is not None:
            detector.draw(display)
            mask_preview = detector.draw_mask_preview(result["mask"])
        else:
            detector.draw(display)
            h, w = display.shape[:2]
            mask_preview = np.zeros((h, w, 3), dtype=np.uint8)

        fps = 1.0 / (time.time() - t0) if (time.time() - t0) > 0 else 0
        if result is not None:
            status = (f"Center=({result['cx']},{result['cy']})  "
                      f"Area={result['area']:.0f}px  "
                      f"BottomBlue={result['blue_ratio_bottom']:.3f}")
        else:
            status = "No blue found"
        cv2.putText(display, f"FPS:{fps:.0f}  {status}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                    cv2.LINE_AA)

        cv2.imshow(WIN_MAIN, display)
        cv2.imshow(WIN_MASK, mask_preview)

        key = cv2.waitKey(1) & 0xFF
        if key == 27 or key == ord('q'):
            break
        elif key == ord('s'):
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"blue_snapshot_{ts}.png"
            cv2.imwrite(fname, display)
            print(f"[SAVE] {fname}")
        elif key == ord('p'):
            print("=" * 50)
            print(f"  HSV 范围       : H[{h_l}-{h_h}] S[{s_l}-{s_h}] V[{v_l}-{v_h}]")
            if result:
                print(f"  中心坐标       : ({result['cx']}, {result['cy']})")
                print(f"  面积           : {result['area']:.0f} px²")
                print(f"  外接矩形       : {result['bbox']}")
                print(f"  下半蓝色占比   : {result['blue_ratio_bottom']:.3f} "
                      f"(阈值 >{P8_BLUE_RATIO_THRESH})")
                print(f"  回填 Final1.py : P8_BLUE_HSV_LOWER=({h_l},{s_l},{v_l}) "
                      f"P8_BLUE_HSV_UPPER=({h_h},{s_h},{v_h})")
            else:
                print("  未检测到蓝色区域")
            print("=" * 50)

    cv2.destroyAllWindows()


# ============================================================================
# 静态图片检测（无需摄像头）
# ============================================================================

def detect_image(image_path: str, detector: BlueDetector,
                 save_path: Optional[str] = None):
    """对静态图片运行蓝色检测"""
    img = cv2.imread(image_path)
    if img is None:
        print(f"[ERROR] 无法读取图片: {image_path}")
        return

    result = detector.detect(img)

    print("=" * 50)
    print(f"  检测颜色       : 蓝色")
    print(f"  图片尺寸       : {img.shape[1]} × {img.shape[0]}")
    print(f"  来源           : {image_path}")
    print(f"  HSV 范围       : "
          f"H[{detector.lower[0]}-{detector.upper[0]}] "
          f"S[{detector.lower[1]}-{detector.upper[1]}] "
          f"V[{detector.lower[2]}-{detector.upper[2]}]")

    display = img.copy()
    if result:
        detector.draw(display)
        print(f"  物体中心       : ({result['cx']}, {result['cy']})")
        print(f"  面积           : {result['area']:.0f} px²")
        print(f"  外接矩形       : {result['bbox']}")
        print(f"  下半蓝色占比   : {result['blue_ratio_bottom']:.3f}")
    else:
        cv2.putText(display, "No blue detected", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        print("  [WARN] 未检测到蓝色区域")
    print("=" * 50)

    if save_path:
        cv2.imwrite(save_path, display)
        print(f"[SAVE] 检测结果 → {save_path}")

    try:
        cv2.imshow("Blue Detection (Static Image)", display)
        print("[INFO] 按任意键关闭窗口 …")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except cv2.error:
        print("[INFO] 无 GUI 环境，结果已保存到文件")


# ============================================================================
# 单帧检测（摄像头）
# ============================================================================

def detect_once(cap: cv2.VideoCapture, detector: BlueDetector,
                save_path: Optional[str] = None):
    """单帧检测，终端打印结果，可选保存截图"""
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] 未能获取帧")
        return

    result = detector.detect(frame)

    print("=" * 50)
    print(f"  检测颜色       : 蓝色")
    print(f"  HSV 范围       : "
          f"H[{detector.lower[0]}-{detector.upper[0]}] "
          f"S[{detector.lower[1]}-{detector.upper[1]}] "
          f"V[{detector.lower[2]}-{detector.upper[2]}]")

    display = frame.copy()
    if result:
        detector.draw(display)
        print(f"  物体中心       : ({result['cx']}, {result['cy']})")
        print(f"  面积           : {result['area']:.0f} px²")
        print(f"  外接矩形       : {result['bbox']}")
        print(f"  下半蓝色占比   : {result['blue_ratio_bottom']:.3f} "
              f"(阈值 >{P8_BLUE_RATIO_THRESH})")
    else:
        cv2.putText(display, "No blue detected", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        print("  [WARN] 未检测到蓝色区域")
    print("=" * 50)

    if save_path:
        cv2.imwrite(save_path, display)
        print(f"[SAVE] 检测结果 → {save_path}")

    try:
        cv2.imshow("Blue Detection", display)
        print("[INFO] 按任意键关闭窗口 …")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except cv2.error:
        print("[INFO] 无 GUI 环境，结果已保存到文件")


# ============================================================================
# 命令行入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="USB 摄像头蓝色区域检测 + HSV 调参")
    parser.add_argument("--h-low", type=int, default=DEFAULT_HSV_LOWER[0])
    parser.add_argument("--s-low", type=int, default=DEFAULT_HSV_LOWER[1])
    parser.add_argument("--v-low", type=int, default=DEFAULT_HSV_LOWER[2])
    parser.add_argument("--h-high", type=int, default=DEFAULT_HSV_UPPER[0])
    parser.add_argument("--s-high", type=int, default=DEFAULT_HSV_UPPER[1])
    parser.add_argument("--v-high", type=int, default=DEFAULT_HSV_UPPER[2])
    parser.add_argument("--once", action="store_true",
                        help="单帧检测模式，打印结果后退出")
    parser.add_argument("--save", type=str, default=None,
                        help="保存检测结果截图路径 (.png)")
    parser.add_argument("--min-area", type=int, default=200,
                        help="最小轮廓面积，滤除噪点 (默认: 200 px²)")
    parser.add_argument("--bottom-ratio", type=float,
                        default=DEFAULT_BLUE_ROI_BOTTOM_RATIO,
                        help="蓝色检测取画面底部比例 (默认: 0.25=下面1/4)")
    parser.add_argument("--image", type=str, default=None,
                        help="检测静态图片中的蓝色（无需摄像头）")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--brightness", type=int, default=DEFAULT_BRIGHTNESS,
                        help="摄像头亮度 (默认 -20, 同 3.sh 修白屏)")
    parser.add_argument("--contrast", type=int, default=DEFAULT_CONTRAST,
                        help="摄像头对比度 (默认 3, 同 3.sh)")
    args = parser.parse_args()

    detector = BlueDetector(
        lower=(args.h_low, args.s_low, args.v_low),
        upper=(args.h_high, args.s_high, args.v_high),
        bottom_ratio=args.bottom_ratio,
    )

    # ---- 静态图片模式（无需摄像头） ----
    if args.image:
        detect_image(args.image, detector, save_path=args.save)
        return

    # ---- 摄像头模式 ----
    try:
        cap = open_usb_camera(width=args.width, height=args.height,
                              fps=args.fps,
                              brightness=args.brightness,
                              contrast=args.contrast)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    try:
        if args.once:
            detect_once(cap, detector, save_path=args.save)
        else:
            live_detect(cap, detector)
    finally:
        cap.release()


if __name__ == "__main__":
    main()
