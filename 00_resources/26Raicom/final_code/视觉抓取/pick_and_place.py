#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拾取放置系统: 颜色检测 + D1 机械臂 IK 控制
==========================================
通过 RealSense 相机检测颜色物体, 分阶段控制 D1 机械臂抓取物块。

策略 (2段伸出):
  1. 机械臂归零 (0, 0, 0)
  2. 检测物块, 底座旋转 (X轴) 对中画面
  3. 对中后测距, 计算目标 Y = 深度距离(cm) - 4.5cm 偏移
     (距离 <15cm 或 >30cm 时回到初始位置重新检测)
  4. 第1段: 伸出 1/2 距离, Z=-2, 重新对中 (物块丢失3帧则降Z)
  5. 第2段: 全伸出, Z=-2, 重新对中 (同上3帧降Z逻辑)
  6. Z=-10 抓取 → Z=0 抬起 → XYZ 归零
  7. 切换到夹住走姿态, 带物行走

底座角度 (J0) 策略:
  伸出/升降/抓取阶段锁定当前底座角度 (lock_j0), 目标沿该方位的径向延伸,
  机械臂伸长时底座不再漂移; 只有居中/对中 (X 调整) 阶段才允许转动底座。

坐标系约定 (用户测试验证):
  X: 负值 = 画面左转, 正值 = 画面右转 (底座旋转)
  Y: 负值 = 伸出,     正值 = 回收 (前向延伸)
  Z: 负值 = 下降,     正值 = 上升

用法:
    python3 pick_and_place.py eth0                        # 检测绿色, 自动抓取
    python3 pick_and_place.py eth0 --color red            # 检测红色
    python3 pick_and_place.py eth0 --color blue --once    # 单次抓取后退出
    python3 pick_and_place.py eth0 --dry-run              # 离线测试 (不连机械臂)
    python3 pick_and_place.py eth0 --show-window          # 显示摄像头预览窗口
