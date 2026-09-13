"""相机几何：内参解析、外参变换、点云/目标框投影、深度反投影、目标判定。

面向高级仿真的「外部传感器」几何层，输入全部来自 :mod:`backend.sensor_suite`
的传感器声明（类型 / 挂载体 / 外参 / 频率 / 内外参），因此**不依赖任何 GPU、ROS2
或真机数据**，可以离线单测。

坐标系约定（与 MATRiX v1.0.13 文档一致，见 ``2.6`` 节的 RoamerX 适配配方）：

- **机身系 base_link**：FLU —— x 前、y 左、z 上，单位米；
- **传感器安装系**：``rotation``（roll/pitch/yaw，度）按 ZYX 顺序构成
  :func:`mount_rotation`，语义是「把安装系轴映射到机身系」；
  机身系点变换到安装系：``p_sensor = Rᵀ (p_base − t)``；
- **相机光学系**：x 右、y 下、z 前（OpenCV/常规视觉约定）。
  安装系 FLU → 光学系：``x_opt = −y_flu``、``y_opt = −z_flu``、``z_opt = x_flu``，
  即默认安装（rotation 全 0）的相机朝机身 **+x（正前方）** 看。

内参解析遵循 MATRiX 的声明惯例：``fov`` 为**水平**视场角；``fx``/``fy`` 为 0 表示
未标定，``cx``/``cy`` 为负表示未标定 —— 此时按针孔模型与像素质心约定推导
（``cx = (W−1)/2``、``fy = fx``），使水平视场边缘恰好落在 ``u = 0`` 与 ``u = W−1``：

    fx = (W − 1) / (2 · tan(hfov / 2))

度量单位统一为米与像素；深度图按 ``z``（前向距离）解释。
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from fastapi import APIRouter, HTTPException

from backend.runtime_registry import load_registry

router = APIRouter(prefix="/api/perception/projection", tags=["perception"])

Point3 = Sequence[float]

#: 相机前方多少米以内不投影（针孔模型在 z→0 处发散）
DEFAULT_Z_MIN = 1e-3


# --------------------------------------------------------------------------
# 内参 / 外参
# --------------------------------------------------------------------------
def resolve_intrinsics(
    width: int,
    height: int,
    *,
    fov_deg: float | None = None,
    fx: float = 0.0,
    fy: float = 0.0,
    cx: float = -1.0,
    cy: float = -1.0,
) -> dict[str, Any]:
    """把 MATRiX 风格的内参声明解析成完整针孔内参。

    ``fov_deg`` 为水平视场角；``fx``/``fy`` 为 0、``cx``/``cy`` 为负时按视场角与
    像素质心推导。返回 ``fx, fy, cx, cy, width, height, hfov_deg, source``。
    """
    if width < 2 or height < 2:
        raise ValueError("width/height 至少为 2")
    resolved_fx = float(fx) if fx and fx > 0 else 0.0
    resolved_fy = float(fy) if fy and fy > 0 else 0.0
    if resolved_fx <= 0:
        if not fov_deg or fov_deg <= 0 or fov_deg >= 180:
            raise ValueError("fx 未标定时必须给出 0 < fov_deg < 180")
        resolved_fx = (width - 1) / (2.0 * math.tan(math.radians(fov_deg) / 2.0))
    if resolved_fy <= 0:
        resolved_fy = resolved_fx  # 方形像素假设
    resolved_cx = float(cx) if cx is not None and cx >= 0 else (width - 1) / 2.0
    resolved_cy = float(cy) if cy is not None and cy >= 0 else (height - 1) / 2.0
    hfov = 2.0 * math.degrees(math.atan((width - 1) / (2.0 * resolved_fx)))
    vfov = 2.0 * math.degrees(math.atan((height - 1) / (2.0 * resolved_fy)))
    return {
        "width": width,
        "height": height,
        "fx": resolved_fx,
        "fy": resolved_fy,
        "cx": resolved_cx,
        "cy": resolved_cy,
        "hfov_deg": hfov,
        "vfov_deg": vfov,
        "source": "derived_from_fov" if not fx else "calibrated",
    }


# --------------------------------------------------------------------------
# 相机档位（H8）：理想针孔口径 与 真机标定口径（含畸变项）
# --------------------------------------------------------------------------
def camera_profiles() -> list[dict[str, Any]]:
    """全部相机档位（``registry/cameras.json``，单一真值）。"""
    payload = load_registry("cameras")
    profiles = payload.get("profiles") or []
    if not profiles:
        raise ValueError("registry/cameras.json 未声明任何档位")
    return [dict(item) for item in profiles]


def camera_profile(profile_id: str) -> dict[str, Any]:
    """按 id 取一个相机档位；不存在即报错并列出可选值。"""
    for item in camera_profiles():
        if str(item.get("id")) == profile_id:
            return item
    raise KeyError(f"未知相机档位 {profile_id!r}；可选：{', '.join(str(p.get('id')) for p in camera_profiles())}")


def camera_profile_intrinsics(profile: dict[str, Any]) -> dict[str, Any]:
    """把档位声明解析成完整内参（含畸变模型与系数，供投影直接消费）。"""
    resolution = profile.get("resolution") or {}
    declared = profile.get("intrinsics") or {}
    resolved = resolve_intrinsics(
        int(resolution.get("width") or 0),
        int(resolution.get("height") or 0),
        fov_deg=profile.get("fov_deg"),
        fx=float(declared.get("fx") or 0.0),
        fy=float(declared.get("fy") or 0.0),
        cx=float(declared.get("cx", -1.0)),
        cy=float(declared.get("cy", -1.0)),
    )
    resolved["profile_id"] = profile.get("id")
    resolved["label"] = profile.get("label")
    resolved["kind"] = profile.get("kind")
    resolved["scope"] = profile.get("scope")
    resolved["distortion_model"] = str(profile.get("model") or "pinhole")
    resolved["distortion"] = [float(c) for c in (profile.get("distortion") or [])]
    resolved["evidence"] = profile.get("evidence") or {}
    return resolved


def distort_normalized(
    x: float,
    y: float,
    *,
    model: str = "pinhole",
    coefficients: Sequence[float] | None = None,
) -> tuple[float, float]:
    """归一化像平面点 ``(x/z, y/z)`` → 畸变后的归一化点。

    支持两种模型（与 ``registry/cameras.json`` 的 ``distortion_models`` 对应）：

    * ``brown_conrady``：``[k1, k2, p1, p2, k3]``，径向 + 切向（OpenCV plumb-bob）；
    * ``fisheye_equidistant``：``[k1, k2, k3, k4]``，Kannala-Brandt：
      ``θd = θ·(1 + k1θ² + k2θ⁴ + k3θ⁶ + k4θ⁸)``。

    系数全为 0（或模型为 ``pinhole``）时原样返回，因此「理想针孔」与「畸变真实」
    共用一条代码路径，差别只在数据。
    """
    coeffs = [float(c) for c in (coefficients or [])]
    if model in ("", "pinhole") or not any(abs(c) > 0.0 for c in coeffs):
        return x, y
    if model == "brown_conrady":
        k1, k2, p1, p2, k3 = (coeffs + [0.0] * 5)[:5]
        r2 = x * x + y * y
        radial = 1.0 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
        return (
            x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x),
            y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y,
        )
    if model == "fisheye_equidistant":
        k1, k2, k3, k4 = (coeffs + [0.0] * 4)[:4]
        radius = math.hypot(x, y)
        if radius < 1e-12:
            return x, y
        theta = math.atan(radius)
        theta2 = theta * theta
        theta_d = theta * (1.0 + k1 * theta2 + k2 * theta2**2 + k3 * theta2**3 + k4 * theta2**4)
        scale = theta_d / radius
        return x * scale, y * scale
    raise ValueError(f"未知畸变模型 {model!r}（可选 brown_conrady / fisheye_equidistant / pinhole）")


def distortion_impact(
    profile_id: str,
    *,
    grid: int = 9,
) -> dict[str, Any]:
    """同一 K 下「畸变关 vs 畸变开」的像素位移统计（H8 的验收口径）。

    刻意**不比对两组不同内参**（那会把焦距口径差异混进来）：这里用同一个档位的
    内参，只把畸变系数置零作为「理想针孔」基线，因此量出来的就是**镜头畸变本身**
    造成的像素位移。返回最大/均值/RMS 位移、四角与边缘位移，以及判定。
    """
    profile = camera_profile(profile_id)
    resolved = camera_profile_intrinsics(profile)
    width, height = int(resolved["width"]), int(resolved["height"])
    fx, fy = float(resolved["fx"]), float(resolved["fy"])
    model = str(resolved["distortion_model"])
    coeffs = list(resolved["distortion"])

    # 在理想针孔口径下覆盖整幅画面的归一化采样网格
    u_max = (width - 1) - float(resolved["cx"])
    u_min = -float(resolved["cx"])
    v_max = (height - 1) - float(resolved["cy"])
    v_min = -float(resolved["cy"])
    steps = max(3, int(grid))
    samples: list[dict[str, Any]] = []
    for iy in range(steps):
        y_off = v_min + (v_max - v_min) * iy / (steps - 1)
        for ix in range(steps):
            x_off = u_min + (u_max - u_min) * ix / (steps - 1)
            ideal_u = x_off + float(resolved["cx"])
            ideal_v = y_off + float(resolved["cy"])
            norm_x, norm_y = x_off / fx, y_off / fy
            dx, dy = distort_normalized(norm_x, norm_y, model=model, coefficients=coeffs)
            real_u, real_v = fx * dx + float(resolved["cx"]), fy * dy + float(resolved["cy"])
            if not (math.isfinite(real_u) and math.isfinite(real_v)):
                continue
            samples.append(
                {
                    "ideal": [ideal_u, ideal_v],
                    "distorted": [real_u, real_v],
                    "delta_px": math.hypot(real_u - ideal_u, real_v - ideal_v),
                    "inside": 0.0 <= real_u <= width - 1 and 0.0 <= real_v <= height - 1,
                }
            )

    deltas = [item["delta_px"] for item in samples]
    if not deltas:
        raise ValueError(f"档位 {profile_id} 的采样全落在模型奇点，无法比较（检查畸变系数）")
    mean = sum(deltas) / len(deltas)
    rms = math.sqrt(sum(d * d for d in deltas) / len(deltas))
    worst = max(samples, key=lambda item: item["delta_px"])
    max_delta = worst["delta_px"]

    corners = [
        item
        for item in samples
        if abs(item["ideal"][0] - (0.0 if item["ideal"][0] < width / 2 else width - 1)) < 1e-9
        and abs(item["ideal"][1] - (0.0 if item["ideal"][1] < height / 2 else height - 1)) < 1e-9
    ]
    return {
        "profile": profile_id,
        "model": model,
        "coefficients": coeffs,
        "resolution": {"width": width, "height": height},
        "samples": len(samples),
        "max_delta_px": max_delta,
        "mean_delta_px": mean,
        "rms_delta_px": rms,
        "max_at": worst["ideal"],
        "corner_delta_px": [round(item["delta_px"], 2) for item in corners],
        "inside_frame_ratio": sum(1 for item in samples if item["inside"]) / len(samples),
        "distortion_matters": max_delta >= 1.0,
        "note": "位移 = 同一内参下「畸变开 - 畸变关」，因此只反映镜头畸变本身",
    }


def mount_rotation(roll_deg: float = 0.0, pitch_deg: float = 0.0, yaw_deg: float = 0.0) -> list[list[float]]:
    """ZYX 顺序的安装旋转矩阵：把安装系轴映射到机身系（度）。"""
    r, p, y = (math.radians(roll_deg), math.radians(pitch_deg), math.radians(yaw_deg))
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy_, sy = math.cos(y), math.sin(y)
    return [
        [cy_ * cp, cy_ * sp * sr - sy * cr, cy_ * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy_ * cr, sy * sp * cr - cy_ * sr],
        [-sp, cp * sr, cp * cr],
    ]


def _mat_transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [[matrix[j][i] for j in range(3)] for i in range(3)]


def _mat_vec(matrix: list[list[float]], vector: Sequence[float]) -> tuple[float, float, float]:
    x, y, z = float(vector[0]), float(vector[1]), float(vector[2])
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z,
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z,
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z,
    )


def flu_to_optical(vector: Sequence[float]) -> tuple[float, float, float]:
    """安装系 FLU（x 前 y 左 z 上）→ 相机光学系（x 右 y 下 z 前）。"""
    x, y, z = float(vector[0]), float(vector[1]), float(vector[2])
    return (-y, -z, x)


def camera_frame_from_sensor(sensor: dict[str, Any]) -> dict[str, Any]:
    """从 sensor_suite 的传感器声明解析出相机几何（外参旋转的逆 + 平移）。"""
    position = dict(sensor.get("position") or {})
    rotation = dict(sensor.get("rotation") or {})
    rot = mount_rotation(
        float(rotation.get("roll") or 0.0),
        float(rotation.get("pitch") or 0.0),
        float(rotation.get("yaw") or 0.0),
    )
    return {
        "translate": (float(position.get("x") or 0.0), float(position.get("y") or 0.0), float(position.get("z") or 0.0)),
        "rotation_inverse": _mat_transpose(rot),
        "rotation": rot,
        "mount": sensor.get("mount") or "base_link",
    }


# --------------------------------------------------------------------------
# 投影
# --------------------------------------------------------------------------
def base_points_to_optical(points: Iterable[Point3], sensor: dict[str, Any]) -> list[tuple[float, float, float]]:
    """机身系点（FLU）→ 相机光学系点。"""
    frame = camera_frame_from_sensor(sensor)
    tx, ty, tz = frame["translate"]
    rot_inv = frame["rotation_inverse"]
    out: list[tuple[float, float, float]] = []
    for point in points:
        relative = (float(point[0]) - tx, float(point[1]) - ty, float(point[2]) - tz)
        out.append(flu_to_optical(_mat_vec(rot_inv, relative)))
    return out


def project_optical_points(
    points: Iterable[Point3],
    intrinsics: dict[str, Any],
    *,
    z_min: float = DEFAULT_Z_MIN,
    distortion_model: str | None = None,
    distortion_coefficients: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    """光学系点 → 像素。返回逐点 ``{u, v, depth, inside, valid}``；``depth ≤ z_min`` 视为无效。

    畸变（H8）：``distortion_model`` / ``distortion_coefficients`` 缺省时从
    ``intrinsics`` 里读（:func:`camera_profile_intrinsics` 会把档位的
    ``distortion_model`` 与 ``distortion`` 一并带上），因此**既有调用方零改动**，
    而带畸变的档位自动走畸变路径。系数全零即退化为理想针孔。
    """
    fx, fy = float(intrinsics["fx"]), float(intrinsics["fy"])
    cx, cy = float(intrinsics["cx"]), float(intrinsics["cy"])
    width, height = int(intrinsics["width"]), int(intrinsics["height"])
    model = distortion_model if distortion_model is not None else str(intrinsics.get("distortion_model") or "pinhole")
    coefficients = (
        distortion_coefficients
        if distortion_coefficients is not None
        else (intrinsics.get("distortion") or [])
    )
    results: list[dict[str, Any]] = []
    for point in points:
        x, y, z = float(point[0]), float(point[1]), float(point[2])
        if not all(map(math.isfinite, (x, y, z))) or z <= z_min:
            results.append({"u": None, "v": None, "depth": z, "inside": False, "valid": False})
            continue
        dx, dy = distort_normalized(x / z, y / z, model=model, coefficients=coefficients)
        u = fx * dx + cx
        v = fy * dy + cy
        results.append(
            {
                "u": u,
                "v": v,
                "depth": z,
                "inside": 0.0 <= u <= width - 1 and 0.0 <= v <= height - 1,
                "valid": True,
            }
        )
    return results


def project_base_points(
    points: Iterable[Point3],
    sensor: dict[str, Any],
    intrinsics: dict[str, Any],
    *,
    z_min: float = DEFAULT_Z_MIN,
) -> list[dict[str, Any]]:
    """机身系点 → 像素（外参 + 内参一步到位）。"""
    return project_optical_points(base_points_to_optical(points, sensor), intrinsics, z_min=z_min)


def project_box(
    center: Sequence[float],
    half_extents: Sequence[float],
    sensor: dict[str, Any],
    intrinsics: dict[str, Any],
    *,
    z_min: float = DEFAULT_Z_MIN,
) -> dict[str, Any]:
    """轴对齐长方体（机身系中心 + 半尺寸）→ 2D 包围框。

    返回 ``{bbox:[u0,v0,u1,v1] | None, corners_visible, corners_total, any_visible}``。
    """
    cx_, cy_, cz_ = float(center[0]), float(center[1]), float(center[2])
    hx, hy, hz = float(half_extents[0]), float(half_extents[1]), float(half_extents[2])
    corners = [
        (cx_ + sx * hx, cy_ + sy * hy, cz_ + sz * hz)
        for sx in (-1.0, 1.0)
        for sy in (-1.0, 1.0)
        for sz in (-1.0, 1.0)
    ]
    projected = project_base_points(corners, sensor, intrinsics, z_min=z_min)
    visible = [item for item in projected if item["valid"]]
    if not visible:
        return {"bbox": None, "corners_visible": 0, "corners_total": len(corners), "any_visible": False}
    us = [item["u"] for item in visible]
    vs = [item["v"] for item in visible]
    return {
        "bbox": [min(us), min(vs), max(us), max(vs)],
        "corners_visible": len(visible),
        "corners_total": len(corners),
        "any_visible": True,
    }


def depth_image_to_points(
    depth: Sequence[Sequence[float]],
    intrinsics: dict[str, Any],
    *,
    z_min: float = DEFAULT_Z_MIN,
) -> dict[str, Any]:
    """深度图（行主序，单位米）→ 光学系点云。

    返回 ``{points, valid, total}``；``points`` 元素为 ``(x, y, z)``（光学系，米）。
    """
    fx, fy = float(intrinsics["fx"]), float(intrinsics["fy"])
    cx, cy = float(intrinsics["cx"]), float(intrinsics["cy"])
    points: list[tuple[float, float, float]] = []
    total = 0
    for row, line in enumerate(depth):
        for col, value in enumerate(line):
            total += 1
            d = float(value)
            if not math.isfinite(d) or d <= z_min:
                continue
            points.append(((col - cx) * d / fx, (row - cy) * d / fy, d))
    return {"points": points, "valid": len(points), "total": total}


def arrival_verdict(
    position_xy: Sequence[float],
    target_xy: Sequence[float],
    *,
    tolerance_m: float | None = None,
) -> dict[str, Any]:
    """目标判定（到达）：平面距离 ≤ 容差即判定到达。

    H10：容差不再由本模块自带默认值（旧默认 0.3 与导航侧的 0.35 是两套口径），
    而是走 ``registry/arrival_criteria.json`` 的单一真值；显式传入旧值时不阻断，
    但结果里会带 ``deviation`` 说明已偏离单一真值。稳定性（连续拍数）不在此判定，
    需要时用 :func:`backend.arrival_criteria.waypoint_arrival`。
    """
    from backend.arrival_criteria import waypoint_arrival, waypoint_spec

    spec = waypoint_spec()
    verdict = waypoint_arrival(
        position_xy,
        target_xy,
        tolerance_m=tolerance_m,
        consecutive_ticks=int(spec["stable_ticks"]),
    )
    return {
        "distance_m": verdict["distance_m"],
        "tolerance_m": verdict["thresholds"]["tolerance_m"],
        "arrived": verdict["arrived"],
        "thresholds": verdict["thresholds"],
        "deviation": verdict["deviation"],
        "source": "registry/arrival_criteria.json::waypoint",
    }


def target_visibility(
    points: Iterable[Point3],
    sensor: dict[str, Any],
    intrinsics: dict[str, Any],
    *,
    z_min: float = DEFAULT_Z_MIN,
) -> dict[str, Any]:
    """目标判定（可见性）：目标区采样点中落入视野的比例与最近深度。"""
    projected = project_base_points(points, sensor, intrinsics, z_min=z_min)
    valid = [item for item in projected if item["valid"]]
    inside = [item for item in valid if item["inside"]]
    depths = [item["depth"] for item in inside]
    return {
        "sampled": len(projected),
        "projectable": len(valid),
        "inside_frame": len(inside),
        "visible_ratio": (len(inside) / len(projected)) if projected else 0.0,
        "nearest_depth_m": min(depths) if depths else None,
        "verdict": "visible" if inside else "not_visible",
    }


# --------------------------------------------------------------------------
# 自检（离线、可单测）
# --------------------------------------------------------------------------
def _default_sensors() -> list[dict[str, Any]]:
    from backend.sensor_suite import preset_sensors

    return [sensor.to_dict() for sensor in preset_sensors("default")]


def resolved_sensor_intrinsics() -> list[dict[str, Any]]:
    """默认套件里带内参的传感器（rgb / depth）× 解析后的针孔内参。"""
    out: list[dict[str, Any]] = []
    for sensor in _default_sensors():
        optics = sensor.get("intrinsics")
        if not optics or not optics.get("width"):
            continue
        resolved = resolve_intrinsics(
            int(optics["width"]),
            int(optics["height"]),
            fov_deg=optics.get("fov_deg"),
            fx=float(sensor.get("meta", {}).get("fx") or 0.0),
            fy=float(sensor.get("meta", {}).get("fy") or 0.0),
            cx=float(sensor.get("meta", {}).get("cx", -1.0)),
            cy=float(sensor.get("meta", {}).get("cy", -1.0)),
        )
        out.append(
            {
                "id": sensor["id"],
                "kind": sensor["kind"],
                "class": sensor["class"],
                "topic": sensor["topic"],
                "mount": sensor["mount"],
                "frequency_hz": sensor["frequency_hz"],
                "position": sensor["position"],
                "rotation": sensor["rotation"],
                "intrinsics": resolved,
            }
        )
    return out


def camera_projection_selftest() -> dict[str, Any]:
    """相机几何自检：内参推导、中心射线、视场边缘、遮挡剔除、框投影、深度往返、目标判定。"""
    with_intrinsics = resolved_sensor_intrinsics()
    camera = next((item for item in with_intrinsics if item["kind"] == "rgb"), None)
    depth_sensor = next((item for item in with_intrinsics if item["kind"] == "depth"), None)
    cases: list[dict[str, Any]] = []

    def case(name: str, ok: bool, detail: dict[str, Any]) -> None:
        cases.append({"name": name, "ok": bool(ok), **detail})

    if camera is None:  # pragma: no cover - 默认套件缺 rgb 才会走到
        raise ValueError("默认套件缺少带内参的 rgb 传感器")

    intrinsics = camera["intrinsics"]
    mount = {"position": camera["position"], "rotation": camera["rotation"], "mount": camera["mount"]}

    # 1) 光轴上的点 → 主点（考虑安装平移与旋转，含一个 90° 偏航的合成传感器）
    position = camera["position"] or {}
    rotation = camera["rotation"] or {}

    def axis_point(sensor: dict[str, Any], distance: float = 3.0) -> tuple[float, float, float]:
        rot = mount_rotation(
            float(rotation.get("roll") or 0.0),
            float(rotation.get("pitch") or 0.0),
            float(rotation.get("yaw") or 0.0),
        )
        ox, oy, oz = _mat_vec(rot, (distance, 0.0, 0.0))
        return (
            float(position.get("x") or 0.0) + ox,
            float(position.get("y") or 0.0) + oy,
            float(position.get("z") or 0.0) + oz,
        )

    center = project_base_points([axis_point(camera)], mount, intrinsics)[0]
    yawed = project_base_points(
        [(0.0, 0.0, 0.0), (0.0, 3.0, 0.0)],
        {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "rotation": {"yaw": 90.0}},
        intrinsics,
    )
    # 偏航 90° 的相机朝机身 +y 看：位于 (0, 3, 0) 的点应落在主点上
    case(
        "optical_axis_point_hits_principal_point",
        abs(center["u"] - intrinsics["cx"]) < 1e-9
        and abs(center["v"] - intrinsics["cy"]) < 1e-9
        and abs(yawed[1]["u"] - intrinsics["cx"]) < 1e-9
        and abs(yawed[1]["v"] - intrinsics["cy"]) < 1e-9,
        {
            "u": center["u"],
            "v": center["v"],
            "cx": intrinsics["cx"],
            "cy": intrinsics["cy"],
            "yaw90_u": yawed[1]["u"],
            "yaw90_v": yawed[1]["v"],
        },
    )

    # 2) 水平视场边缘 → u = 0 / u = W-1（内参推导与边缘一致性）
    half = 3.0 * math.tan(math.radians(intrinsics["hfov_deg"]) / 2.0)
    left = project_base_points([(3.0, half, 0.0)], mount, intrinsics)[0]
    right = project_base_points([(3.0, -half, 0.0)], mount, intrinsics)[0]
    case(
        "hfov_edges_map_to_image_edges",
        abs(left["u"] - 0.0) < 1e-6 and abs(right["u"] - (intrinsics["width"] - 1)) < 1e-6,
        {"u_at_left_edge": left["u"], "u_at_right_edge": right["u"], "width": intrinsics["width"]},
    )

    # 3) 相机后方的点必须被剔除
    behind = project_base_points([(-2.0, 0.0, 0.0)], mount, intrinsics)[0]
    case("points_behind_camera_rejected", not behind["valid"], {"valid": behind["valid"]})

    # 4) 长方体投影：2D 框应包含该长方体中心的投影，且角点可见计数在 [1, 8]
    box = project_box((2.0, 0.0, 0.0), (0.3, 0.3, 0.3), mount, intrinsics)
    box_center = project_base_points([(2.0, 0.0, 0.0)], mount, intrinsics)[0]
    inside_bbox = bool(
        box["bbox"]
        and box["bbox"][0] <= box_center["u"] <= box["bbox"][2]
        and box["bbox"][1] <= box_center["v"] <= box["bbox"][3]
    )
    case(
        "box_projects_to_2d_bbox",
        box["any_visible"] and inside_bbox and 1 <= box["corners_visible"] <= box["corners_total"],
        {"bbox": box["bbox"], "corners_visible": box["corners_visible"]},
    )

    # 5) 深度 → 点云 → 投影：往返应回到原像素
    if depth_sensor is not None:
        depth_intr = depth_sensor["intrinsics"]
        u0, v0 = depth_intr["cx"] + 40.0, depth_intr["cy"] - 25.0
        d = 2.5
        x = (u0 - depth_intr["cx"]) * d / depth_intr["fx"]
        y = (v0 - depth_intr["cy"]) * d / depth_intr["fy"]
        points = depth_image_to_points([[d] * depth_intr["width"]], depth_intr)
        back = project_optical_points([(x, y, d)], depth_intr)[0]
        case(
            "depth_roundtrip_returns_same_pixel",
            abs(back["u"] - u0) < 1e-6 and abs(back["v"] - v0) < 1e-6 and points["valid"] == depth_intr["width"],
            {"u": back["u"], "v": back["v"], "expected_u": u0, "expected_v": v0},
        )
    else:  # pragma: no cover
        case("depth_roundtrip_returns_same_pixel", False, {"reason": "默认套件缺少 depth 传感器"})

    # 6) 目标判定：到达 + 可见性
    arrived = arrival_verdict((0.0, 0.0), (0.2, 0.0), tolerance_m=0.3)
    missed = arrival_verdict((0.0, 0.0), (1.0, 0.0), tolerance_m=0.3)
    zone = [(2.0 + dx, dy, 0.0) for dx in (-0.3, 0.0, 0.3) for dy in (-0.3, 0.0, 0.3)]
    visibility = target_visibility(zone, mount, intrinsics)
    case(
        "target_verdict_arrival_and_visibility",
        arrived["arrived"] and not missed["arrived"] and visibility["verdict"] == "visible" and visibility["visible_ratio"] > 0.5,
        {"arrived": arrived["arrived"], "missed_arrived": missed["arrived"], "visible_ratio": visibility["visible_ratio"]},
    )

    # 7) H8：理想针孔 vs 真机畸变的像素差（同 K，只开关畸变）
    ideal_impact = distortion_impact("ideal-pinhole-1920x1080")
    real_impact = distortion_impact("go2-front-fisheye-1920x1080")
    case(
        "ideal_pinhole_vs_distorted_real_pixel_delta",
        ideal_impact["max_delta_px"] == 0.0 and real_impact["max_delta_px"] > 1.0,
        {
            "ideal_max_delta_px": ideal_impact["max_delta_px"],
            "real_profile": real_impact["profile"],
            "real_model": real_impact["model"],
            "real_max_delta_px": round(real_impact["max_delta_px"], 3),
            "real_mean_delta_px": round(real_impact["mean_delta_px"], 3),
            "real_rms_delta_px": round(real_impact["rms_delta_px"], 3),
            "corner_delta_px": real_impact["corner_delta_px"],
            "note": "位移 = 同一内参下畸变开-关，只反映镜头畸变本身",
        },
    )

    failures = [item["name"] for item in cases if not item["ok"]]
    return {
        "success": True,
        "sensors": with_intrinsics,
        "cases": cases,
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
    }


def _quat_from_matrix(matrix: list[list[float]]) -> tuple[float, float, float, float]:
    """旋转矩阵 → 四元数 (w, x, y, z)（Shepperd 分支法，纯 Python）。"""
    m = matrix
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2][1] - m[1][2]) / s
        y = (m[0][2] - m[2][0]) / s
        z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        w = (m[2][1] - m[1][2]) / s
        x = 0.25 * s
        y = (m[0][1] + m[1][0]) / s
        z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        w = (m[0][2] - m[2][0]) / s
        x = (m[0][1] + m[1][0]) / s
        y = 0.25 * s
        z = (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
        w = (m[1][0] - m[0][1]) / s
        x = (m[0][2] + m[2][0]) / s
        y = (m[1][2] + m[2][1]) / s
        z = 0.25 * s
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    return (w / norm, x / norm, y / norm, z / norm)


def mujoco_camera_pose(sensor: dict[str, Any]) -> dict[str, Any]:
    """把 FLU 安装（``position``/``rotation``）换算成 MuJoCo ``<camera>`` 位姿。

    MuJoCo 相机约定：本地 **x 右、y 上、z 后**，视线沿本地 **−z**（OpenGL 风格）。
    与安装系 FLU（x 前 y 左 z 上）的关系（安装系坐标下的相机三轴）：

        X_mj = (0, −1, 0)   Y_mj = (0, 0, 1)   Z_mj = (−1, 0, 0)

    再左乘安装旋转 ``R_mount`` 得到世界（机身）系下的姿态。
    """
    frame = camera_frame_from_sensor(sensor)
    rot = frame["rotation"]  # 安装旋转：安装系轴 → 机身系
    columns = [
        _mat_vec(rot, (0.0, -1.0, 0.0)),
        _mat_vec(rot, (0.0, 0.0, 1.0)),
        _mat_vec(rot, (-1.0, 0.0, 0.0)),
    ]
    axis_matrix = [[columns[c][r] for c in range(3)] for r in range(3)]
    return {
        "pos": list(frame["translate"]),
        "quat": list(_quat_from_matrix(axis_matrix)),
        "axis_matrix": axis_matrix,
    }


#: 交叉校验用的采样点（机身系，米）：中心 / 左右 / 上下 / 远近 / 一个后方点
MUJOCO_CHECK_POINTS: tuple[tuple[float, float, float], ...] = (
    (2.0, 0.0, 0.0),
    (2.0, 0.5, 0.0),
    (2.0, -0.5, 0.0),
    (2.0, 0.0, 0.4),
    (2.0, 0.0, -0.4),
    (0.8, 0.15, 0.05),
    (3.5, -0.3, 0.2),
    (-1.0, 0.0, 0.0),
)


def mujoco_camprojection_check(
    *,
    sensor: dict[str, Any] | None = None,
    focal_m: float = 0.05,
    sensor_size_m: tuple[float, float] = (0.036, 0.024),
    resolution: tuple[int, int] = (640, 480),
    points: Sequence[Point3] | None = None,
) -> dict[str, Any]:
    """用 MuJoCo 原生 ``<camprojection>`` 交叉校验本模块的针孔投影。

    做法：把 ``sensor_suite`` 的相机安装换算成 MuJoCo 相机位姿（:func:`mujoco_camera_pose`），
    在 MJCF 里建同一位姿的 ``<camera>`` 与若干目标 site，取其 ``<camprojection>`` 输出，
    与本模块 :func:`project_base_points` 的结果逐点比较。

    口径差异说明：MuJoCo 内参为 ``fx = focal/sensorsize_x·res_x``、
    ``fy = focal/sensorsize_y·res_y``、主点 ``(res_x/2, res_y/2)``；本模块默认主点为
    ``((W−1)/2, (H−1)/2)``。交叉校验时**显式传入 MuJoCo 的主点**，因此比较的是投影数学本身，
    半像素差被隔离在 ``principal_point_convention`` 字段里单独报告。
    """
    try:
        import mujoco  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - 依赖缺失时降级
        return {"available": False, "reason": f"mujoco 不可导入: {exc}"}

    if sensor is None:
        from backend.sensor_suite import preset_sensors

        sensor = next(item.to_dict() for item in preset_sensors("default") if item.kind == "rgb")
    probes = tuple(points) if points is not None else MUJOCO_CHECK_POINTS

    pose = mujoco_camera_pose(sensor)
    res_x, res_y = resolution
    intrinsics = resolve_intrinsics(
        res_x,
        res_y,
        fx=focal_m / sensor_size_m[0] * res_x,
        fy=focal_m / sensor_size_m[1] * res_y,
        cx=res_x / 2.0,
        cy=res_y / 2.0,
    )

    target_bodies = "\n".join(
        f'    <body name="t{i}" pos="{p[0]} {p[1]} {p[2]}"><site name="s{i}" size="0.001"/><geom size="0.001"/></body>'
        for i, p in enumerate(probes)
    )
    sensors = "\n".join(
        f'    <camprojection name="uv{i}" site="s{i}" camera="cam"/>' for i in range(len(probes))
    )
    xml = f"""
