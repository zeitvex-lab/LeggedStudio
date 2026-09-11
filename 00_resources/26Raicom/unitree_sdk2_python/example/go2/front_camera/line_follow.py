"""
Go2 + D435i 黑线循迹程序

原理：
  - D435i 摄像头朝下拍摄地面
  - 图像处理提取黑色线条的质心位置
  - 计算线条偏离画面中心的水平偏移量
  - 用比例控制将偏移映射为角速度，驱动机器人沿黑线前进
"""
import sys
import time
import cv2
import numpy as np
import pyrealsense2 as rs

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

# ============================================================
# 可调参数
# ============================================================
FORWARD_SPEED = 0.15         # 前进速度 (m/s)，建议 0.1~0.2
MAX_ANGULAR_SPEED = 0.5      # 最大角速度 (rad/s)
KP = 0.008                   # 比例控制系数（偏移像素 → 角速度）
DEAD_ZONE = 15               # 死区像素，偏移小于此值不纠偏
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
ROI_TOP = 300                # 只处理画面下半部分（近处地面）
ROI_BOTTOM = 480

# 黑线检测阈值（灰度值，0=纯黑, 255=纯白）
BLACK_THRESHOLD = 70         # 低于此值视为黑线
MIN_BLACK_AREA = 200         # 最小黑色像素面积，过滤噪点

# ============================================================


def detect_black_line(gray_frame):
    """
    检测画面中的黑线，返回线条质心的水平偏移量（像素）。
    偏移量 = 黑线中心X - 画面中心X
    正偏移 → 黑线偏右 → 需要右转
    负偏移 → 黑线偏左 → 需要左转
    返回: (offset_x, found)   found=False 表示未检测到黑线
    """
    h, w = gray_frame.shape
    center_x = w // 2

    # 只取 ROI 区域（画面下半部分，即机器人前方近处地面）
    roi = gray_frame[ROI_TOP:ROI_BOTTOM, :]

    # 二值化：黑色像素为 255
    _, binary = cv2.threshold(roi, BLACK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    # 形态学开运算：去除小噪点
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # 找轮廓
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return 0, False

    # 取面积最大的轮廓作为黑线
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)

    if area < MIN_BLACK_AREA:
        return 0, False

    # 计算质心
    M = cv2.moments(largest)
    if M["m00"] == 0:
        return 0, False

    cx = int(M["m10"] / M["m00"])  # 质心 X（相对于 ROI）
    # 换算到全图坐标系
    offset = cx - center_x

    return offset, True


