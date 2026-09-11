#!/usr/bin/env python3
# ========================================================================================
# d435i_stream.py — D435i 画面推流到 Foxglove + 共享内存喂帧给视觉脚本
# ========================================================================================
#
# 运行环境: 上位机 RK3588（独占 D435i，其它脚本通过 d435i_client.py 共享内存取帧）
#
# 做两件事:
#   1. 把 color 1080p JPEG 推到 Foxglove WebSocket，你在电脑端用 Foxglove 看画面
#   2. 把最新对齐的 (color, depth) 写到 /dev/shm/d435i_frame.npz，供
#      solver.py / box_detector_rknn.py 取帧（不抢相机）
#
# 生命周期: 由 navigation_dog 在 OCR_SOLVE 启动、识别完 8 箱后停止
#
# 用法:
#   python3 d435i_stream.py
#   python3 d435i_stream.py --port 8765 --stream-fps 30 --shm-fps 15 --no-depth
#
# 电脑端:
#   安装 Foxglove Studio，连接 ws://<上位机IP>:8765，订阅 /d435i/color

import argparse
import signal
import sys
import time
import os

import cv2
import numpy as np

try:
    import pyrealsense2 as rs
    HAS_REALSENSE = True
except ImportError:
    HAS_REALSENSE = False

import foxglove
from foxglove.messages import CompressedImage, Timestamp

# 与 box_detector_rknn.py / box_detector_pt.py 的 RealSense 配置完全一致
COLOR_W, COLOR_H = 1920, 1080
DEPTH_W, DEPTH_H = 640, 480
FPS = 30

# 共享内存文件（d435i_client.py 读同一个路径）
SHM_PATH = "/dev/shm/d435i_frame.npz"
SHM_TMP = "/dev/shm/d435i_frame.npz.tmp"

running = True


def stop(*_):
    global running
    running = False
    print("\n🔴 停止信号，准备退出...")


def open_d435i():
    """打开 D435i: color 1080p bgr8 + depth 640x480 z16，depth 对齐到 color"""
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, COLOR_W, COLOR_H, rs.format.bgr8, FPS)
    config.enable_stream(rs.stream.depth, DEPTH_W, DEPTH_H, rs.format.z16, FPS)

    profile = pipeline.start(config)
    device = profile.get_device()
    color_sensor = device.first_color_sensor()
    color_sensor.set_option(rs.option.enable_auto_exposure, 1)

    align = rs.align(rs.stream.color)
    print(f"🟢 D435i 已启动: color {COLOR_W}x{COLOR_H} + depth {DEPTH_W}x{DEPTH_H} @ {FPS}fps")
    return pipeline, align


def write_shm(color_bgr, depth_frame, counter):
    """把最新对齐帧原子写入 shm（tmp + rename）。
    保存: color 的 JPEG（省内存）、depth 的 numpy、计数器（供客户端同步校验）。
    Windows 下没有 /dev/shm，落到脚本同目录（仅测试用，实际跑在 Linux 上）。"""
    ok, buf = cv2.imencode(".jpg", color_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return
    color_bytes = buf.tobytes()

    depth_arr = None
    if depth_frame is not None:
        depth_arr = np.asanyarray(depth_frame.get_data())

    try:
        np.savez(SHM_TMP,
                 color_jpg=color_bytes,
                 depth=depth_arr,
                 counter=counter)
        os.replace(SHM_TMP, SHM_PATH)
    except Exception as e:
        # Windows 测试环境 / 磁盘满 等，推流不受影响，只打日志
        print(f"⚠️ shm 写入失败（推流不受影响）: {e}")


def main():
    parser = argparse.ArgumentParser(description="D435i → Foxglove 推流 + shm 喂帧")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--stream-fps", type=float, default=30.0,
                        help="推流帧率（JPEG 编码 + 网络发送）")
    parser.add_argument("--shm-fps", type=float, default=15.0,
                        help="写共享内存帧率（视觉脚本不需要 30fps）")
    parser.add_argument("--no-depth", action="store_true",
                        help="不推深度伪彩图（默认不推，此参数保留兼容）")
    args = parser.parse_args()

    if not HAS_REALSENSE:
        print("❌ 未安装 pyrealsense2")
        sys.exit(1)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    # 1. 启动 Foxglove WebSocket 服务
    server = foxglove.start_server(
        host="0.0.0.0",
        port=args.port,
        name="d435i-server",
    )
    print(f"🟢 Foxglove server started: ws://0.0.0.0:{args.port}")

    # 2. 启动 D435i（独占）
    pipeline, align = open_d435i()

    stream_dt = 1.0 / max(args.stream_fps, 1e-3)
    shm_dt = 1.0 / max(args.shm_fps, 1e-3)
    last_stream = 0.0
    last_shm = 0.0
    counter = 0

    try:
        while running:
            now = time.monotonic()

            frameset = pipeline.wait_for_frames()
            aligned = align.process(frameset)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame:
                continue

            color_image = np.asanyarray(color_frame.get_data())

            # 写共享内存（喂给 solver / box_detector）
            if now - last_shm >= shm_dt:
                write_shm(color_image, depth_frame, counter)
                last_shm = now

            # 推流到 Foxglove
            if now - last_stream >= stream_dt:
                ok, buffer = cv2.imencode(".jpg", color_image,
                                          [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok:
                    foxglove.log(
                        "/d435i/color",
                        CompressedImage(
                            timestamp=Timestamp.now(),
                            frame_id="d435i_color",
                            format="jpeg",
                            data=buffer.tobytes(),
                        ),
                    )
                last_stream = now

            counter += 1

    except KeyboardInterrupt:
        print("\n🔴 Stopped")
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass
        # 清理共享内存
        for p in (SHM_PATH, SHM_TMP):
            try:
                os.remove(p)
            except OSError:
                pass
        print("🔴 已退出，shm 已清理")


if __name__ == "__main__":
    main()
