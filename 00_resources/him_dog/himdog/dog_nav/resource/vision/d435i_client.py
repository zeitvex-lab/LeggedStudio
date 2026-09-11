#!/usr/bin/env python3
# ========================================================================================
# d435i_client.py — 从 d435i_stream.py 共享内存取帧的客户端
# ========================================================================================
#
# 视觉脚本（solver.py / box_detector_rknn.py）用这个客户端取帧，
# 而不是自己打开 D435i（D435i 已被 d435i_stream.py 独占）。
#
# 用法:
#   from d435i_client import FrameClient, ShmUnavailable
#   client = FrameClient()
#   color, depth = client.grab()              # 最新对齐帧
#   color = client.grab_color()               # 单 color 帧（solver 用）
#   pairs = client.grab_burst(5, 0.033)       # 连取 5 帧（box_detector 投票用）
#
# 读不到 shm 时（d435i_stream 没跑）抛 ShmUnavailable，
# 调用方捕获后回退到直接打开 D435i（保证检测/OCR 行为退回现状）。

import time

import cv2
import numpy as np

# 与 d435i_stream.py 同一个 shm 路径
SHM_PATH = "/dev/shm/d435i_frame.npz"

# 计数器相同才算同一帧（color/depth 同步），超过这个差就重读
COUNTER_TOL = 0


class ShmUnavailable(RuntimeError):
    """共享内存不可用（d435i_stream 没运行 / 文件损坏）"""


class FrameClient:
    """从共享内存读取 D435i 最新对齐帧。

    所有 grab* 在连不上 shm 时抛 ShmUnavailable，调用方应捕获并回退。
    """

    def __init__(self, shm_path=SHM_PATH, timeout=5.0):
        self.shm_path = shm_path
        # 启动时等一等服务就绪（navigation_dog 启动 streamer 后才轮询创建 client）
        self.timeout = timeout

    def _load_npz(self):
        """读取 shm，返回 (color_jpg_bytes, depth_array_or_None, counter)。
        连不上/损坏抛 ShmUnavailable。"""
        try:
            data = np.load(self.shm_path, allow_pickle=True)
        except Exception as e:
            raise ShmUnavailable(f"读取 shm 失败: {e}")

        if "color_jpg" not in data or "counter" not in data:
            raise ShmUnavailable("shm 内容不全")

        color_jpg = data["color_jpg"].tobytes()
        depth = data["depth"] if "depth" in data else None
        counter = int(data["counter"])
        return color_jpg, depth, counter

    def grab(self):
        """取最新对齐 (color_bgr, depth) 帧。
        color 从 JPEG 解码；depth 是 numpy z16 数组（已与 color 对齐）。
        depth 可能为 None（streamer 未启 depth 流时）。
        返回 (color_bgr, depth_or_None)。"""
        color_jpg, depth, _ = self._load_npz()
        color = cv2.imdecode(np.frombuffer(color_jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if color is None:
            raise ShmUnavailable("JPEG 解码失败")
        return color, depth

    def grab_color(self):
        """取最新 color 单帧（solver OCR 用）"""
        color, _ = self.grab()
        return color

    def grab_burst(self, n, interval_s=0.033):
        """连取 n 帧对齐 (color, depth)，间隔 interval_s 秒。
        用于 box_detector 多帧投票。返回 [(color, depth), ...]，长度可能 < n。"""
        results = []
        last_counter = None
        deadline = time.monotonic() + self.timeout

        while len(results) < n:
            try:
                color_jpg, depth, counter = self._load_npz()
            except ShmUnavailable:
                if not results:
                    raise  # 一帧都没取到，直接抛
                time.sleep(interval_s)
                if time.monotonic() > deadline:
                    break
                continue

            # 跳过重复帧（等 streamer 写新帧）
            if last_counter is not None and counter - last_counter <= COUNTER_TOL:
                time.sleep(interval_s)
                if time.monotonic() > deadline:
                    break
                continue

            color = cv2.imdecode(np.frombuffer(color_jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if color is None:
                time.sleep(interval_s)
                continue
            results.append((color, depth))
            last_counter = counter

            if len(results) < n:
                time.sleep(interval_s)

        return results


def grab_with_fallback(grab_fn, fallback_fn, *args, **kwargs):
    """工具函数: 先试 grab_fn(优先 shm)，ShmUnavailable 则走 fallback_fn。
    方便 vision 脚本一行接入：
        frames, depths = grab_with_fallback(
            lambda: client.grab_burst(5),
            capture_frames_realsense, 10, 5, 1, cfg)
    """
    try:
        return grab_fn()
    except ShmUnavailable:
        return fallback_fn(*args, **kwargs)