"""

from __future__ import annotations

import argparse
import sys
import os
import time
import signal
from typing import Optional

import numpy as np

# 添加当前目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from depth_camera import DepthCamera
from color_object_detector import ColorObjectDetector

# 尝试导入 OpenCV (用于显示)
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# 尝试导入机械臂控制模块
try:
    from arm_ik_control import ArmIKController, IKController, REF_JOINT_ANGLES
    HAS_ARM = True
except ImportError:
    HAS_ARM = False
    REF_JOINT_ANGLES = [-90.0, 10.0, 55.0, 0.0, -61.0, 0.0, 60.0]
    IKController = None


# ============================================================
# 常量
# ============================================================

FRAME_WIDTH = 640      # 相机画面宽度
FRAME_HEIGHT = 480     # 相机画面高度
FRAME_CENTER_X = FRAME_WIDTH // 2   # 320
FRAME_CENTER_Y = FRAME_HEIGHT // 2  # 240

CENTER_THRESHOLD_PX = 15    # X 轴居中判定阈值 (像素)
DEPTH_OFFSET_CM = 3.6       # 深度距离减去此偏移 = 机械臂 Y 伸出距离 (cm)
MIN_DETECT_DISTANCE_CM = 15.0  # 测距有效范围下限 (cm): 距离 < 此值回到初始位置重新检测
MAX_DETECT_DISTANCE_CM = 30.0  # 测距有效范围上限 (cm): 距离 > 此值回到初始位置重新检测
MAX_DISTANCE_RETRIES = 5    # 距离超出有效范围时, 最多回到初始位置重新检测的次数
Z_GRAB = -10.5             # 抓取时 Z 轴位置 (cm)
GRIPPER_CLOSE_ANGLE = 19.0  # 抓取时夹爪角度 (度)

# ---- HSV 颜色范围 (修改此处的 H/S/V 上下限即可调整目标颜色) ----
# 取值范围: H 0-179, S 0-255, V 0-255
HSV_LOWER = (52, 70, 48)     # H/S/V 下限 (green1)
HSV_UPPER = (100, 255, 255)  # H/S/V 上限 (green1)
# 备用值: green2 → (70, 62, 46) / (100, 255, 255)

# 初始归零关节角度 (夹爪张开 60°, 释放物块)
INIT_HOME_ANGLES = [-90.0, 10.0, 55.0, 0.0, -61.0, 0.0, 60.0]
# 抓取后归零关节角度 (夹爪闭合 10°, 保持抓取)
HOME_JOINT_ANGLES = [-90.0, 10.0, 55.0, 0.0, -61.0, 0.0, 19.0]
# 夹住走姿态: XYZ 归零 (0,0,0) 后切换, 夹爪闭合 19° 带物行走
CARRY_HOME_ANGLES = [-6.9, -87.0, 89.7, -0.3, 3.8, 0.3, 19.0]

# X 轴居中控制参数
DEFAULT_X_GAIN = 0.03       # P 控制器增益 (cm/pixel), 需实测调优
DEFAULT_X_STEP_MAX = 2.5    # 单次 X 调整最大步长 (cm)
DEFAULT_X_STEP_MIN = 0.3    # 单次 X 调整最小步长 (cm)

# 移动参数 (与 arm_ik_control.py 默认 duration=2.0 保持一致)
CENTER_MOVE_DURATION = 1.0   # 居中调整移动时长 (秒)
STAGE_MOVE_DURATION = 1.2    # 分段伸出移动时长 (秒)
GRAB_MOVE_DURATION = 1.3     # 抓取移动时长 (秒)
HOME_MOVE_DURATION = 1.0     # 归零移动时长 (秒)
CARRY_MOVE_DURATION = 2.0    # 切换到夹住走姿态的移动时长 (秒)

# 等待参数 (留足时间让舵机稳定)
STAGE_SETTLE_TIME = 1.3      # 移动后稳定等待 (秒)
GRAB_WAIT_TIME = 4.0         # 抓取后等待 (秒)


# ============================================================
# 全局中断标志
# ============================================================

_interrupted = False


def _signal_handler(signum, frame):
    global _interrupted
    _interrupted = True
    print("\n[PP] 收到中断信号, 正在停止...")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ============================================================
# 拾取放置控制器
# ============================================================

class PickAndPlaceController:
    """颜色检测 + 机械臂控制协调器"""

    def __init__(self,
                 network_interface: Optional[str] = None,
                 color_name: str = "green",
                 dry_run: bool = False,
                 show_window: bool = True,
                 min_area: int = 200,
                 depth_offset_cm: float = DEPTH_OFFSET_CM,
                 center_threshold_px: int = CENTER_THRESHOLD_PX,
                 x_gain: float = DEFAULT_X_GAIN,
                 x_step_max: float = DEFAULT_X_STEP_MAX,
                 x_step_min: float = DEFAULT_X_STEP_MIN):
        """
        参数:
            network_interface: 网络接口名 (如 "eth0"), dry_run 模式下可为 None
            color_name: 检测颜色名 ("red", "green", "blue", "yellow")
            dry_run: 仅测试模式, 不连接机械臂
            show_window: 显示 OpenCV 预览窗口 (默认开启, 参照 color_object_detector.py)
            min_area: 最小轮廓面积, 滤除噪点 (默认: 200 px²)
            depth_offset_cm: 深度距离偏移 (默认: 3.5cm)
            center_threshold_px: X 轴居中判定阈值 (默认: 15px)
            x_gain: X 轴居中 P 控制器增益 (cm/pixel)
            x_step_max: 单次 X 调整最大步长 (cm)
            x_step_min: 单次 X 调整最小步长 (cm)
        """
        self.dry_run = dry_run
        self.show_window = show_window
        self.min_area = min_area
        self.depth_offset_cm = depth_offset_cm
        self.center_threshold_px = center_threshold_px
        self.x_gain = x_gain
        self.x_step_max = x_step_max
        self.x_step_min = x_step_min

        # ---- 夹爪状态跟踪 ----
        self.current_gripper = None

        # ---- 初始化相机 ----
        print("[PP] 初始化深度相机...")
        self.cam = DepthCamera(
            width=FRAME_WIDTH,
            height=FRAME_HEIGHT,
            fps=30,
            enable_color=True,
        )
        self.cam.start()
        print(f"[PP] 相机就绪: {FRAME_WIDTH}x{FRAME_HEIGHT} @ 30fps")

        # ---- 初始化颜色检测器 ----
        self.detector = ColorObjectDetector(color_name=color_name)
        print(f"[PP] 颜色检测器就绪: {self.detector.color_label}")

        # ---- 覆盖 HSV 范围 (参数在文件顶部 HSV_LOWER / HSV_UPPER 修改) ----
        self.detector.set_hsv_range(HSV_LOWER, HSV_UPPER)
        print(f"[PP] HSV 范围: H[{HSV_LOWER[0]}-{HSV_UPPER[0]}] "
              f"S[{HSV_LOWER[1]}-{HSV_UPPER[1]}] "
              f"V[{HSV_LOWER[2]}-{HSV_UPPER[2]}]")

        # ---- 初始化机械臂控制器 ----
        self.arm = None
        if not dry_run:
            if not HAS_ARM:
                raise ImportError("无法导入 arm_ik_control 模块")
            if network_interface is None:
                raise ValueError("需要指定网络接口 (如 eth0)")
            print(f"[PP] 初始化机械臂控制器 (interface={network_interface})...")
            self.arm = ArmIKController(network_interface)
            self.arm.init()
            print("[PP] 机械臂控制器就绪")
        else:
            print("[PP] DRY-RUN 模式: 不连接机械臂, 仅模拟移动")

        # ---- 当前状态 ----
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_z = 0.0
        # 当前底座 (J0) 角度: 只在居中/对中 (X 调整) 时改变,
        # 伸出/升降/抓取时保持锁定, 防止机械臂伸长时底座角度漂移
        self.current_j0 = INIT_HOME_ANGLES[0]

        # ---- 离线 IK 模拟 (dry-run) ----
        self.ik_sim = None
        if dry_run and IKController is not None:
            self.ik_sim = IKController()

        # ---- OpenCV 窗口 (参照 color_object_detector.py 布局) ----
        if self.show_window and HAS_CV2:
            self._win_main = "Color Object Detector"
            self._win_mask = "Mask"
            cv2.namedWindow(self._win_main, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self._win_main, 960, 720)
            cv2.namedWindow(self._win_mask, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self._win_mask, 480, 360)
            print("[PP] 预览窗口就绪 (按 ESC/Q 退出)")

        # ---- 统计 ----
        self.stats = {
            "detections": 0,
            "failed_detections": 0,
            "x_adjustments": 0,
            "z_adjustments": 0,
        }

    # ================================================================
    # 底层操作
    # ================================================================

    def _get_detection(self) -> Optional[dict]:
        """获取当前帧的检测结果, 返回 None 表示未检测到物块"""
        depth_frame, color_frame = self.cam.get_frames(aligned=True)
        if not depth_frame or color_frame is None:
            return None

        color_img = np.asanyarray(color_frame.get_data())
        result = self.detector.detect(color_img, depth_frame, min_area=self.min_area)

        # 更新预览窗口 (参照 color_object_detector.py live_detect 布局)
        if self.show_window and HAS_CV2:
            display = color_img.copy()
            if result is not None:
                self.detector.draw(display)
                # 画面中心十字线
                cv2.line(display,
                         (FRAME_CENTER_X - 30, FRAME_CENTER_Y),
                         (FRAME_CENTER_X + 30, FRAME_CENTER_Y),
                         (255, 255, 0), 1)
                cv2.line(display,
                         (FRAME_CENTER_X, FRAME_CENTER_Y - 30),
                         (FRAME_CENTER_X, FRAME_CENTER_Y + 30),
                         (255, 255, 0), 1)
                mask_preview = self.detector.draw_mask_preview(result["mask"])
            else:
                mask_preview = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)

            # 顶部状态栏 (仿照 color_object_detector.py 格式)
            status = f"Target: {self.detector.color_label}"
            if result:
                status += (f"  |  Pos=({result['cx']},{result['cy']})"
                          f"  Dist={result['distance_mm']:.0f}mm"
                          f"  Area={result['area']:.0f}px²")
            else:
                status += "  |  No target found"
            status += (f"  |  Arm X={self.current_x:+.1f} Y={self.current_y:+.1f} "
                      f"Z={self.current_z:+.1f}")
            cv2.putText(display, status, (10, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                        cv2.LINE_AA)

            cv2.imshow(self._win_main, display)
            cv2.imshow(self._win_mask, mask_preview)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                global _interrupted
                _interrupted = True

        if result is not None:
            self.stats["detections"] += 1
        else:
            self.stats["failed_detections"] += 1

        return result

    def _move_arm(self, x: float, y: float, z: float,
                  gripper: Optional[float] = None,
                  duration: float = 1.5,
                  lock_j0: Optional[float] = None):
        """移动机械臂到指定 XYZ 坐标 (cm)

        始终显式传递夹爪角度, 防止 J6 (关节7) 掉电。

        Args:
            lock_j0: 锁定底座角度 (度); None = 底座自由 (仅居中/对中使用)
        """
        self.current_x = x
        self.current_y = y
        self.current_z = z

        # 确保夹爪角度始终有值, 防止 J6 无指令掉电
        if gripper is None:
            gripper = self.current_gripper
        if gripper is not None:
            self.current_gripper = gripper

        if self.dry_run:
            # 模拟 IK 求解, 跟踪底座角度 (锁定时 J0 不变)
            if self.ik_sim is not None:
                if lock_j0 is not None:
                    self.current_j0 = lock_j0
                else:
                    angles, _, _ = self.ik_sim.xyz_to_joints(x, y, z, gripper=gripper)
                    self.current_j0 = angles[0]
            elif lock_j0 is not None:
                self.current_j0 = lock_j0
            g_str = f" grip={gripper}" if gripper is not None else ""
            print(f"  [DRY-RUN] move → X={x:+.2f} Y={y:+.2f} Z={z:+.2f}{g_str} "
                  f"(duration={duration}s)")
            time.sleep(0.2)
            return

        angles_7dof, _, _ = self.arm.move_to_xyz(x, y, z, gripper=gripper,
                                                 smooth=True, duration=duration,
                                                 lock_j0=lock_j0)
        # 记录底座角度: 锁定移动保持锁定值, 自由移动取实际解出的 J0
        if lock_j0 is not None:
            self.current_j0 = lock_j0
        else:
            self.current_j0 = angles_7dof[0]

    def _move_x_only(self, x: float, duration: float = CENTER_MOVE_DURATION):
        """仅调整 X 轴 (保持 Y, Z 不变) — 底座旋转对中, 底座自由"""
        self._move_arm(x, self.current_y, self.current_z, duration=duration)

    def _move_y_only(self, y: float, duration: float = STAGE_MOVE_DURATION):
        """仅调整 Y 轴 (保持 X, Z 不变) — 伸出/回收, 锁定底座角度"""
        self._move_arm(self.current_x, y, self.current_z,
                       duration=duration, lock_j0=self.current_j0)

    def _move_z_only(self, z: float, duration: float = STAGE_MOVE_DURATION):
        """仅调整 Z 轴 (保持 X, Y 不变) — 升降, 锁定底座角度"""
        self._move_arm(self.current_x, self.current_y, z,
                       duration=duration, lock_j0=self.current_j0)

    # ================================================================
    # 居中控制
    # ================================================================

    def center_x(self, max_attempts: int = 15) -> bool:
        """
        X 轴居中控制: 通过调整机械臂 X 参数使物块在画面水平居中。

        自适应增益: 误差大时用全增益快速逼近, 误差小时衰减增益防止超调。
        检测超调 (误差方向翻转) 时进一步缩小步长。

        返回:
            True  = 已居中
            False = 物块丢失或超时
        """
        print(f"[CenterX] 开始 X 轴居中 (阈值=±{self.center_threshold_px}px, "
              f"增益={self.x_gain} cm/px)")

        prev_sign = 0  # 上一轮误差方向, 用于检测超调

        for attempt in range(1, max_attempts + 1):
            if _interrupted:
                return False

            result = self._get_detection()
            if result is None:
                time.sleep(0.3)
                continue

            cx = result["cx"]
            error_px = cx - FRAME_CENTER_X

            if abs(error_px) <= self.center_threshold_px:
                print(f"[CenterX] ✓ 已居中! cx={cx}, 误差={error_px:+d}px, "
                      f"当前X={self.current_x:+.2f}cm")
                return True

            # 自适应增益: 误差 < 40px 时衰减, 避免超调
            abs_err = abs(error_px)
            if abs_err < 20:
                effective_gain = self.x_gain * 0.35
            elif abs_err < 40:
                effective_gain = self.x_gain * 0.55
            elif abs_err < 80:
                effective_gain = self.x_gain * 0.75
            else:
                effective_gain = self.x_gain

            adjust_cm = effective_gain * error_px

            # 限幅
            sign = 1.0 if adjust_cm > 0 else -1.0
            abs_adjust = abs(adjust_cm)
            abs_adjust = max(self.x_step_min, min(abs_adjust, self.x_step_max))
            adjust_cm = sign * abs_adjust

            # 超调检测: 误差方向翻转 → 步长减半
            if prev_sign != 0 and sign != prev_sign:
                adjust_cm *= 0.5
                print(f"[CenterX] ⚡ 检测到超调, 步长减半 → {adjust_cm:+.2f}cm")
            prev_sign = sign

            target_x = self.current_x + adjust_cm

            print(f"[CenterX] 尝试 {attempt}/{max_attempts}: cx={cx}, "
                  f"误差={error_px:+d}px (增益×{effective_gain/self.x_gain:.2f}) "
                  f"→ 调整 X {adjust_cm:+.2f}cm → X={target_x:+.2f}cm")

            self._move_x_only(target_x, duration=CENTER_MOVE_DURATION)
            self.stats["x_adjustments"] += 1
            time.sleep(STAGE_SETTLE_TIME)

        print(f"[CenterX] ✗ 居中失败: 超过最大尝试次数 {max_attempts}")
        return False

    def _detect_center_measure(self, once: bool = True) -> Optional[float]:
        """
        Step 1-3 组合: 搜索物块 → 底座旋转对中 → 对中后测距。

        返回:
            物块深度距离 (cm), 或 None 表示失败 (中断 / 未检测到 / 对中失败)
        """
        # ---- Step 1: 检测物块 ----
        print("\n[Step 1] 搜索物块...")

        while not _interrupted:
            result = self._get_detection()
            if result is not None:
                break
            if not once:
                time.sleep(0.5)
                continue
            # 单次模式: 等待最多 10 秒
            print("  等待物块出现...")
            for _ in range(20):
                if _interrupted:
                    return None
                time.sleep(0.5)
                result = self._get_detection()
                if result is not None:
                    break
            if result is None:
                print("[Step 1] ✗ 未检测到物块, 退出")
                return None
            break

        if _interrupted:
            return None

        cx = result["cx"]
        print(f"[Step 1] ✓ 物块已检测: cx={cx}")

        # ---- Step 2: 底座旋转对中 ----
        print("\n[Step 2] 底座旋转对中 (X轴)...")
        if not self.center_x():
            print("[Step 2] ✗ 对中失败")
            return None

        # ---- Step 3: 对中后测距 ----
        print("\n[Step 3] 对中后检测距离...")
        result = self._get_detection()
        if result is None:
            print("[Step 3] ✗ 对中后未检测到物块, 退出")
            return None

        depth_mm = result["distance_mm"]
        depth_cm = depth_mm / 10.0
        print(f"[Step 3] ✓ 距离={depth_mm:.0f}mm ({depth_cm:.1f}cm)")
        return depth_cm

    # ================================================================
    # 主抓取流程
    # ================================================================

    def run(self, once: bool = True) -> bool:
        """
        执行一次完整的拾取放置流程 (2段伸出)。

        流程:
          1. 归零 (X=0, Y=0, Z=0)
          2. 检测物块
          3. 底座旋转对中 (X轴), 测距; 距离 <15cm 或 >30cm 回到初始位置重新检测
          4. 第1段: 伸出 1/2 距离, Z=-2, 重新对中
          5. 第2段: 全伸出, Z=-2, 重新对中
          6. 下降 Z=-10, 抓取, 抬起, 归零
          7. 切换到夹住走姿态 (带物行走)

        参数:
            once: True = 执行一次后返回, False = 循环等待物块

        返回: True = 成功完成, False = 中断或失败
        """
        print("\n" + "=" * 60)
        print("  拾取放置系统启动 (2段伸出)")
        print(f"  检测颜色: {self.detector.color_label}")
        print(f"  模式: {'DRY-RUN (离线模拟)' if self.dry_run else '在线控制'}")
        print("=" * 60)

        # ---- Step 0: 归零 (直接发关节角度, 夹爪张开, 不走IK) ----
        print(f"\n[Step 0] 机械臂归零 → {INIT_HOME_ANGLES}")
        if self.dry_run:
            print(f"  [DRY-RUN] set_angles → {INIT_HOME_ANGLES}")
            time.sleep(0.5)
        else:
            self._wait_for_home(INIT_HOME_ANGLES, step_label="Step0")
        self.current_x, self.current_y, self.current_z = 0.0, 0.0, 0.0
        print("[Step 0] ✓ 归零完成")

        # ---- Step 1-3: 搜索 → 对中 → 测距 (距离范围校验) ----
        # 距离 < MIN_DETECT_DISTANCE_CM 或 > MAX_DETECT_DISTANCE_CM 时,
        # 回到初始位置 (0,0,0) 重新检测, 最多重试 MAX_DISTANCE_RETRIES 次
        depth_cm = None
        for attempt in range(1, MAX_DISTANCE_RETRIES + 1):
            if _interrupted:
                return False

            if attempt > 1:
                print(f"\n[PP] 距离超出有效范围, 回到初始位置重新检测 "
                      f"(第 {attempt}/{MAX_DISTANCE_RETRIES} 次)...")
                self._move_arm(0.0, 0.0, 0.0, duration=CENTER_MOVE_DURATION)
                time.sleep(STAGE_SETTLE_TIME)

            depth_cm = self._detect_center_measure(once=once)
            if depth_cm is None:
                return False

            if MIN_DETECT_DISTANCE_CM <= depth_cm <= MAX_DETECT_DISTANCE_CM:
                print(f"[Step 3] ✓ 距离 {depth_cm:.1f}cm 在有效范围 "
                      f"[{MIN_DETECT_DISTANCE_CM:.0f}, {MAX_DETECT_DISTANCE_CM:.0f}]cm 内")
                break

            if depth_cm < MIN_DETECT_DISTANCE_CM:
                reason = f"过近 (< {MIN_DETECT_DISTANCE_CM:.0f}cm)"
            else:
                reason = f"过远 (> {MAX_DETECT_DISTANCE_CM:.0f}cm)"
            print(f"[Step 3] ⚠ 距离 {depth_cm:.1f}cm {reason}, 回到初始位置重新检测...")
        else:
            print(f"[Step 3] ✗ 距离始终超出 [{MIN_DETECT_DISTANCE_CM:.0f}, "
                  f"{MAX_DETECT_DISTANCE_CM:.0f}]cm, 放弃本次抓取")
            return False

        # 计算目标 Y 距离
        extend_distance_cm = depth_cm - self.depth_offset_cm
        if extend_distance_cm <= 0:
            print(f"[Step 3] ✗ 物块距离太近! 深度={depth_cm:.1f}cm, "
                  f"偏移={self.depth_offset_cm}cm → 伸出距离={extend_distance_cm:.1f}cm")
            return False
        target_y = -extend_distance_cm

        print(f"[Step 3] 目标延伸距离 = {extend_distance_cm:.1f}cm "
              f"(深度{depth_cm:.1f}cm - {self.depth_offset_cm}cm偏移) "
              f"→ Y={target_y:+.1f}cm")

        # ---- Step 4: 完全伸长 → Z=-10 抓取 (已删除 1/2 重新对中段, 第一段对中后直接全伸) ----
        if _interrupted:
            return False

        print(f"\n[Step 4] === 完全伸长: Y={target_y:.1f}cm → Z={Z_GRAB:.0f} 抓取 ===")
        # 全伸出 Y (等待延长, 确保舵机稳定)
        self._move_y_only(target_y, duration=STAGE_MOVE_DURATION)
        time.sleep(STAGE_SETTLE_TIME * 2.3)
        # Z 直接降到抓取位
        self._move_z_only(Z_GRAB, duration=STAGE_MOVE_DURATION)
        time.sleep(STAGE_SETTLE_TIME)

        print(f"[Step 4] ✓ 伸长完成 (X={self.current_x:+.2f}, Y={self.current_y:+.2f}, Z={self.current_z:+.2f})")

        # ---- Step 5: 抓取 ----
        if _interrupted:
            return False

        print("[Step 5] 夹爪闭合...")
        self._move_arm(self.current_x, self.current_y, Z_GRAB,
                       gripper=GRIPPER_CLOSE_ANGLE,
                       duration=GRAB_MOVE_DURATION,
                       lock_j0=self.current_j0)
        time.sleep(GRAB_WAIT_TIME)  # 延长等待夹爪闭合到位, 防止没抓稳就下一步

        print(f"[Step 5] ✓ 抓取完成")

        # ---- Step 6: 分段回收归零 ----
        if _interrupted:
            return False

        print(f"\n[Step 6] 分段回收: Z→0 → Y→0 → X→0")
        # 6.1 抬 Z 到 0
        self._move_z_only(0.0, duration=STAGE_MOVE_DURATION)
        time.sleep(STAGE_SETTLE_TIME)
        print(f"  [6.1] Z=0 ✓")
        # 6.2 收 Y 到 0
        self._move_y_only(0.0, duration=STAGE_MOVE_DURATION)
        time.sleep(STAGE_SETTLE_TIME)
        print(f"  [6.2] Y=0 ✓")
        # 6.3 收 X 到 0 (夹爪保持闭合)
        self._move_x_only(0.0, duration=CENTER_MOVE_DURATION)
        time.sleep(STAGE_SETTLE_TIME)
        print(f"  [6.3] X=0 ✓ 归零完成")

        # ---- Step 7: 切换到夹住走姿态 (带物行走) ----
        if _interrupted:
            return False

        print(f"\n[Step 7] 切换到夹住走姿态 → {CARRY_HOME_ANGLES}")
        if self.dry_run:
            print(f"  [DRY-RUN] set_angles → {[f'{a:.1f}' for a in CARRY_HOME_ANGLES]}")
            time.sleep(0.2)
            carry_ok = True
        else:
            carry_ok = self._move_to_joint_angles(CARRY_HOME_ANGLES, step_label="Step7",
                                                  duration=CARRY_MOVE_DURATION)
        if carry_ok:
            print("[Step 7] ✓ 夹住走姿态就绪 (可带物行走)")
        else:
            print("[Step 7] ⚠ 夹住走姿态未完全到位 (抓取已完成, 注意带物行走安全)")

        print("\n" + "=" * 60)
        print("  ✓ 拾取放置完成!")
        self._print_stats()
        print("=" * 60)

        return True

    def _wait_for_home(self, target_angles, step_label: str = "Home",
                       max_retries: int = 10) -> bool:
        """
        发送目标关节角度并等待舵机实际到位。
        每 1.5s 检测一次当前角度, 未到位则重发指令。

        返回: True = 已到位, False = 超时
        """
        target = np.array(target_angles)
        tolerance = 35.0  # 每关节容许误差 (度)

        for attempt in range(1, max_retries + 1):
            self.arm.arm.set_angles(target_angles)
            time.sleep(1.5)

            current = np.array(self.arm.arm.current_angles)
            errors = np.abs(current - target)
            max_err = np.max(errors)

            if max_err <= tolerance:
                print(f"[{step_label}] ✓ 舵机已到位! 最大误差={max_err:.1f}° "
                      f"(尝试 {attempt} 次)")
                return True

            print(f"[{step_label}] 舵机未到位, 最大误差={max_err:.1f}° > {tolerance}°, "
                  f"重发 ({attempt}/{max_retries})...")

        print(f"[{step_label}] ⚠ 超时: {max_retries} 次重试后仍未到位")
        return False

    def _move_to_joint_angles(self, target_angles, step_label: str = "Joint",
                              duration: float = CARRY_MOVE_DURATION,
                              max_retries: int = 5) -> bool:
        """
        直接发送目标关节角度并平滑到位 (用于非 XYZ 目标姿态, 如夹住走)。

        使用 smooth_move 平滑过渡 (抓取后带物移动更稳), 再等待舵机实际到位,
        未到位则重发指令。

        返回: True = 已到位, False = 超时
        """
        target = np.array(target_angles)
        tolerance = 80.0  # 每关节容许误差 (度): 真机调试后放宽, 避免到位判定过严反复重发

        for attempt in range(1, max_retries + 1):
            self.arm.arm.smooth_move(list(target), duration=duration)
            time.sleep(STAGE_SETTLE_TIME)

            current = np.array(self.arm.arm.current_angles)
            max_err = np.max(np.abs(current - target))

            if max_err <= tolerance:
                print(f"[{step_label}] ✓ 舵机已到位! 最大误差={max_err:.1f}° "
                      f"(尝试 {attempt} 次)")
                return True

            print(f"[{step_label}] 舵机未到位, 最大误差={max_err:.1f}° > {tolerance}°, "
                  f"重发 ({attempt}/{max_retries})...")

        print(f"[{step_label}] ⚠ 超时: {max_retries} 次重试后仍未到位")
        return False

    def _print_stats(self):
        """打印统计信息"""
        print(f"  检测次数: {self.stats['detections']}")
        print(f"  未检测到: {self.stats['failed_detections']}")
        print(f"  X 调整:   {self.stats['x_adjustments']}")
        print(f"  Z 调整:   {self.stats['z_adjustments']}")

    def cleanup(self):
        """清理资源"""
        print("[PP] 清理资源...")
        if self.show_window and HAS_CV2:
            cv2.destroyAllWindows()
        if self.cam is not None:
            self.cam.close()
            print("[PP] 相机已关闭")

    # ================================================================
    # 交互模式
    # ================================================================

    def interactive(self):
        """交互控制模式"""
        print("""
