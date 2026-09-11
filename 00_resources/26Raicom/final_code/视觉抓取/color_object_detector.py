#!/usr/bin/env python3
"""
颜色物体检测 + 深度测距
========================
检测画面中特定颜色的物体，输出：
  - 物体中心坐标 (x, y)
  - 物体距离 (mm)
  - 物体面积 (px²)

用法:
    # 实时预览（检测绿色物体 + Trackbar 调参）
    python3 color_object_detector.py

    # 检测其他颜色
    python3 color_object_detector.py --color red
    python3 color_object_detector.py --color blue
    python3 color_object_detector.py --color yellow

    # 单帧检测（打印结果到终端）
    python3 color_object_detector.py --once --color green

    # 保存检测结果截图
    python3 color_object_detector.py --once --color green --save result.png
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional, Tuple

import numpy as np

try:
    import pyrealsense2 as rs
except ImportError:
    print("[ERROR] pyrealsense2 未安装，请运行: pip install pyrealsense2")
    sys.exit(1)

try:
    import cv2
except ImportError:
    print("[ERROR] OpenCV 未安装，请运行: pip install opencv-python")
    sys.exit(1)

# 复用现有摄像头封装
from depth_camera import DepthCamera

# ============================================================================
# 预设颜色 HSV 范围  (OpenCV: H∈[0,179], S∈[0,255], V∈[0,255])
# ============================================================================
COLOR_PRESETS: dict = {
    "red": {
        "name": "红色",
        # 红色在 HSV 中跨越 0°，需要两段合并
        "ranges": [
            {"lower": (0, 100, 100), "upper": (10, 255, 255)},
            {"lower": (160, 100, 100), "upper": (179, 255, 255)},
        ],
    },
    "green": {
        "name": "绿色",
        "ranges": [
            {"lower": (72, 64, 46), "upper": (98, 255, 255)},
        ],
    },
    "blue": {
        "name": "蓝色",
        "ranges": [
            {"lower": (100, 50, 50), "upper": (130, 255, 255)},
        ],
    },
    "yellow": {
        "name": "黄色",
        "ranges": [
            {"lower": (20, 100, 100), "upper": (35, 255, 255)},
        ],
    },
}


# ============================================================================
# 颜色检测器
# ============================================================================
class ColorObjectDetector:
    """在彩色帧中检测特定颜色物体，结合深度帧获取距离"""

    def __init__(self, color_name: str = "green"):
        """
        参数:
            color_name: 颜色名 ("red", "green", "blue", "yellow")
        """
        self.set_color(color_name)

        # 形态学核
        self._kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self._kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

        # 当前检测结果
        self.result: Optional[dict] = None

    # ------------------------------------------------------------------
    def set_color(self, color_name: str):
        """切换检测颜色"""
        preset = COLOR_PRESETS.get(color_name)
        if preset is None:
            raise ValueError(f"不支持的颜色: {color_name}，可选: {list(COLOR_PRESETS.keys())}")
        self.color_name = color_name
        self.color_label = preset["name"]
        self._ranges = preset["ranges"]

    # ------------------------------------------------------------------
    def set_hsv_range(self, lower: Tuple[int, int, int],
                      upper: Tuple[int, int, int]):
        """手动设置单段 HSV 范围（配合 Trackbar 使用）"""
        self._ranges = [{"lower": lower, "upper": upper}]

    # ------------------------------------------------------------------
    def detect(self, color_bgr: np.ndarray, depth_frame,
               min_area: int = 200) -> Optional[dict]:
        """
        在 BGR 图像中检测目标颜色物体，返回最大物体的信息

        参数:
            color_bgr : BGR 彩色图像 (H×W×3, uint8)
            depth_frame : RealSense 深度帧对象
            min_area : 最小轮廓面积 (px²)，滤除噪点

        返回:
            dict 或 None:
                {
                    "cx": int,        # 中心 x (像素)
                    "cy": int,        # 中心 y (像素)
                    "distance_mm": float,  # 距离 (毫米)，无效为 0.0
                    "area": float,    # 轮廓面积 (px²)
                    "bbox": (x, y, w, h),  # 外接矩形
                    "contour": np.ndarray, # 轮廓点
                }
        """
        h, w = color_bgr.shape[:2]
        hsv = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2HSV)

        # 多段 mask 合并（支持红色跨 0°）
        mask = np.zeros((h, w), dtype=np.uint8)
        for r in self._ranges:
            lower = np.array(r["lower"], dtype=np.uint8)
            upper = np.array(r["upper"], dtype=np.uint8)
            mask |= cv2.inRange(hsv, lower, upper)

        # 形态学去噪：开运算去小噪点 → 闭运算填空洞
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel_open)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel_close)

        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            self.result = None
            return None

        # 面积过滤 + 取最大
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

        # 边界检查
        cx = np.clip(cx, 0, w - 1)
        cy = np.clip(cy, 0, h - 1)

        # 查询深度
        dist_m = depth_frame.get_distance(cx, cy)
        distance_mm = dist_m * 1000.0

        bbox = cv2.boundingRect(largest)

        self.result = {
            "cx": cx,
            "cy": cy,
            "distance_mm": distance_mm,
            "area": area,
            "bbox": bbox,
            "contour": largest,
            "mask": mask,
        }
        return self.result

    # ------------------------------------------------------------------
    def draw(self, image: np.ndarray) -> np.ndarray:
        """在图像上绘制检测结果"""
        if self.result is None:
            return image

        r = self.result
        x, y, bw, bh = r["bbox"]

        # 轮廓框 (绿色)
        cv2.rectangle(image, (x, y), (x + bw, y + bh), (0, 255, 0), 2)

        # 中心十字 (红色)
        cx, cy = r["cx"], r["cy"]
        cross_size = 15
        cv2.line(image, (cx - cross_size, cy), (cx + cross_size, cy),
                 (0, 0, 255), 2)
        cv2.line(image, (cx, cy - cross_size), (cx, cy + cross_size),
                 (0, 0, 255), 2)
        cv2.circle(image, (cx, cy), 4, (0, 0, 255), -1)

        # 信息标注 (白色背景黑字)
        lines = [
            f"Color: {self.color_label}",
            f"Pos: ({cx}, {cy})",
            f"Dist: {r['distance_mm']:.0f} mm",
            f"Area: {r['area']:.0f} px",
        ]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        thickness = 1
        line_h = 22

        # 文字区域放在物体上方，如果空间不够则放下方
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
# 实时预览
# ============================================================================

# Trackbar 回调（什么都不做，只用于 createTrackbar 的签名要求）
def _nothing(_):
    pass


def live_detect(cam: DepthCamera, detector: ColorObjectDetector):
    """实时预览 + HSV Trackbar 调参"""
    WIN_MAIN = "Color Object Detector"
    WIN_MASK = "Mask"
    WIN_TRACK = "HSV Trackbar"

    cv2.namedWindow(WIN_MAIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_MAIN, 960, 720)
    cv2.namedWindow(WIN_MASK, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_MASK, 480, 360)
    cv2.namedWindow(WIN_TRACK, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_TRACK, 500, 280)

    # 用第一段 range 初始化 trackbar
    init_range = detector._ranges[0]
    h_low, s_low, v_low = init_range["lower"]
    h_high, s_high, v_high = init_range["upper"]

    cv2.createTrackbar("H Low", WIN_TRACK, h_low, 179, _nothing)
    cv2.createTrackbar("H High", WIN_TRACK, h_high, 179, _nothing)
    cv2.createTrackbar("S Low", WIN_TRACK, s_low, 255, _nothing)
    cv2.createTrackbar("S High", WIN_TRACK, s_high, 255, _nothing)
    cv2.createTrackbar("V Low", WIN_TRACK, v_low, 255, _nothing)
    cv2.createTrackbar("V High", WIN_TRACK, v_high, 255, _nothing)

    print("[INFO] 实时检测中 … 按 ESC/Q 退出 | S=截图 | P=打印当前值")
    print(f"[INFO] 当前检测颜色: {detector.color_label}")

    while True:
        t0 = time.time()

        # 读取 trackbar 值
        h_l = cv2.getTrackbarPos("H Low", WIN_TRACK)
        h_h = cv2.getTrackbarPos("H High", WIN_TRACK)
        s_l = cv2.getTrackbarPos("S Low", WIN_TRACK)
        s_h = cv2.getTrackbarPos("S High", WIN_TRACK)
        v_l = cv2.getTrackbarPos("V Low", WIN_TRACK)
        v_h = cv2.getTrackbarPos("V High", WIN_TRACK)

        detector.set_hsv_range((h_l, s_l, v_l), (h_h, s_h, v_h))

        # 获取帧
        depth_frame, color_frame = cam.get_frames(aligned=True)
        if not depth_frame or color_frame is None:
            continue

        color_img = np.asanyarray(color_frame.get_data())

        # 检测
        result = detector.detect(color_img, depth_frame)

        # 绘制
        display = color_img.copy()
        if result is not None:
            detector.draw(display)
            mask_preview = detector.draw_mask_preview(result["mask"])
        else:
            mask_preview = np.zeros((cam.height, cam.width, 3), dtype=np.uint8)

        # 顶部状态栏
        fps = 1.0 / (time.time() - t0) if (time.time() - t0) > 0 else 0
        status = f"Target: {detector.color_label}"
        if result:
            status += (f"  |  Pos=({result['cx']},{result['cy']})"
                       f"  Dist={result['distance_mm']:.0f}mm"
                       f"  Area={result['area']:.0f}px²")
        else:
            status += "  |  No target found"
        cv2.putText(display, f"FPS:{fps:.0f} {status}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                    cv2.LINE_AA)

        cv2.imshow(WIN_MAIN, display)
        cv2.imshow(WIN_MASK, mask_preview)

        key = cv2.waitKey(1) & 0xFF
        if key == 27 or key == ord('q'):
            break
        elif key == ord('s'):
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"detect_snapshot_{ts}.png"
            cv2.imwrite(fname, display)
            print(f"[SAVE] {fname}")
        elif key == ord('p'):
            if result:
                print("=" * 50)
                print(f"  颜色          : {detector.color_label}")
                print(f"  中心坐标       : ({result['cx']}, {result['cy']})")
                print(f"  距离           : {result['distance_mm']:.0f} mm")
                print(f"  面积           : {result['area']:.0f} px²")
                print(f"  HSV 范围       : H[{h_l}-{h_h}] S[{s_l}-{s_h}] V[{v_l}-{v_h}]")
                print("=" * 50)
            else:
                print("[INFO] 未检测到目标物体")

    cv2.destroyAllWindows()


# ============================================================================
# 静态图片检测（无需摄像头）
# ============================================================================

def detect_image(image_path: str, detector: ColorObjectDetector,
                 save_path: Optional[str] = None):
    """
    对静态图片运行颜色检测（无深度数据）

    注意: 保存的截图是可视化渲染图 (彩色+深度叠加+十字线)，
    不包含原始深度数据，因此距离显示为 N/A。
    完整检测请连接 D435i 摄像头使用 --once 模式。
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"[ERROR] 无法读取图片: {image_path}")
        return

    print("=" * 50)
    print(f"  检测颜色       : {detector.color_label}")
    print(f"  图片尺寸       : {img.shape[1]} × {img.shape[0]}")
    print(f"  来源           : {image_path}")
    print("  [WARN] 静态图片不含深度数据，距离无法获取")
    print("=" * 50)

    # 创建一个假的深度帧对象 — 我们只需要它的 get_distance 返回固定值
    # 这里不用 depth_frame，detector.detect 需要它但只用于 get_distance
    # 我们 hack: 传入 None，然 detect() 里会调用 get_distance 时报错
    # 更好的做法: 修改 detect 函数，允许 depth_frame=None
    # 这里用简单方案: 对静态图直接跑 opencv 检测部分

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, w = img.shape[:2]

    mask = np.zeros((h, w), dtype=np.uint8)
    for r in detector._ranges:
        lower = np.array(r["lower"], dtype=np.uint8)
        upper = np.array(r["upper"], dtype=np.uint8)
        mask |= cv2.inRange(hsv, lower, upper)

    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, detector._kernel_open)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, detector._kernel_close)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    min_area = 200
    valid = [c for c in contours if cv2.contourArea(c) >= min_area]

    if not valid:
        display = img.copy()
        cv2.putText(display, "No target detected", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        print("  [WARN] 未检测到目标物体")
        print("=" * 50)
    else:
        largest = max(valid, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        M = cv2.moments(largest)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            x, y, bw, bh = cv2.boundingRect(largest)
            cx, cy = x + bw // 2, y + bh // 2
        bbox = cv2.boundingRect(largest)

        # 手动填充 result 供 draw() 使用
        detector.result = {
            "cx": cx, "cy": cy,
            "distance_mm": 0.0,  # 无深度数据
            "area": area, "bbox": bbox,
            "contour": largest, "mask": mask,
        }

        display = img.copy()
        detector.draw(display)
        # 覆盖距离标注为 N/A
        x, y, bw, bh = bbox
        cv2.putText(display, "Dist: N/A (no depth)", (x, y - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        print(f"  物体中心       : ({cx}, {cy})")
        print(f"  面积           : {area:.0f} px²")
        print(f"  外接矩形       : {bbox}")
        print(f"  距离           : N/A (静态图片无深度数据)")
        print("=" * 50)

    if save_path:
        cv2.imwrite(save_path, display)
        print(f"[SAVE] 检测结果 → {save_path}")

    # 有显示器时弹窗，无显示器时仅保存
    try:
        cv2.imshow("Detection Result (Static Image)", display)
        print("[INFO] 按任意键关闭窗口 …")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except cv2.error:
        print("[INFO] 无 GUI 环境，结果已保存到文件")


# ============================================================================
# 单帧检测（摄像头）
# ============================================================================

def detect_once(cam: DepthCamera, detector: ColorObjectDetector,
                save_path: Optional[str] = None):
    """单帧检测，终端打印结果，可选保存截图"""
    depth_frame, color_frame = cam.get_frames(aligned=True)
    if not depth_frame or color_frame is None:
        print("[ERROR] 未能获取帧")
        return

    color_img = np.asanyarray(color_frame.get_data())
    result = detector.detect(color_img, depth_frame)

    print("=" * 50)
    print(f"  检测颜色       : {detector.color_label}")
    print(f"  分辨率         : {cam.width} × {cam.height}")

    if result:
        display = color_img.copy()
        detector.draw(display)
        print(f"  物体中心       : ({result['cx']}, {result['cy']})")
        print(f"  距离           : {result['distance_mm']:.0f} mm")
        print(f"  面积           : {result['area']:.0f} px²")
        print(f"  外接矩形       : {result['bbox']}")
    else:
        display = color_img.copy()
        cv2.putText(display, "No target detected", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        print("  [WARN] 未检测到目标物体")
    print("=" * 50)

    if save_path:
        cv2.imwrite(save_path, display)
        print(f"[SAVE] 检测结果 → {save_path}")

    # 有显示器时弹窗，无显示器时仅保存
    try:
        cv2.imshow("Detection Result", display)
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
        description="颜色物体检测 + 深度测距 (RealSense D435i)")
    parser.add_argument("--color", type=str, default="green",
                        choices=["red", "green", "blue", "yellow"],
                        help="目标颜色 (默认: green)")
    parser.add_argument("--once", action="store_true",
                        help="单帧检测模式，打印结果后退出")
    parser.add_argument("--save", type=str, default=None,
                        help="保存检测结果截图路径 (.png)")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--min-area", type=int, default=200,
                        help="最小轮廓面积，滤除噪点 (默认: 200 px²)")
    parser.add_argument("--image", type=str, default=None,
                        help="检测静态图片中的颜色物体（无需摄像头，无深度数据）")
    args = parser.parse_args()

    # 初始化检测器
    detector = ColorObjectDetector(color_name=args.color)

    # ---- 静态图片模式（无需摄像头） ----
    if args.image:
        detect_image(args.image, detector, save_path=args.save)
        return

    # ---- 摄像头模式 ----
    cam = DepthCamera(
        width=args.width,
        height=args.height,
        fps=args.fps,
        enable_color=True,
    )
    cam.start()

    try:
        if args.once:
            detect_once(cam, detector, save_path=args.save)
        else:
            live_detect(cam, detector)
    finally:
        cam.close()


if __name__ == "__main__":
    main()
