"""
Go2 + D435i 黑线循迹 (1:1 翻译 go2_line_follow.cpp)

双ROI预瞄 + PID + 自适应速度 + ClassicWalk
+ 深度过滤: 用深度数据排除地面上的黑色障碍物
"""

import sys
import time
import cv2
import numpy as np
import pyrealsense2 as rs

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

# ============================================================
BASE_SPEED = 0.25
MIN_SPEED = 0.06
MAX_YAW = 3.0            # 直角弯需要大幅度转弯
KP = 1.20                # 更强比例控制，快速回到线中间
KI = 0.05                # 更大积分，消除稳态偏移（走歪）
KD = 0.10                # 微分预判弯道趋势
FAR_WEIGHT = 0.35

CONTROL_PERIOD = 0.05    # 20Hz 控制频率，防卡顿

BLACK_THRESHOLD = 70
MIN_AREA = 200.0
INTERSECTION_AREA = 4000

DEPTH_TOLERANCE = 150
DISPLAY_SKIP = 3

# ============================================================


def process_roi(roi, img_w, depth_roi=None):
    """处理单个ROI -> (detected, normalized_error, cx_pixel)

    如果有深度数据: 过滤掉深度偏离地面中值的像素(障碍物)
    """
    _, binary = cv2.threshold(roi, BLACK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    # 深度过滤: 只保留地面上的黑线,排除凸起的黑色障碍物
    if depth_roi is not None:
        valid_depth = depth_roi > 0         # 排除深度无效像素
        if np.any(valid_depth):
            median_depth = np.median(depth_roi[valid_depth])
            depth_mask = np.abs(depth_roi.astype(np.float32) - median_depth) < DEPTH_TOLERANCE
            depth_mask = (depth_mask & valid_depth).astype(np.uint8) * 255
            binary = cv2.bitwise_and(binary, depth_mask)

    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cv2.morphologyEx(binary, cv2.MORPH_OPEN, k, dst=binary)

    m = cv2.moments(binary, True)
    if m["m00"] > MIN_AREA:
        cx = m["m10"] / m["m00"]
        err = (img_w / 2.0 - cx) / (img_w / 2.0)
        return True, err, cx
    return False, 0.0, 0.0


def compute_yaw(error, integral, prev_err, last_t):
    """PID -> (yaw, integral, prev_err, last_t)"""
    now = time.time()
    dt = now - last_t
    if dt <= 0 or dt > 0.5:
        dt = 0.05
    last_t = now

    integral += error * dt
    if integral > 2.0:
        integral = 2.0
    if integral < -2.0:
        integral = -2.0

    deriv = (error - prev_err) / dt
    prev_err = error

    yaw = KP * error + KI * integral + KD * deriv
    if yaw > MAX_YAW:
        yaw = MAX_YAW
    if yaw < -MAX_YAW:
        yaw = -MAX_YAW
    return yaw, integral, prev_err, last_t


def main():
    global BASE_SPEED, BLACK_THRESHOLD, KP, KI, KD

    print("=" * 55)
    print("  Go2 + D435i 黑线循迹 (双ROI+PID)")
    print("=" * 55)
    print(f"  speed: {BASE_SPEED}~{MIN_SPEED}  kp={KP} ki={KI} kd={KD}")
    print(f"  far_weight={FAR_WEIGHT}  thresh={BLACK_THRESHOLD}")
    print("=" * 55)

    # ---- 1. DDS ----
    if len(sys.argv) > 1:
        ChannelFactoryInitialize(0, sys.argv[1])
    else:
        ChannelFactoryInitialize(0)

    # ---- 2. 运动 ----
    from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient

    sport = SportClient()
    sport.SetTimeout(10.0)
    sport.Init()

    msc = MotionSwitcherClient()
    msc.SetTimeout(5.0)
    msc.Init()

    print("[INIT] SelectMode normal")
    msc.SelectMode("normal")
    time.sleep(1.5)

    print("[INIT] StandUp")
    sport.StandUp()
    time.sleep(2)

    print("[INIT] SwitchJoystick")
    sport.SwitchJoystick(False)
    time.sleep(0.5)

    print("[INIT] ClassicWalk")
    sport.ClassicWalk(True)
    time.sleep(0.5)

    print("[INIT] Ready")

    # ---- 3. D435i (color + depth, align depth->color) ----
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    try:
        pipeline.start(config)
        print("[INFO] D435i started")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return

    align = rs.align(rs.stream.color)
    print("[INFO] 深度过滤已启用 (排除地面障碍物)")

    # ---- 状态 ----
    integral = 0.0
    prev_err = 0.0
    last_t = time.time()
    last_move_t = 0.0
    frame_cnt = 0
    near_cx = 0.0
    far_cx = 0.0

    print("[INFO] 循迹开始, ESC 停止")

    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned = align.process(frames)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame:
                continue

            img = np.asanyarray(color_frame.get_data())
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 深度图 (mm)
            depth = np.asanyarray(depth_frame.get_data()) if depth_frame else None

            h, w = gray.shape
            if w > 640:
                gray = cv2.resize(gray, (w // 2, h // 2))
                if depth is not None:
                    depth = cv2.resize(depth, (w // 2, h // 2), interpolation=cv2.INTER_NEAREST)
                h, w = gray.shape

            roi_half = h // 2
            roi_mid = h * 3 // 4

            # ---- 双ROI检测 (带深度过滤) ----
            near_roi = gray[roi_mid:h, :]
            near_depth = depth[roi_mid:h, :] if depth is not None else None
            near_det, near_err, near_cx = process_roi(near_roi, w, near_depth)

            far_roi = gray[roi_half:roi_mid, :]
            far_depth = depth[roi_half:roi_mid, :] if depth is not None else None
            far_det, far_err, far_cx = process_roi(far_roi, w, far_depth)

            # ---- 融合 ----
            detected = False
            err = 0.0
            is_intersection = False

            if near_det and far_det:
                err = (1.0 - FAR_WEIGHT) * near_err + FAR_WEIGHT * far_err
                detected = True
            elif near_det:
                err = near_err
                detected = True
            elif far_det:
                err = far_err
                detected = True

            if near_det:
                near_bin = cv2.threshold(near_roi, BLACK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)[1]
                if cv2.countNonZero(near_bin) > INTERSECTION_AREA:
                    is_intersection = True
                    err = 0.0

            # ---- PID + 自适应速度 ----
            if detected:
                if is_intersection:
                    vyaw = 0.0
                    integral = 0.0
                    prev_err = 0.0
                else:
                    vyaw, integral, prev_err, last_t = compute_yaw(err, integral, prev_err, last_t)

                abs_yaw = abs(vyaw)
                if abs_yaw > 0.60:
                    vx = MIN_SPEED
                elif abs_yaw > 0.20:
                    vx = MIN_SPEED + (BASE_SPEED - MIN_SPEED) * (0.60 - abs_yaw) / 0.40
                else:
                    vx = BASE_SPEED
            else:
                vyaw = 0.80
                vx = 0.0
                integral = 0.0
                prev_err = 0.0

            # 控制频率限制: 20Hz, 防卡顿
            t_now = time.time()
            if t_now - last_move_t >= CONTROL_PERIOD:
                sport.Move(vx, 0, vyaw)
                last_move_t = t_now

            # ---- 可视化 (降频) ----
            frame_cnt += 1
            if frame_cnt % DISPLAY_SKIP == 0:
                # 缩放到显示尺寸
                disp_w, disp_h = 480, 480 * h // w
                small = cv2.resize(gray, (disp_w, disp_h))
                disp = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)

                # 远处ROI框 (蓝)
                fy0 = roi_half * disp_h // h
                fy1 = roi_mid * disp_h // h
                cv2.rectangle(disp, (0, fy0), (disp_w - 1, fy1), (255, 200, 0), 1)
                # 近处ROI框 (黄)
                ny0 = roi_mid * disp_h // h
                cv2.rectangle(disp, (0, ny0), (disp_w - 1, disp_h - 1), (0, 255, 255), 1)
                # 中线 (红)
                cv2.line(disp, (disp_w // 2, fy0), (disp_w // 2, disp_h - 1), (255, 0, 0), 1)

                # 远处检测点 (蓝点)
                if far_det:
                    fcx = int(far_cx * disp_w / w)
                    fcy = (fy0 + fy1) // 2
                    cv2.circle(disp, (fcx, fcy), 5, (255, 0, 0), -1)

                # 近处检测点 (红点)
                if near_det:
                    ncx = int(near_cx * disp_w / w)
                    ncy = (ny0 + disp_h) // 2
                    cv2.circle(disp, (ncx, ncy), 6, (0, 0, 255), -1)

                # 状态文字
                if detected:
                    if is_intersection:
                        txt = "CROSSROAD -> STRAIGHT"
                        color = (0, 165, 255)
                    else:
                        txt = f"LINE near={near_err:+.3f} far={far_err:+.3f}"
                        color = (0, 255, 0)
                else:
                    txt = "LOST"
                    color = (0, 0, 255)
                cv2.putText(disp, txt, (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

                # 速度信息
                cv2.putText(disp, f"vx={vx:.2f} vyaw={vyaw:+.2f}",
                            (5, disp_h - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

                cv2.imshow("LineFollow", disp)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                print("[INFO] ESC")
                break
            if key == ord('w'):
                BLACK_THRESHOLD = min(255, BLACK_THRESHOLD + 5)
                print(f"[TUNE] thresh={BLACK_THRESHOLD}")
            elif key == ord('s'):
                BLACK_THRESHOLD = max(0, BLACK_THRESHOLD - 5)
                print(f"[TUNE] thresh={BLACK_THRESHOLD}")
            elif key == ord('r'):
                BASE_SPEED = min(0.8, BASE_SPEED + 0.05)
                print(f"[TUNE] speed={BASE_SPEED:.2f}")
            elif key == ord('f'):
                BASE_SPEED = max(0.05, BASE_SPEED - 0.05)
                print(f"[TUNE] speed={BASE_SPEED:.2f}")
            elif key == ord('t'):
                KP = min(2.0, KP + 0.05)
                print(f"[TUNE] kp={KP:.2f}")
            elif key == ord('g'):
                KP = max(0.1, KP - 0.05)
                print(f"[TUNE] kp={KP:.2f}")

    except KeyboardInterrupt:
        print("\n[INFO] Interrupt")
    finally:
        sport.StopMove()
        time.sleep(0.3)
        pipeline.stop()
        cv2.destroyAllWindows()
        print("[INFO] Exit")


if __name__ == "__main__":
    main()
