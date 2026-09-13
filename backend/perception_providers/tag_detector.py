"""视觉基准标签（tag）位姿估计 + 停靠伺服 provider（route=external）。

**用户场景**：「接一个相机，识别 tag 码后调整自身位置」。本 provider 负责这件事里
**除了"从图像里找角点"之外的全部**：

1. **位姿逆解**：已知标签物理边长 + 相机内参 ⇒ 由 4 个角点像素坐标解出标签在相机光学系的
   位姿（单应 DLT 分解），再经 `sensor_suite` 的安装外参转到机身系（FLU）。
   正向投影/内外参全部复用 `backend/camera_projection.py`，并用它做**重投影误差**自校验
   （恢复出的位姿再投影回像素，与输入角点比对 —— 既是质量指标，也是测试抓手）。
2. **停靠判定**：复用 H10 的 `visual_dock_arrival`（3 cm / 3 cm / 2.5°、丢帧 0.7 s / 确认 2.5 s），
   不新造阈值。
3. **停靠伺服**：`visual_servo_command` —— 先对准（|yaw_err| ≥ 门限原地转），再按前向误差
   前进/后退到 `standoff_m`（与 H12 跟随控制器同形的律）。

**检测这一步**（图像 → 角点）需要可选依赖（`opencv-contrib-python` 的 aruco / `apriltag`）：
仓库当前环境**只有 numpy**，所以这里**不假装能检测**——传 `image` 进来会得到明确的
`requires_optional_dependency` 报错；传 `corners_px`（任何检测器的输出）即可走完几何与停靠。
注意 AprilTag 与 ArUco 是两套互不识别（family 不同）的码，选检测器时要与场景里的标签一致。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from backend.arrival_criteria import visual_dock_arrival, visual_dock_spec
from backend.camera_projection import (
    camera_frame_from_sensor,
    camera_profile,
    camera_profile_intrinsics,
    project_optical_points,
)

#: 角点顺序（顺时针，图像坐标）：左上 → 右上 → 右下 → 左下
CORNER_ORDER = ("tl", "tr", "br", "bl")
#: 标签本体系四角（单位坐标，乘 size/2），顺序与 CORNER_ORDER 对齐
TAG_LOCAL_CORNERS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))

#: 图像检测所需的可选依赖（本仓库当前不装：装了才能"从图检测"）
IMAGE_DETECTOR_PACKAGES = ("cv2", "apriltag", "pupil_apriltags")


def image_detector_available() -> dict[str, Any]:
    """图像检测器是否可用（不可用时**不提供假检测**）。"""
    import importlib.util

    found = {name: importlib.util.find_spec(name) is not None for name in IMAGE_DETECTOR_PACKAGES}
    available = any(found.values())
    return {
        "available": available,
        "packages": found,
        "hint": (
            "图像检测可用" if available else
            "未安装图像检测依赖（opencv-contrib-python 的 aruco 或 apriltag）；"
            "本 provider 只做「角点 → 位姿 → 停靠」的几何与伺服，不伪造检测结果。"
        ),
    }


def optical_to_flu(vector: Sequence[float]) -> tuple[float, float, float]:
    """相机光学系（x 右 y 下 z 前）→ 安装系 FLU（`flu_to_optical` 的逆）。"""
    x, y, z = float(vector[0]), float(vector[1]), float(vector[2])
    return (z, -x, -y)


def distortion_required(intrinsics: dict[str, Any]) -> bool:
    """档位是否带非零畸变（带畸变就必须先去畸变，本模块不做畸变逆运算）。"""
    coefficients = intrinsics.get("distortion") or []
    return any(abs(float(value)) > 1e-12 for value in coefficients)


def pose_from_corners(
    corners_px: Sequence[Sequence[float]],
    intrinsics: dict[str, Any],
    tag_size_m: float,
    *,
    undistorted: bool = False,
) -> dict[str, Any]:
    """4 角点像素 → 标签在**相机光学系**的位姿（单应 DLT 分解 + 重投影自校验）。

    ``undistorted=False`` 且档位带畸变 ⇒ 直接报错（不偷偷按理想针孔处理——那会把
    "没去畸变"变成静默误差）。
    """
    if float(tag_size_m) <= 0:
        raise ValueError("tag_size_m 必须为正（标签物理边长是标定输入，不是猜的）")
    points = np.asarray([[float(p[0]), float(p[1])] for p in corners_px], dtype=float)
    if points.shape != (4, 2):
        raise ValueError(f"需要 4 个角点（得到 {points.shape}），顺序 {CORNER_ORDER}")
    if not undistorted and distortion_required(intrinsics):
        raise ValueError(
            "该相机档位带畸变系数：请先把角点去畸变再传入（undistorted=True），"
            "本模块不做畸变逆运算（宁可报错，也不静默按理想针孔算）"
        )

    fx, fy = float(intrinsics["fx"]), float(intrinsics["fy"])
    cx, cy = float(intrinsics["cx"]), float(intrinsics["cy"])
    half = float(tag_size_m) / 2.0
    local = np.asarray(TAG_LOCAL_CORNERS, dtype=float) * half

    rows, values = [], []
    for (tag_x, tag_y), (u, v) in zip(local, points):
        xn, yn = (u - cx) / fx, (v - cy) / fy
        rows.append([tag_x, tag_y, 1.0, 0.0, 0.0, 0.0, -xn * tag_x, -xn * tag_y])
        values.append(xn)
        rows.append([0.0, 0.0, 0.0, tag_x, tag_y, 1.0, -yn * tag_x, -yn * tag_y])
        values.append(yn)
    solution, *_ = np.linalg.lstsq(np.asarray(rows), np.asarray(values), rcond=None)
    homography = np.array([
        [solution[0], solution[1], solution[2]],
        [solution[3], solution[4], solution[5]],
        [solution[6], solution[7], 1.0],
    ])
    # 注意：上面的 DLT 用的右手边是**归一化坐标** (u-cx)/fx，所以内参 K 已经被除掉了，
    # 这个 H 本身就等于 [r1 r2 t]/t_z（不是像素空间的 H）。像素空间单应才需要再乘 K⁻¹——
    # 早先多乘了一次，只在大倾角/偏心场景才会被重投影误差抓住（正中靶心时两种解都"自洽"）。
    col1, col2, col3 = homography[:, 0], homography[:, 1], homography[:, 2]
    norm = (np.linalg.norm(col1) + np.linalg.norm(col2)) / 2.0
    if norm <= 1e-12:
        raise ValueError("角点退化（四点共线或尺度为零），无法解位姿")
    scale = 1.0 / norm
    r1, r2, translation = scale * col1, scale * col2, scale * col3
    rotation = np.stack([r1, r2, np.cross(r1, r2)], axis=1)
    u_mat, _, vt_mat = np.linalg.svd(rotation)
    rotation = u_mat @ vt_mat  # 正交化（角点有噪声时防止漂移）
    if translation[2] <= 0.0:  # 标签必须在相机前方
        translation = -translation
        rotation = -rotation

    camera_points = [tuple(rotation @ np.array([x, y, 0.0]) + translation) for x, y in local]
    reprojected = project_optical_points(camera_points, intrinsics)
    errors = [
        math.hypot(float(item["u"]) - float(u), float(item["v"]) - float(v))
        for item, (u, v) in zip(reprojected, points)
        if item["valid"]
    ]
    return {
        "position_optical": [float(value) for value in translation],
        "rotation_optical": [[float(value) for value in row] for row in rotation],
        "in_plane_rotation_rad": math.atan2(float(rotation[1, 0]), float(rotation[0, 0])),
        "reprojection_error_px": (sum(errors) / len(errors)) if errors else None,
        "tag_size_m": float(tag_size_m),
    }


def visual_servo_command(
    tag_position_base: Sequence[float],
    yaw_error_rad: float,
    *,
    params: dict[str, Any],
) -> list[float]:
    """停靠伺服：先对准，再按前向误差前进/后退到 ``standoff_m``（同 H12 跟随控制器同形）。"""
    standoff = float(params["standoff_m"])
    yaw_gate = math.radians(float(params["yaw_gate_deg"]))
    max_wz = float(params["max_wz"])
    if abs(yaw_error_rad) >= yaw_gate:
        wz = max(-max_wz, min(max_wz, float(params["kp_yaw"]) * yaw_error_rad))
        return [0.0, 0.0, round(wz, 6)]
    forward_error = float(tag_position_base[0]) - standoff
    vx = float(params["kp_dist"]) * forward_error
    vx = max(-float(params["max_back_mps"]), min(float(params["max_vx"]), vx))
    wz = max(-max_wz, min(max_wz, float(params["kp_yaw"]) * yaw_error_rad))
    return [round(vx, 6), 0.0, round(wz, 6)]


class TagDetector:
    """provider 实现（生命周期形状：init / update / on_reset）。"""

    provider_id = "tag_detector"

    def init(self, params: dict[str, Any]) -> None:
        required = (
            "camera_profile_id", "sensor_id", "tag_size_m", "standoff_m",
            "kp_dist", "kp_yaw", "max_vx", "max_back_mps", "max_wz", "yaw_gate_deg", "actions",
        )
        missing = [key for key in required if key not in params]
        if missing:
            raise ValueError(f"tag_detector 缺参数 {missing}（阈值/标定只有注册表一处真值）")
        self.params = dict(params)
        profile = camera_profile(str(params["camera_profile_id"]))
        self.intrinsics = camera_profile_intrinsics(profile)
        from backend.sensor_suite import preset_sensors

        preset = str(params.get("sensor_preset") or "default")
        sensor = next((item.to_dict() for item in preset_sensors(preset)
                       if item.id == str(params["sensor_id"])), None)
        if sensor is None:
            raise ValueError(f"套件 {preset!r} 里没有传感器 {params['sensor_id']!r}（安装外参来自 sensor_suite）")
        self.sensor = sensor
        self.on_reset()

    def on_reset(self) -> None:
        self._last_seen_time: float | None = None
        self._clock_start: float | None = None
        self._last: dict[str, Any] | None = None
        self._readings = 0

    def _pose_base(self, position_optical: Sequence[float]) -> list[float]:
        frame = camera_frame_from_sensor(self.sensor)
        rotation = np.asarray(frame["rotation"], dtype=float)
        translate = np.asarray(frame["translate"], dtype=float)
        point = rotation @ np.asarray(optical_to_flu(position_optical), dtype=float) + translate
        return [float(value) for value in point]

    def update(self, reading: Any, time_s: float = 0.0) -> dict[str, Any]:
        """吃一帧检测结果：``{"tag_id": str, "corners_px": [[u,v]×4]}``（空/缺失表示本帧没看到）。"""
        if isinstance(reading, dict) and reading.get("image") is not None:
            state = image_detector_available()
            raise ValueError(
                "收到原始图像：本 provider 不做图像检测（需要可选依赖 "
                f"{', '.join(IMAGE_DETECTOR_PACKAGES)}；当前 {state['packages']}）。"
                "请传入检测器输出的 corners_px。"
            )
        payload = reading if isinstance(reading, dict) else {}
        corners = payload.get("corners_px")
        self._readings += 1
        detected = bool(corners) and len(corners) == 4

        if detected:
            self._last_seen_time = float(time_s)
            pose = pose_from_corners(
                corners, self.intrinsics, float(self.params["tag_size_m"]),
                undistorted=bool(payload.get("undistorted", False)),
            )
        else:
            pose = None

        if self._clock_start is None:
            self._clock_start = float(time_s)
        # 丢帧计时：见过就用"多久没见到"，从未见过就从第一次调用算起
        # （早先用 `or float(time_s)` 兜底，导致"从未见过"时恒为 0，丢失判定永远不触发）
        baseline = self._last_seen_time if self._last_seen_time is not None else self._clock_start
        lost_frame_s = 0.0 if detected else max(0.0, float(time_s) - float(baseline))
        standoff = float(self.params["standoff_m"])
        position_base = self._pose_base(pose["position_optical"]) if pose else None
        yaw_error = math.atan2(position_base[1], position_base[0]) if position_base else None
        dock = visual_dock_arrival(
            lateral_m=(position_base[1] if position_base else float("inf")),
            forward_m=((position_base[0] - standoff) if position_base else float("inf")),
            yaw_error_rad=(yaw_error if yaw_error is not None else float("inf")),
            lost_frame_s=lost_frame_s,
        )
        actions = dict(self.params.get("actions") or {})
        if not detected:
            action = dict(actions.get("lost") or {})
            command = [0.0, 0.0, 0.0]
        elif dock["docked"]:
            action = dict(actions.get("docked") or {})
            command = [0.0, 0.0, 0.0]
        else:
            action = dict(actions.get("detected") or {})
            command = visual_servo_command(position_base, float(yaw_error), params=self.params)

        self._last = {
            "provider_id": self.provider_id,
            "sensor": "rgb",
            "tag_id": payload.get("tag_id"),
            "detected": detected,
            "position_base": ({axis: round(value, 5) for axis, value in zip("xyz", position_base)}
                              if position_base else None),
            "distance_m": round(math.hypot(position_base[0], position_base[1]), 5) if position_base else None,
            "bearing_rad": round(float(yaw_error), 5) if yaw_error is not None else None,
            "pose": pose,
            "dock": dock,
            "servo_cmd": command,
            "action": action,
            "lost_frame_s": round(lost_frame_s, 4),
            "camera_profile_id": self.params["camera_profile_id"],
            "thresholds_source": "registry/arrival_criteria.json#visual_dock",
            "dock_thresholds": visual_dock_spec(),
            "image_detector": image_detector_available(),
            "readings": self._readings,
            "time_s": float(time_s),
        }
        return dict(self._last)

    @property
    def last_reading(self) -> dict[str, Any] | None:
        return dict(self._last) if self._last else None
