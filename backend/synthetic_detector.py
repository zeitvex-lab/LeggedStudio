"""合成检测器：把「已知几何的标签角点」投成**带声明式噪声**的像素。

**它是什么、不是什么**（这条边界很重要，别把它读成"我们有了图像识别"）：

* **是**一个**检测器模型**：给定标签在相机光学系的 4 个角点，输出"检测器会给出的"
  ``corners_px``，并按参数加**像素噪声 / 丢帧 / 缺角**——用来模拟检测器**不完美**这一事实。
* **不是**图像识别。它**不读任何像素**、不跑 aruco/apriltag，也不假装"从图里认出了标签"。
  真图像检测仍需 ``opencv-contrib-python`` 的 aruco 或 ``apriltag``；
  ``tag_detector.image_detector_available()`` 会如实报 False（本仓当前环境即如此）。

**为什么需要它**：``tag_detector.py`` 只做「角点 → 位姿 → 停靠伺服」，而"角点从哪来"在仿真里
**没人负责**——于是这条链路只有单点测试、没有**闭环**。本模块让它能在不装任何可选依赖的前提下
跑通并单测：

    标签真值位姿 → 4 角点（光学系） → [本模块：投影 + 噪声] → corners_px
        → tag_detector.pose_from_corners → 位姿 + 重投影误差 → 停靠伺服

噪声是**声明的仿真参数**（``DetectionNoise`` 的四个字段），不是"把完美投影当检测结果"——
所以不违反上游「不伪造检测结果」的约定。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Sequence

from backend.camera_projection import project_optical_points

#: 与 ``tag_detector`` 的角点顺序一致（左上→右上→右下→左下）
CORNER_COUNT = 4

#: 默认随机种子：固定 ⇒ 回归可复现（"每次抽新题"的仿真没法当门禁）
DEFAULT_SEED = 0


@dataclass(frozen=True)
class DetectionNoise:
    """检测器不完美程度的**声明式**参数。

    全部为 0 时退化成"理想检测"（近似真实检测器的上界），可用于验证几何链路本身。
    """

    #: 像素级高斯噪声标准差（检测器定位精度）
    sigma_px: float = 0.0
    #: 系统性像素偏移（等效于"畸变没校正干净"这类偏置，不随帧变化）
    bias_px: float = 0.0
    #: 整帧丢失概率（对应"这一帧没看到标签"）
    drop_frame_rate: float = 0.0
    #: 单角点丢失概率（对应部分遮挡；缺任何一个角点都判为本帧未检测）
    drop_corner_rate: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "sigma_px": self.sigma_px,
            "bias_px": self.bias_px,
            "drop_frame_rate": self.drop_frame_rate,
            "drop_corner_rate": self.drop_corner_rate,
        }

    def clamped(self) -> "DetectionNoise":
        """把概率夹到 [0,1]、噪声取绝对值——越界参数不该悄悄变成"永远丢帧"。"""
        return DetectionNoise(
            sigma_px=abs(float(self.sigma_px)),
            bias_px=abs(float(self.bias_px)),
            drop_frame_rate=min(1.0, max(0.0, float(self.drop_frame_rate))),
            drop_corner_rate=min(1.0, max(0.0, float(self.drop_corner_rate))),
        )


def synthetic_detector_selftest() -> dict[str, Any]:
    """自检：无噪声时"投影→检测→反解"应还原真值位姿（闭环几何一致）。"""
    from backend.camera_projection import camera_profile, camera_profile_intrinsics
    from backend.perception_providers.tag_detector import pose_from_corners

    intrinsics = camera_profile_intrinsics(camera_profile("ideal-pinhole-1920x1080"))
    tag_size_m = 0.16
    truth = (0.10, -0.04, 1.20)  # 标签在相机光学系的位置
    half = tag_size_m / 2.0
    corners = [
        (truth[0] + dx * half, truth[1] + dy * half, truth[2])
        for dx, dy in ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    ]
    detected = detect_from_optical(corners, intrinsics, noise=DetectionNoise(), z_min=0.1)
    if not detected["detected"]:
        return {"verdict": "fail", "reason": f"理想条件下未检测：{detected['reason']}"}
    pose = pose_from_corners(detected["corners_px"], intrinsics, tag_size_m, undistorted=True)
    error = max(abs(float(a) - b) for a, b in zip(pose["position_optical"], truth))
    return {
        "verdict": "pass" if error < 1e-6 else "fail",
        "position_error_m": error,
        "reprojection_error_px": pose.get("reprojection_error_px"),
        "truth": list(truth),
        "recovered": [round(float(v), 9) for v in pose["position_optical"]],
    }


def detect_from_optical(
    corners_optical: Sequence[Sequence[float]],
    intrinsics: dict[str, Any],
    *,
    noise: DetectionNoise | None = None,
    rng: random.Random | None = None,
    z_min: float = 0.1,
) -> dict[str, Any]:
    """光学系角点 →（带噪声的）像素角点。

    返回 ``{"detected": bool, "reason": str, "corners_px": [[u,v]×4] | None, ...}``。
    **未检测时 ``corners_px`` 为 ``None``** —— 调用方应把这一帧当"没看到"，
    而不是拿一组假角点继续算（那才是"伪造检测"）。

    ``reason`` 取值：``ok`` / ``bad_input`` / ``dropped_frame`` / ``unprojectable`` /
    ``corner_missing``。
    """
    spec = (noise or DetectionNoise()).clamped()
    generator = rng if rng is not None else random.Random(DEFAULT_SEED)

    points = [[float(p[0]), float(p[1]), float(p[2])] for p in corners_optical]
    if len(points) != CORNER_COUNT:
        return _miss("bad_input", spec, f"需要 {CORNER_COUNT} 个角点，得到 {len(points)}")
    if spec.drop_frame_rate > 0.0 and generator.random() < spec.drop_frame_rate:
        return _miss("dropped_frame", spec, "本帧整帧丢失")

    projected = project_optical_points(points, intrinsics, z_min=z_min)
    if len(projected) != CORNER_COUNT or not all(item.get("valid") for item in projected):
        # 深度不足 / 投影无效：真实检测器也看不到（例如标签贴到镜头前）
        return _miss("unprojectable", spec, "存在无效投影（深度不足或无法成像）")

    corners_px = []
    for item in projected:
        u = float(item["u"])
        v = float(item["v"])
        if spec.drop_corner_rate > 0.0 and generator.random() < spec.drop_corner_rate:
            return _miss("corner_missing", spec, "单角点丢失（遮挡）")
        if spec.bias_px:
            u += spec.bias_px
            v += spec.bias_px
        if spec.sigma_px:
            u += generator.gauss(0.0, spec.sigma_px)
            v += generator.gauss(0.0, spec.sigma_px)
        corners_px.append([u, v])

    return {
        "detected": True,
        "reason": "ok",
        "corners_px": corners_px,
        "noise": spec.as_dict(),
        # 明文标注：这是**合成**检测，不是图像识别（防止下游把它当真实能力）
        "source": "synthetic_detector",
        "image_based": False,
    }


def _miss(reason: str, spec: DetectionNoise, detail: str) -> dict[str, Any]:
    return {
        "detected": False,
        "reason": reason,
        "corners_px": None,
        "detail": detail,
        "noise": spec.as_dict(),
        "source": "synthetic_detector",
        "image_based": False,
    }


def corners_from_tag_pose(
    position_optical: Sequence[float],
    *,
    tag_size_m: float,
    in_plane_rotation_rad: float = 0.0,
) -> list[list[float]]:
    """由标签在光学系的位姿生成 4 个角点（顺序与 ``tag_detector`` 一致）。

    这是"场景侧"该做的换算（真值 → 角点），与检测噪声无关，所以单独一个函数。
    """
    import math

    half = float(tag_size_m) / 2.0
    cos_a, sin_a = math.cos(float(in_plane_rotation_rad)), math.sin(float(in_plane_rotation_rad))
    x, y, z = (float(position_optical[0]), float(position_optical[1]), float(position_optical[2]))
    corners = []
    for dx, dy in ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)):
        local_x = dx * half
        local_y = dy * half
        corners.append([
            x + cos_a * local_x - sin_a * local_y,
            y + sin_a * local_x + cos_a * local_y,
            z,
        ])
    return corners