<mujoco model="projection-crosscheck">
  <worldbody>
    <body name="cam_body" pos="{pose['pos'][0]} {pose['pos'][1]} {pose['pos'][2]}"
          quat="{pose['quat'][0]} {pose['quat'][1]} {pose['quat'][2]} {pose['quat'][3]}">
      <camera name="cam" pos="0 0 0" focal="{focal_m} {focal_m}"
              sensorsize="{sensor_size_m[0]} {sensor_size_m[1]}"
              resolution="{res_x} {res_y}"/>
    </body>
{target_bodies}
  </worldbody>
  <sensor>
{sensors}
  </sensor>
</mujoco>
"""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    mine = project_base_points(probes, sensor, intrinsics)
    rows: list[dict[str, Any]] = []
    max_du = max_dv = 0.0
    for i, point in enumerate(probes):
        reference = data.sensordata[i * 2 : i * 2 + 2]
        expected = mine[i]
        if not expected["valid"]:
            rows.append({"point": list(point), "mujoco": None, "mine": None, "skipped": "相机后方"})
            continue
        du = abs(float(reference[0]) - expected["u"])
        dv = abs(float(reference[1]) - expected["v"])
        max_du, max_dv = max(max_du, du), max(max_dv, dv)
        rows.append(
            {
                "point": list(point),
                "mujoco": [float(reference[0]), float(reference[1])],
                "mine": [round(expected["u"], 9), round(expected["v"], 9)],
                "abs_du": du,
                "abs_dv": dv,
            }
        )

    compare = [row for row in rows if "mujoco" in row and row["mujoco"] is not None]
    # MuJoCo 的 sensordata 以 float32 存储：像素量级 ~500 时 ULP ≈ 6e-5 px，
    # 因此判定阈值取 2 × ULP（数学一致性远优于该量级，见 rows 里的 abs_du/abs_dv）。
    max_coord = max((abs(value) for row in compare for value in row["mujoco"]), default=0.0)
    tolerance = max(1e-6, 2.0 * max_coord * 2.0 ** -23)
    return {
        "available": True,
        "success": True,
        "camera_pose": pose,
        "intrinsics": intrinsics,
        "resolution": [res_x, res_y],
        "principal_point_convention": {
            "mujoco": [res_x / 2.0, res_y / 2.0],
            "camera_projection_default": [(res_x - 1) / 2.0, (res_y - 1) / 2.0],
        },
        "compared": len(compare),
        "max_abs_du": max_du,
        "max_abs_dv": max_dv,
        "tolerance_px": tolerance,
        "rows": rows,
        "verdict": "pass" if compare and max(max_du, max_dv) <= tolerance else "fail",
    }


@router.get("/mujoco-check")
async def projection_mujoco_check():
    """用 MuJoCo 原生 camprojection 交叉校验本模块的针孔投影（需安装 mujoco）。"""
    return mujoco_camprojection_check()


@router.get("/sensors")
async def projection_sensors():
    """默认传感器套件中带内参的传感器及其解析后的针孔内参。"""
    sensors = resolved_sensor_intrinsics()
    return {"success": True, "count": len(sensors), "sensors": sensors}


@router.get("/selftest")
async def projection_selftest():
    """相机几何自检（中心射线 / 视场边缘 / 遮挡剔除 / 框投影 / 深度往返 / 目标判定）。"""
    return camera_projection_selftest()


@router.post("/project")
async def project_points(payload: dict[str, Any]):
    """按传感器 id 投影一组机身系点。

    载荷：``{"sensor_id": "camera", "points": [[x, y, z], ...], "preset": "default"}``。
    """
    from backend.sensor_suite import preset_names, preset_sensors

    preset = str(payload.get("preset") or "default")
    if preset not in preset_names():
        raise HTTPException(status_code=404, detail=f"Unknown sensor preset: {preset}")
    sensor_id = str(payload.get("sensor_id") or "camera")
    sensor = next((item.to_dict() for item in preset_sensors(preset) if item.id == sensor_id), None)
    if sensor is None:
        raise HTTPException(status_code=404, detail=f"Unknown sensor id: {sensor_id}")
    optics = sensor.get("intrinsics")
    if not optics or not optics.get("width"):
        raise HTTPException(status_code=400, detail=f"sensor {sensor_id} 没有相机内参（无法投影）")
    raw_points = payload.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        raise HTTPException(status_code=400, detail="points 必须是非空数组")
    intrinsics = resolve_intrinsics(
        int(optics["width"]),
        int(optics["height"]),
        fov_deg=optics.get("fov_deg"),
        fx=float(sensor.get("meta", {}).get("fx") or 0.0),
        fy=float(sensor.get("meta", {}).get("fy") or 0.0),
        cx=float(sensor.get("meta", {}).get("cx", -1.0)),
        cy=float(sensor.get("meta", {}).get("cy", -1.0)),
    )
    projected = project_base_points(raw_points, sensor, intrinsics)
    return {
        "success": True,
        "preset": preset,
        "sensor_id": sensor_id,
        "intrinsics": intrinsics,
        "count": len(projected),
        "points": projected,
    }


@router.get("/cameras")
async def projection_cameras():
    """可选相机档位（H8）：理想针孔口径 与 真机标定口径，含解析后的内参与畸变模型。"""
    profiles = [
        {"id": profile.get("id"), "label": profile.get("label"), "kind": profile.get("kind"),
         "scope": profile.get("scope"), "model": profile.get("model"),
         "intrinsics": camera_profile_intrinsics(profile)}
        for profile in camera_profiles()
    ]
    return {"success": True, "source": "registry/cameras.json", "count": len(profiles), "profiles": profiles}


@router.get("/cameras/compare")
async def projection_cameras_compare():
    """理想针孔 vs 畸变真实的像素差（H8 验收口径）。

    两种比较都给：① 同一档位内「畸变关 vs 畸变开」（只反映镜头畸变本身）；
    ② 注册表声明的跨档位对照（如 fov 90° 理想针孔 vs Go2 真机鱼眼）。
    """
    impacts = {str(profile.get("id")): distortion_impact(str(profile.get("id"))) for profile in camera_profiles()}
    comparisons = []
    for pair in (load_registry("cameras").get("comparisons") or []):
        ideal_id, real_id = str(pair.get("ideal")), str(pair.get("real"))
        ideal, real = impacts.get(ideal_id), impacts.get(real_id)
        if not ideal or not real:
            continue
        comparisons.append(
            {
                "label": pair.get("label"),
                "ideal": {"id": ideal_id, "max_delta_px": ideal["max_delta_px"]},
                "real": {
                    "id": real_id,
                    "model": real["model"],
                    "max_delta_px": real["max_delta_px"],
                    "mean_delta_px": real["mean_delta_px"],
                    "corner_delta_px": real["corner_delta_px"],
                },
                "max_delta_px": real["max_delta_px"],
            }
        )
    return {
        "success": True,
        "source": "registry/cameras.json",
        "distortion_impact": impacts,
        "comparisons": comparisons,
    }
