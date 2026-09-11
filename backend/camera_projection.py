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
) -> list[dict[str, Any]]:
    """光学系点 → 像素。返回逐点 ``{u, v, depth, inside, valid}``；``depth ≤ z_min`` 视为无效。"""
    fx, fy = float(intrinsics["fx"]), float(intrinsics["fy"])
    cx, cy = float(intrinsics["cx"]), float(intrinsics["cy"])
    width, height = int(intrinsics["width"]), int(intrinsics["height"])
    results: list[dict[str, Any]] = []
    for point in points:
        x, y, z = float(point[0]), float(point[1]), float(point[2])
        if not all(map(math.isfinite, (x, y, z))) or z <= z_min:
            results.append({"u": None, "v": None, "depth": z, "inside": False, "valid": False})
            continue
        u = fx * (x / z) + cx
        v = fy * (y / z) + cy
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
    tolerance_m: float = 0.3,
) -> dict[str, Any]:
    """目标判定（到达）：平面距离 ≤ 容差即判定到达。"""
    distance = math.dist((float(position_xy[0]), float(position_xy[1])), (float(target_xy[0]), float(target_xy[1])))
    return {
        "distance_m": distance,
        "tolerance_m": tolerance_m,
        "arrived": distance <= tolerance_m,
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

    failures = [item["name"] for item in cases if not item["ok"]]
    return {
        "success": True,
        "sensors": with_intrinsics,
        "cases": cases,
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
    }


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
