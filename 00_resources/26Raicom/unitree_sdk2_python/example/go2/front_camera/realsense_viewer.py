"""
Intel RealSense D435i 深度摄像头查看器

功能：
  - 实时显示 D435i 的 RGB 彩色画面 + 深度伪彩色图（左右并排）
  - 画面中心显示中心点的实际距离（米）
  - 按 ESC 退出
  - 按 S 键截图保存

依赖：
  pip install pyrealsense2 opencv-python numpy

用法：
  python realsense_viewer.py
"""

import cv2
import numpy as np
import pyrealsense2 as rs


def main():
    print("=" * 55)
    print("  Intel RealSense D435i 深度摄像头查看器")
    print("=" * 55)

    # 1. 配置数据流
    pipeline = rs.pipeline()
    config = rs.config()

    # RGB 彩色流: 640x480, 30fps
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    # 深度流: 640x480, 30fps
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)

    # 2. 启动摄像头
    try:
        profile = pipeline.start(config)
    except RuntimeError as e:
        print(f"[ERROR] 无法连接 D435i 摄像头: {e}")
        print("[INFO] 请检查 USB 连接是否正常")
        return

    # 获取深度传感器，用于读取深度标尺
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()
    print(f"[INFO] 深度标尺 (depth scale): {depth_scale:.4f} 米/单位")
    print(f"[INFO] 按 ESC 退出 | 按 S 截图")

    # 3. 深度对齐到彩色（使深度图与 RGB 图像素一一对应）
    align = rs.align(rs.stream.color)
    # 深度伪彩色渲染器
    colorizer = rs.colorizer()

    try:
        while True:
            # 等待一帧数据
            frames = pipeline.wait_for_frames()
            # 深度对齐到彩色
            aligned_frames = align.process(frames)

            depth_frame = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()

            if not depth_frame or not color_frame:
                continue

            # 转为 numpy 数组
            depth_colored = np.asanyarray(colorizer.colorize(depth_frame).get_data())
            color_image = np.asanyarray(color_frame.get_data())

            # 读取中心点的深度距离
            w, h = 640, 480
            center_dist = depth_frame.get_distance(w // 2, h // 2)  # 单位：米

            # === 左图: RGB ===
            cv2.putText(color_image, "RGB", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            # 画中心十字
            cv2.drawMarker(color_image, (w // 2, h // 2), (0, 255, 0),
                           cv2.MARKER_CROSS, 20, 2)

            # === 右图: 深度伪彩色 ===
            cv2.putText(depth_colored, "DEPTH", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.drawMarker(depth_colored, (w // 2, h // 2), (0, 255, 0),
                           cv2.MARKER_CROSS, 20, 2)

            # === 合并显示 ===
            combined = np.hstack((color_image, depth_colored))
            ch, cw = combined.shape[:2]

            # 底部信息栏
            cv2.putText(combined, f"Center Distance: {center_dist:.3f} m", (10, ch - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(combined, "ESC: Quit | S: Screenshot", (cw // 2 + 10, ch - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow("D435i - RGB + Depth", combined)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                break
            elif key == ord('s') or key == ord('S'):
                filename = "d435i_screenshot.jpg"
                cv2.imwrite(filename, combined)
                print(f"[INFO] 截图已保存: {filename}")

    finally:
        pipeline.stop()

    cv2.destroyAllWindows()
    print("[INFO] 程序已退出")


if __name__ == "__main__":
    main()
