#!/usr/bin/env python3
"""
Intel RealSense D435i 深度摄像头调用模块
===========================================
单帧采集 / 实时预览 / 深度数据导出 / 点云生成

用法:
    # 实时预览（彩色 + 深度叠加）
    python3 depth_camera.py

    # 单帧采集，打印中心区域深度值
    python3 depth_camera.py --once

    # 保存深度图到文件
    python3 depth_camera.py --save depth.npy --once

    # 作为模块导入
    from depth_camera import DepthCamera
    cam = DepthCamera()
    depth_frame, color_frame = cam.get_frames()
    center_depth_mm = cam.get_distance_at(320, 240)
    cam.close()
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import numpy as np

try:
    import pyrealsense2 as rs
except ImportError:
    print("[ERROR] pyrealsense2 未安装，请运行: pip install pyrealsense2")
    sys.exit(1)

try:
    import cv2
except ImportError:
    cv2 = None
    print("[WARN] OpenCV 未安装，无 GUI 模式运行")


# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------
DEFAULT_WIDTH  = 640
DEFAULT_HEIGHT = 480
DEFAULT_FPS    = 30


# ---------------------------------------------------------------------------
# DepthCamera 类
# ---------------------------------------------------------------------------
class DepthCamera:
    """RealSense D435i 深度摄像头高层封装"""

    def __init__(self,
                 width: int  = DEFAULT_WIDTH,
                 height: int = DEFAULT_HEIGHT,
                 fps: int    = DEFAULT_FPS,
                 enable_color: bool = True,
                 enable_imu: bool   = False):
        """
        参数:
            width, height : 分辨率
            fps           : 帧率 (6/15/30/60/90)
            enable_color  : 是否启用 RGB 彩色流
            enable_imu    : 是否启用 IMU （加速度计 + 陀螺仪）
        """
        self.width        = width
        self.height       = height
        self.fps          = fps
        self.enable_color = enable_color
        self.enable_imu   = enable_imu

        # ---- 管线 ----
        self.pipe    = rs.pipeline()
        self.config  = rs.config()
        self.profile = None
        self.align   = None                       # 深度→彩色对齐器（延迟创建）
        self._started = False

        # ---- 传感器对象（IMU 回调用） ----
        self._imu_accel  = None
        self._imu_gyro   = None

        self._configure()

    # ------------------------------------------------------------------
    def _configure(self):
        """配置流"""
        # 深度流
        self.config.enable_stream(
            rs.stream.depth,
            self.width, self.height,
            rs.format.z16,
            self.fps,
        )

        # 彩色流
        if self.enable_color:
            self.config.enable_stream(
                rs.stream.color,
                self.width, self.height,
                rs.format.bgr8,
                self.fps,
            )

        # IMU
        if self.enable_imu:
            self.config.enable_stream(rs.stream.accel, rs.format.motion_xyz32f, 200)
            self.config.enable_stream(rs.stream.gyro,  rs.format.motion_xyz32f, 200)

    # ------------------------------------------------------------------
    def start(self, warmup_frames: int = 15):
        """启动管线，若相机状态异常则尝试硬件复位后重试"""
        if self._started:
            return

        for attempt in range(2):
            try:
                self._start_pipeline()
                self._warmup(warmup_frames)
                return
            except RuntimeError as e:
                if attempt == 0:
                    print(f"[CAM] 相机启动失败 ({e})，尝试硬件复位...")
                    self._hardware_reset_and_wait()
                else:
                    raise RuntimeError(
                        f"相机启动失败，硬件复位后仍然无法获取帧: {e}"
                    ) from e

    def _start_pipeline(self):
        """初始化管线、传感器和对齐器"""
        self.profile = self.pipe.start(self.config)

        # 激光投影仪开
        sensor = self.profile.get_device().query_sensors()[0]
        if sensor.supports(rs.option.emitter_enabled):
            sensor.set_option(rs.option.emitter_enabled, 1)

        # 对齐器：深度 → 彩色
        if self.enable_color:
            self.align = rs.align(rs.stream.color)

        # IMU 回调
        if self.enable_imu:
            self._setup_imu_callback()

        self._started = True

    def _warmup(self, num_frames: int):
        """预热：等待自动曝光稳定"""
        for i in range(num_frames):
            self.pipe.wait_for_frames(timeout_ms=5000)

    def _hardware_reset_and_wait(self):
        """硬件复位相机并等待重新枚举"""
        if self._started:
            self.pipe.stop()
            self._started = False

        ctx = rs.context()
        devices = ctx.query_devices()
        if len(devices) > 0:
            devices[0].hardware_reset()
        else:
            print("[CAM] 警告: 未检测到设备，跳过硬件复位")

        # 等待 USB 重新枚举
        import time as _time
        for _ in range(20):
            _time.sleep(0.5)
            if len(ctx.query_devices()) > 0:
                break

        # 重建管线对象（旧 pipeline 在 reset 后失效）
        self.pipe = rs.pipeline()
        self.config = rs.config()
        self._configure()
        self.align = None
        self._started = False

    # ------------------------------------------------------------------
    def _setup_imu_callback(self):
        """注册 IMU 数据回调"""
        def accel_cb(frame):
            self._imu_accel = frame.as_motion_frame().get_motion_data()

        def gyro_cb(frame):
            self._imu_gyro = frame.as_motion_frame().get_motion_data()

        self.profile.get_device().sensors[1].open(
            self.profile.get_device().sensors[1].get_stream_profiles()[0])
        self.profile.get_device().sensors[1].start(accel_cb)

        self.profile.get_device().sensors[2].open(
            self.profile.get_device().sensors[2].get_stream_profiles()[0])
        self.profile.get_device().sensors[2].start(gyro_cb)

    # ------------------------------------------------------------------
    def get_frames(self, aligned: bool = True):
        """
        获取一帧（阻塞直到帧就绪）
        返回: (depth_frame, color_frame | None)
          - depth_frame : rs.depth_frame 对象
          - color_frame : rs.video_frame 对象 （若 enable_color=False 则为 None）
        """
        if not self._started:
            self.start()

        frames = self.pipe.wait_for_frames(timeout_ms=5000)

        if self.enable_color and aligned and self.align is not None:
            frames = self.align.process(frames)

        depth = frames.get_depth_frame()
        color = frames.get_color_frame() if self.enable_color else None
        return depth, color

    # ------------------------------------------------------------------
    def get_depth_image(self, aligned: bool = True) -> np.ndarray:
        """返回深度帧的 numpy 数组 (uint16, mm)"""
        depth_frame, _ = self.get_frames(aligned=aligned)
        return np.asanyarray(depth_frame.get_data())

    # ------------------------------------------------------------------
    def get_color_image(self, aligned: bool = True) -> Optional[np.ndarray]:
        """返回彩色帧的 numpy 数组 (uint8, BGR)"""
        _, color_frame = self.get_frames(aligned=aligned)
        if color_frame is None:
            return None
        return np.asanyarray(color_frame.get_data())

    # ------------------------------------------------------------------
    def get_distance_at(self, x: int, y: int) -> float:
        """
        获取 (x, y) 像素处的距离（毫米）
        无效 / 超出量程返回 0.0
        """
        depth_frame, _ = self.get_frames()
        return depth_frame.get_distance(x, y) * 1000.0   # m → mm

    # ------------------------------------------------------------------
    def get_center_distance(self) -> float:
        """获取画面中心的距离（毫米）"""
        return self.get_distance_at(self.width // 2, self.height // 2)

    # ------------------------------------------------------------------
    def get_imu(self):
        """返回最新 IMU 读数 (accel, gyro)，若无数据则返回 None"""
        return self._imu_accel, self._imu_gyro

    # ------------------------------------------------------------------
    def get_depth_scale(self) -> float:
        """返回深度缩放因子（将 uint16 像素值转为米）"""
        if not self._started:
            self.start()
        sensor = self.profile.get_device().query_sensors()[0]
        return sensor.get_option(rs.option.depth_units)

    # ------------------------------------------------------------------
    def get_intrinsics(self):
        """返回深度和彩色流内参矩阵"""
        if not self._started:
            self.start()
        profile = self.pipe.get_active_profile()
        depth_intr = profile.get_stream(
            rs.stream.depth).as_video_stream_profile().get_intrinsics()
        color_intr = None
        if self.enable_color:
            color_intr = profile.get_stream(
                rs.stream.color).as_video_stream_profile().get_intrinsics()
        return depth_intr, color_intr

    # ------------------------------------------------------------------
    def deproject(self, x: int, y: int, distance_mm: Optional[float] = None):
        """
        2D 像素 → 3D 空间点 (相机坐标系，米)
        返回: (x_m, y_m, z_m)
        """
        depth_intr, _ = self.get_intrinsics()
        if distance_mm is None:
            distance_mm = self.get_distance_at(x, y)
        z = distance_mm / 1000.0
        point = rs.rs2_deproject_pixel_to_point(depth_intr, [x, y], z)
        return tuple(point)   # (x, y, z) meters

    # ------------------------------------------------------------------
    def close(self):
        """停止管线并释放资源"""
        if self._started:
            self.pipe.stop()
            self._started = False

    # ------------------------------------------------------------------
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()


# ===================================================================
# 可视化工具
# ===================================================================

def colorize_depth(depth_image: np.ndarray,
                   min_mm: int = 300,
                   max_mm: int = 4000) -> np.ndarray:
    """
    将 uint16 深度图转为伪彩色 BGR 图像（Jet colormap）
    depth_image: uint16, 单位 mm
    """
    clipped = np.clip(depth_image.astype(np.float32), min_mm, max_mm)
    normalized = ((clipped - min_mm) / (max_mm - min_mm) * 255).astype(np.uint8)
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
    # 无效像素（0）变黑
    colored[depth_image == 0] = (0, 0, 0)
    return colored


def draw_depth_overlay(color_image: np.ndarray,
                       depth_image: np.ndarray,
                       alpha: float = 0.4) -> np.ndarray:
    """将伪彩色深度叠加到彩色图上"""
    if color_image is None:
        return colorize_depth(depth_image)
    depth_color = colorize_depth(depth_image)
    return cv2.addWeighted(color_image, 1 - alpha, depth_color, alpha, 0)


def draw_center_crosshair(image: np.ndarray,
                          depth_mm: float,
                          color: tuple = (0, 255, 0)) -> np.ndarray:
    """在图像中心画十字线并标注距离"""
    h, w = image.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.line(image, (cx - 20, cy), (cx + 20, cy), color, 2)
    cv2.line(image, (cx, cy - 20), (cx, cy + 20), color, 2)
    text = f"{depth_mm:.0f} mm"
    cv2.putText(image, text, (cx - 40, cy - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    return image


# ===================================================================
# 交互预览
# ===================================================================

def live_preview(cam: DepthCamera):
    """实时预览窗口，按 ESC/Q 退出"""
    if cv2 is None:
        print("[ERROR] 实时预览需要 OpenCV")
        return

    WIN = "Depth Camera — D435i"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 1280, 480)

    show_color   = cam.enable_color
    show_overlay = True          # 深度叠加

    print("[INFO] 实时预览中 … 按 ESC/Q 退出 | O=切换叠加 | C=切换彩色 | S=截图")
    frame_count = 0

    while True:
        t0 = time.time()
        depth_frame, color_frame = cam.get_frames(aligned=True)

        if not depth_frame:
            continue

        depth_img  = np.asanyarray(depth_frame.get_data())
        color_img  = np.asanyarray(color_frame.get_data()) if color_frame is not None else None

        # 中心距离
        cx, cy = cam.width // 2, cam.height // 2
        dist_mm = depth_frame.get_distance(cx, cy) * 1000.0

        # 渲染
        if show_color and color_img is not None and show_overlay:
            display = draw_depth_overlay(color_img, depth_img)
        elif show_color and color_img is not None:
            display = color_img.copy()
        else:
            display = colorize_depth(depth_img)

        draw_center_crosshair(display, dist_mm)

        # FPS
        elapsed = time.time() - t0
        fps_str = f"FPS: {1/elapsed:.1f}" if elapsed > 0 else "FPS: --"
        cv2.putText(display, fps_str, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow(WIN, display)
        key = cv2.waitKey(1) & 0xFF

        if key == 27 or key == ord('q'):       # ESC / Q
            break
        elif key == ord('o'):
            show_overlay = not show_overlay
        elif key == ord('c'):
            show_color = not show_color
        elif key == ord('s'):
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"depth_snapshot_{ts}.png"
            cv2.imwrite(fname, display)
            print(f"[SAVE] {fname}")

        frame_count += 1

    cv2.destroyAllWindows()


# ===================================================================
# 单帧采集
# ===================================================================

def capture_once(cam: DepthCamera, save_path: Optional[str] = None):
    """采集一帧并打印/保存"""
    depth_frame, color_frame = cam.get_frames(aligned=True)

    if not depth_frame:
        print("[ERROR] 未能获取深度帧")
        return

    depth_img = np.asanyarray(depth_frame.get_data())

    # 中心距离
    cx, cy = cam.width // 2, cam.height // 2
    dist_mm = depth_frame.get_distance(cx, cy) * 1000.0

    # 统计
    valid = depth_img[depth_img > 0]
    print("=" * 50)
    print(f"  分辨率        : {cam.width} × {cam.height}")
    print(f"  中心距离       : {dist_mm:.0f} mm")
    print(f"  深度范围       : {valid.min():.0f} – {valid.max():.0f} mm")
    print(f"  有效像素占比   : {len(valid) / depth_img.size * 100:.1f} %")
    print(f"  深度缩放因子   : {cam.get_depth_scale():.6f} m/unit")
    print("=" * 50)

    if save_path:
        if save_path.endswith('.npy'):
            np.save(save_path, depth_img)
            print(f"[SAVE] 深度数据 → {save_path}")
        elif save_path.endswith(('.png', '.jpg', '.bmp')):
            colored = colorize_depth(depth_img)
            cv2.imwrite(save_path, colored)
            print(f"[SAVE] 伪彩色深度图 → {save_path}")
        else:
            np.save(save_path + '.npy', depth_img)
            print(f"[SAVE] 深度数据 → {save_path}.npy")


# ===================================================================
# 命令行入口
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Intel RealSense D435i 深度摄像头工具")
    parser.add_argument("--once", action="store_true",
                        help="仅采集一帧并退出")
    parser.add_argument("--save", type=str, default=None,
                        help="保存路径 (.npy / .png)")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--no-color", action="store_true",
                        help="仅深度流，关闭彩色")
    parser.add_argument("--imu", action="store_true",
                        help="启用 IMU 流")
    args = parser.parse_args()

    cam = DepthCamera(
        width=args.width,
        height=args.height,
        fps=args.fps,
        enable_color=not args.no_color,
        enable_imu=args.imu,
    )
    cam.start()

    try:
        if args.once:
            capture_once(cam, args.save)
        else:
            live_preview(cam)
    finally:
        cam.close()


if __name__ == "__main__":
    main()
