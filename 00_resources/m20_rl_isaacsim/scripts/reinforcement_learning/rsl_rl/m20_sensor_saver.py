"""
m20_sensor_saver.py

在仿真主循环里调用 SensorSaver.save(scene, step) 即可把：
  - 四路相机 RGB → PNG
  - 前/后雷达点云 → PCD (ASCII)
保存到各自子文件夹。

用法示例（在 m20_nav_app.py 的主循环里）：
    from m20_sensor_saver import SensorSaver
    saver = SensorSaver(root_dir="/tmp/m20_data", save_every_n_steps=10)
    ...
    while simulation_app.is_running():
        obs, _ = env.step(action)
        saver.save(env.scene, env.common_step_counter)
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_rgb_png(rgb_np: np.ndarray, filepath: Path):
    """将 HxWx4(RGBA) 或 HxWx3(RGB) uint8 数组保存为 PNG。"""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("请先安装 Pillow：pip install Pillow")

    if rgb_np.dtype != np.uint8:
        rgb_np = (np.clip(rgb_np, 0, 1) * 255).astype(np.uint8)

    if rgb_np.ndim == 3 and rgb_np.shape[2] == 4:
        img = Image.fromarray(rgb_np, mode="RGBA").convert("RGB")
    else:
        img = Image.fromarray(rgb_np, mode="RGB")

    img.save(str(filepath))


def _save_pcd_ascii(points: np.ndarray, filepath: Path):
    """
    将 Nx3 或 Nx4 的点云数组保存为 PCD ASCII 格式。
    points: float32/float64, 列顺序 [x, y, z] 或 [x, y, z, intensity]
    """
    if points.ndim != 2 or points.shape[1] < 3:
        raise ValueError(f"points 形状应为 Nx3 或 Nx4，实际为 {points.shape}")

    xyz = points[:, :3].astype(np.float32)
    has_intensity = points.shape[1] >= 4
    n = len(xyz)

    with open(filepath, "w") as f:
        # PCD 文件头
        f.write("# .PCD v0.7 - Point Cloud Data\n")
        f.write("VERSION 0.7\n")
        if has_intensity:
            f.write("FIELDS x y z intensity\n")
            f.write("SIZE 4 4 4 4\n")
            f.write("TYPE F F F F\n")
            f.write("COUNT 1 1 1 1\n")
        else:
            f.write("FIELDS x y z\n")
            f.write("SIZE 4 4 4\n")
            f.write("TYPE F F F\n")
            f.write("COUNT 1 1 1\n")
        f.write(f"WIDTH {n}\n")
        f.write("HEIGHT 1\n")
        f.write("VIEWPOINT 0 0 0 1 0 0 0\n")
        f.write(f"POINTS {n}\n")
        f.write("DATA ascii\n")

        # 点数据
        if has_intensity:
            intensity = points[:, 3].astype(np.float32)
            for i in range(n):
                f.write(f"{xyz[i,0]:.6f} {xyz[i,1]:.6f} {xyz[i,2]:.6f} {intensity[i]:.6f}\n")
        else:
            for i in range(n):
                f.write(f"{xyz[i,0]:.6f} {xyz[i,1]:.6f} {xyz[i,2]:.6f}\n")


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

class SensorSaver:
    """
    参数
    ----
    root_dir        : 数据根目录，子目录自动创建
    save_every_n_steps : 每隔多少个仿真 step 保存一次（避免 IO 成为瓶颈）
    camera_keys     : scene 里的相机属性名列表（对应 SceneCfg 里定义的字段名）
    lidar_keys      : scene 里的雷达属性名列表
    """

    CAMERA_KEYS = ["front_camera", "rear_camera", "left_camera", "right_camera"]
    LIDAR_KEYS  = ["front_lidar",  "rear_lidar"]

    def __init__(
        self,
        root_dir: str = "/home/user/m20_sensor_data",
        save_every_n_steps: int = 10,
        camera_keys: list[str] | None = None,
        lidar_keys: list[str] | None = None,
    ):
        self.root = Path(root_dir)
        self.every = save_every_n_steps
        self.camera_keys = camera_keys or self.CAMERA_KEYS
        self.lidar_keys  = lidar_keys  or self.LIDAR_KEYS

        # 预建目录
        for key in self.camera_keys:
            _ensure_dir(self.root / key)
        for key in self.lidar_keys:
            _ensure_dir(self.root / key)

        print(f"[SensorSaver] 数据将保存到: {self.root}")
        print(f"[SensorSaver] 相机: {self.camera_keys}")
        print(f"[SensorSaver] 雷达: {self.lidar_keys}")
        print(f"[SensorSaver] 每 {self.every} 步保存一次")

    # ------------------------------------------------------------------
    # 对外接口：在主循环里调用
    # ------------------------------------------------------------------
    def save(self, scene, step: int):
        """
        scene : env.scene  (isaaclab InteractiveScene)
        step  : env.common_step_counter 或任意递增整数
        """
        if step % self.every != 0:
            return

        self._save_cameras(scene, step)
        self._save_lidars(scene, step)

    # ------------------------------------------------------------------
    # 内部：相机
    # ------------------------------------------------------------------
    def _save_cameras(self, scene, step: int):
        for key in self.camera_keys:
            try:
                cam = scene.sensors.get(key)
                if cam is None:
                    # 兼容直接用属性访问的场景
                    cam = getattr(scene, key, None)
                if cam is None:
                    print(f"[SensorSaver] 找不到相机 '{key}'，跳过")
                    continue

                # IsaacLab Camera.data.output 是 dict，key 为 data_types 里的字符串
                rgb = cam.data.output.get("rgb")          # shape: (N_envs, H, W, 4) uint8
                if rgb is None:
                    print(f"[SensorSaver] {key} 无 rgb 数据，跳过")
                    continue

                # 只取第 0 个 env
                img_np = rgb[0].cpu().numpy() if hasattr(rgb[0], "cpu") else np.array(rgb[0])

                fname = self.root / key / f"{step:08d}.png"
                _save_rgb_png(img_np, fname)

            except Exception as e:
                print(f"[SensorSaver] 保存相机 '{key}' 失败: {e}")

    # ------------------------------------------------------------------
    # 内部：雷达（RTX Lidar 通过 annotator 拿点云）
    # ------------------------------------------------------------------
    def _init_lidar_annotators(self, scene):
        import omni.replicator.core as rep
        import omni.usd

        lidar_prim_map = {
            "front_lidar": "/World/envs/env_0/Robot/base_link/front_lidar_mount/front_lidar",
            "rear_lidar":  "/World/envs/env_0/Robot/base_link/rear_lidar_mount/rear_lidar",
        }

        self._lidar_annotators = {}
        stage = omni.usd.get_context().get_stage()

        for key in self.lidar_keys:
            prim_path = lidar_prim_map.get(key)
            if not stage.GetPrimAtPath(prim_path).IsValid():
                print(f"[SensorSaver] 错误：雷达路径不存在 {prim_path}")
                continue

            try:
                # 1. 创建渲染产品。RTX Lidar 必须设置为 [1, 1]
                rp = rep.create.render_product(prim_path, [1, 1])
                
                # 2. 使用你系统列表中存在的正确名称
                # 注意：IsaacCreateRTXLidarScanBuffer 是输出原始极坐标数据的 buffer
                annotator = rep.AnnotatorRegistry.get_annotator("IsaacCreateRTXLidarScanBuffer")
                annotator.attach([rp])
                
                self._lidar_annotators[key] = annotator
                print(f"[SensorSaver] 雷达 annotator 绑定成功: {key} → {prim_path}")
            except Exception as e:
                print(f"[SensorSaver] 绑定雷达 {key} 失败: {e}")

    def _save_lidars(self, scene, step: int):
        if not hasattr(self, "_lidar_annotators"):
            self._init_lidar_annotators(scene)

        for key, annotator in self._lidar_annotators.items():
            try:
                # 获取数据
                data = annotator.get_data()
                
                # 【关键检查】如果渲染产品还没准备好，data 会是空的或 None
                if data is None or len(data) == 0:
                    # 这就是日志中 "Render product not valid" 对应的 Python 表现
                    # 属于正常热身阶段，直接跳过即可
                    continue

                # IsaacCreateRTXLidarScanBuffer 返回的是结构化数组
                # 包含 distance, azimuth, elevation, intensity
                dist = data["distance"]
                az = data["azimuth"]
                el = data["elevation"]
                inten = data["intensity"]

                # 极坐标转笛卡尔坐标 (XYZ)
                # 注意：RTX Lidar 的坐标系通常是：x向前, y向左, z向上
                x = dist * np.cos(el) * np.cos(az)
                y = dist * np.cos(el) * np.sin(az)
                z = dist * np.sin(el)

                pts_np = np.stack([x, y, z, inten], axis=1)  # 组合成 Nx4

                # 保存到文件
                save_path = self.root / key
                save_path.mkdir(parents=True, exist_ok=True)
                fname = save_path / f"{step:08d}.pcd"
                
                # 使用你之前的 _save_pcd_ascii 函数保存
                self._save_pcd_ascii(pts_np, fname)
                
            except Exception as e:
                # 如果是由于数据还没生成导致的 Key错误，我们也捕获它
                pass