+--------------------------------------------------+
|   拾取放置系统 — 交互模式                           |
+--------------------------------------------------+
|  run         - 执行一次抓取流程                     |
|  detect      - 检测物块并打印坐标                   |
|  center      - 仅执行 X 轴居中                     |
|  move X Y Z  - 移动机械臂到指定坐标                 |
|  grip ANGLE  - 设置夹爪角度                        |
|  home        - 机械臂归零                          |
|  status      - 当前状态                            |
|  stats       - 统计信息                            |
|  quit        - 退出                               |
+--------------------------------------------------+
""")

        while not _interrupted:
            try:
                cmd_line = input("\nPP> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not cmd_line:
                continue

            parts = cmd_line.split()
            command = parts[0].lower()

            try:
                if command in ("quit", "exit", "q"):
                    break

                elif command == "run":
                    self.run(once=True)

                elif command == "detect":
                    result = self._get_detection()
                    if result:
                        print(f"  物块: cx={result['cx']}, cy={result['cy']}, "
                              f"dist={result['distance_mm']:.0f}mm, "
                              f"area={result['area']:.0f}px²")
                    else:
                        print("  未检测到物块")

                elif command == "center":
                    self.center_x()

                elif command == "move":
                    if len(parts) < 4:
                        print("用法: move X Y Z")
                        continue
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    self._move_arm(x, y, z)

                elif command == "grip":
                    if len(parts) < 2:
                        print("用法: grip ANGLE")
                        continue
                    angle = float(parts[1])
                    self._move_arm(self.current_x, self.current_y,
                                   self.current_z, gripper=angle)

                elif command == "home":
                    self._move_arm(0.0, 0.0, 0.0, duration=HOME_MOVE_DURATION)

                elif command == "status":
                    print(f"  当前坐标: X={self.current_x:+.2f} "
                          f"Y={self.current_y:+.2f} "
                          f"Z={self.current_z:+.2f}")
                    if self.current_gripper is not None:
                        print(f"  夹爪角度: {self.current_gripper:.1f}°")
                    print(f"  模式: {'DRY-RUN' if self.dry_run else '在线'}")

                elif command == "stats":
                    self._print_stats()

                else:
                    print("可用命令: run, detect, center, move, grip, "
                          "home, status, stats, quit")

            except ValueError as e:
                print(f"参数错误: {e}")
            except Exception as e:
                print(f"错误: {e}")
                import traceback
                traceback.print_exc()


# ============================================================
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="拾取放置系统: 颜色检测 + D1 机械臂 IK 控制",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 pick_and_place.py eth0                        # 检测绿色, 单次抓取
  python3 pick_and_place.py eth0 --color red            # 检测红色物块
  python3 pick_and_place.py eth0 --color blue --loop    # 抓取→夹住走姿态后自动退出
  python3 pick_and_place.py eth0 -i                     # 交互模式
  python3 pick_and_place.py --dry-run                   # 离线测试 (不连机械臂)
  python3 pick_and_place.py eth0 --show-window          # 显示摄像头预览
        """,
    )

    # 连接参数
    parser.add_argument("interface", nargs="?", default=None,
                        help="网络接口 (如 eth0), dry-run 模式可省略")
    parser.add_argument("--dry-run", action="store_true",
                        help="离线模式 (仅模拟机械臂移动, 不真实连接)")

    # 检测参数
    parser.add_argument("--color", type=str, default="green",
                        choices=["red", "green", "blue", "yellow"],
                        help="目标颜色 (默认: green)")
    parser.add_argument("--min-area", type=int, default=200,
                        help="最小轮廓面积, 滤除噪点 (默认: 200 px²)")

    # 控制参数
    parser.add_argument("--x-gain", type=float, default=DEFAULT_X_GAIN,
                        help=f"X 轴居中 P 增益 cm/px (默认: {DEFAULT_X_GAIN})")
    parser.add_argument("--x-step-max", type=float, default=DEFAULT_X_STEP_MAX,
                        help=f"单次 X 调整最大步长 cm (默认: {DEFAULT_X_STEP_MAX})")
    parser.add_argument("--x-step-min", type=float, default=DEFAULT_X_STEP_MIN,
                        help=f"单次 X 调整最小步长 cm (默认: {DEFAULT_X_STEP_MIN})")
    parser.add_argument("--depth-offset", type=float, default=DEPTH_OFFSET_CM,
                        help=f"深度距离偏移 cm (默认: {DEPTH_OFFSET_CM})")
    parser.add_argument("--center-threshold", type=int, default=CENTER_THRESHOLD_PX,
                        help=f"X 轴居中判定阈值 px (默认: {CENTER_THRESHOLD_PX})")

    # 模式参数
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="交互控制模式")
    parser.add_argument("--loop", action="store_true",
                        help="抓取并切换到夹住走姿态后自动退出 (否则持续等待物块)")
    parser.add_argument("--show-window", action="store_true", default=True,
                        help="显示 OpenCV 摄像头预览窗口 (默认开启)")
    parser.add_argument("--no-window", action="store_false", dest="show_window",
                        help="关闭摄像头预览窗口")

    # 机械臂参数 (传递给 ArmIKController)
    parser.add_argument("--force-enable", action="store_true",
                        help="强制使能机械臂 (即使已上电)")
    parser.add_argument("--j4-scale-x-pos", type=float, default=1.3,
                        help="J4 X+补偿 (默认: 1.3)")
    parser.add_argument("--j4-scale-x-neg", type=float, default=-0.1,
                        help="J4 X-补偿 (默认: -0.1)")
    parser.add_argument("--j4-scale-y", type=float, default=0.73,
                        help="J4 Y补偿 (默认: 0.73)")
    parser.add_argument("--j4-scale-z", type=float, default=0.0,
                        help="J4 Z补偿 (默认: 0.0)")
    parser.add_argument("--j4-bias", type=float, default=0.0,
                        help="J4 固定偏置 (默认: 0.0)")

    args = parser.parse_args()

    # 创建控制器 (CLI 参数覆盖默认值)
    controller = PickAndPlaceController(
        network_interface=args.interface,
        color_name=args.color,
        dry_run=args.dry_run,
        show_window=args.show_window,
        min_area=args.min_area,
        depth_offset_cm=args.depth_offset,
        center_threshold_px=args.center_threshold,
        x_gain=args.x_gain,
        x_step_max=args.x_step_max,
        x_step_min=args.x_step_min,
    )

    # 修改 J4 补偿参数 (在线模式)
    if not args.dry_run and controller.arm is not None:
        ik = controller.arm.ik_ctrl
        ik.j4_scale_x_pos = args.j4_scale_x_pos
        ik.j4_scale_x_neg = args.j4_scale_x_neg
        ik.j4_scale_y = args.j4_scale_y
        ik.j4_scale_z = args.j4_scale_z
        ik.j4_bias = args.j4_bias

    try:
        if args.interactive:
            # 交互模式
            controller.interactive()

        elif args.loop:
            # 循环模式: 持续检测并抓取; 抓取成功并切换到夹住走姿态后直接退出
            print("[PP] 循环模式: 抓取完成并切换夹住走姿态后自动退出")
            cycle = 0
            while not _interrupted:
                cycle += 1
                print(f"\n{'#' * 60}")
                print(f"#  第 {cycle} 次抓取")
                print(f"{'#' * 60}")
                success = controller.run(once=False)
                if not success:
                    print(f"[PP] 第 {cycle} 次抓取未完成, 继续等待...")
                    time.sleep(2.0)
                    continue
                # 已切换到夹住走姿态, 不再检测, 直接退出程序
                print("[PP] ✓ 夹住走姿态就绪, 退出程序")
                break

        else:
            # 默认: 单次抓取
            controller.run(once=True)

    except KeyboardInterrupt:
        print("\n[PP] 用户中断")
    finally:
        controller.cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(main())