def draw_debug(color_frame, gray_frame, offset, found):
    """绘制调试信息"""
    h, w = color_frame.shape[:2]
    center_x = w // 2

    # 画 ROI 框
    cv2.rectangle(color_frame, (0, ROI_TOP), (w, ROI_BOTTOM), (255, 255, 0), 1)

    # 画画面中心竖线
    cv2.line(color_frame, (center_x, 0), (center_x, h), (0, 255, 0), 1)

    if found:
        # 画检测到的黑线中心
        line_cx = center_x + offset
        cv2.line(color_frame, (line_cx, ROI_TOP), (line_cx, ROI_BOTTOM), (0, 0, 255), 2)
        cv2.circle(color_frame, (line_cx, (ROI_TOP + ROI_BOTTOM) // 2), 8, (0, 0, 255), -1)
        status = f"LINE FOUND | offset: {offset:+d}px"
        status_color = (0, 255, 0)
    else:
        status = "LINE LOST"
        status_color = (0, 0, 255)

    cv2.putText(color_frame, status, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

    # 右侧显示二值化小窗
    roi = gray_frame[ROI_TOP:ROI_BOTTOM, :]
    _, binary = cv2.threshold(roi, BLACK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    binary_resized = cv2.resize(binary, (200, 150))
    binary_bgr = cv2.cvtColor(binary_resized, cv2.COLOR_GRAY2BGR)
    h_main, w_main = color_frame.shape[:2]
    color_frame[10:10 + 150, w_main - 210:w_main - 10] = binary_bgr
    cv2.putText(color_frame, "Binary", (w_main - 210, 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


def main():
    global FORWARD_SPEED, BLACK_THRESHOLD, KP

    print("=" * 55)
    print("  Go2 + D435i 黑线循迹")
    print("=" * 55)
    print(f"  前进速度: {FORWARD_SPEED} m/s")
    print(f"  最大角速度: {MAX_ANGULAR_SPEED} rad/s")
    print(f"  比例系数 Kp: {KP}")
    print(f"  黑线阈值: {BLACK_THRESHOLD} (灰度)")
    print(f"  死区: ±{DEAD_ZONE} px")
    print("=" * 55)

    # ---- 1. 初始化 DDS 通道 ----
    if len(sys.argv) > 1:
        ChannelFactoryInitialize(0, sys.argv[1])
    else:
        ChannelFactoryInitialize(0)

    # ---- 2. 初始化运动客户端 ----
    from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient

    sport = SportClient()
    sport.SetTimeout(10.0)
    sport.Init()

    msc = MotionSwitcherClient()
    msc.SetTimeout(5.0)
    msc.Init()

    # 选择运动模式
    print("[INFO] 选择运动模式: normal")
    msc.SelectMode("normal")
    time.sleep(1.5)

    # 恢复站立（退出泄力状态）
    print("[INFO] 恢复舵机力度...")
    sport.RecoveryStand()
    time.sleep(2)

    # 站立
    print("[INFO] 让机器人站立...")
    sport.StandUp()
    time.sleep(2)

    # 设置速度等级
    sport.SpeedLevel(1)

    # ---- 3. 启动 D435i 摄像头 ----
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, FRAME_WIDTH, FRAME_HEIGHT,
                         rs.format.bgr8, 30)

    try:
        pipeline.start(config)
        print("[INFO] D435i 摄像头已启动")
    except RuntimeError as e:
        print(f"[ERROR] 无法连接摄像头: {e}")
        sport.StandDown()
        return

    print("[INFO] 循迹开始！按 ESC 停止")
    print("[WARN] 请随时准备按 ESC 紧急停止！")

    target_vyaw = 0.0
    stopped = False
    lost_count = 0
    MAX_LOST_FRAMES = 30  # 连续多少帧没检测到线就停下

    try:
        while True:
            # 获取摄像头帧
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue

            color_image = np.asanyarray(color_frame.get_data())
            gray = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            # 检测黑线
            offset, found = detect_black_line(gray)

            # 计算角速度（比例控制 + 死区）
            if found:
                lost_count = 0
                if abs(offset) > DEAD_ZONE:
                    target_vyaw = -KP * offset  # 负号：offset正(线偏右) → vyaw正(右转)
                    target_vyaw = np.clip(target_vyaw, -MAX_ANGULAR_SPEED, MAX_ANGULAR_SPEED)
                else:
                    target_vyaw = 0.0
            else:
                lost_count += 1
                if lost_count > MAX_LOST_FRAMES and not stopped:
                    sport.Move(0, 0, 0)
                    stopped = True
                    target_vyaw = 0.0
                    print("[WARN] 黑线丢失，机器人已停止")

            # 发送运动指令（已停止则不再发送）
            if not stopped:
                sport.Move(FORWARD_SPEED, 0, target_vyaw)

            # 绘制调试信息
            draw_debug(color_image, gray, offset, found)

            # 状态文字
            status_str = "STOPPED" if stopped else f"vyaw: {target_vyaw:+.3f} | lost: {lost_count}"
            cv2.putText(color_image, status_str,
                        (10, FRAME_HEIGHT - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.putText(color_image, "ESC: STOP", (FRAME_WIDTH - 150, FRAME_HEIGHT - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

            cv2.imshow("Line Follow", color_image)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                print("[INFO] 用户按下 ESC，停止循迹")
                break

            # 实时调参快捷键
            if key == ord('w'):
                BLACK_THRESHOLD = min(255, BLACK_THRESHOLD + 5)
                print(f"[TUNE] BLACK_THRESHOLD = {BLACK_THRESHOLD}")
            elif key == ord('e'):
                BLACK_THRESHOLD = max(0, BLACK_THRESHOLD - 5)
                print(f"[TUNE] BLACK_THRESHOLD = {BLACK_THRESHOLD}")
            elif key == ord('r'):
                FORWARD_SPEED = min(0.5, FORWARD_SPEED + 0.02)
                print(f"[TUNE] FORWARD_SPEED = {FORWARD_SPEED:.2f}")
            elif key == ord('f'):
                FORWARD_SPEED = max(0.02, FORWARD_SPEED - 0.02)
                print(f"[TUNE] FORWARD_SPEED = {FORWARD_SPEED:.2f}")
            elif key == ord('t'):
                KP = min(0.05, KP + 0.001)
                print(f"[TUNE] KP = {KP:.4f}")
            elif key == ord('g'):
                KP = max(0.001, KP - 0.001)
                print(f"[TUNE] KP = {KP:.4f}")

    except KeyboardInterrupt:
        print("\n[INFO] 收到中断信号")
    finally:
        # 安全停止
        print("[INFO] 正在停止机器人...")
        sport.StopMove()
        time.sleep(0.3)

        pipeline.stop()
        cv2.destroyAllWindows()
        print("[INFO] 程序已退出")


if __name__ == "__main__":
    main()
