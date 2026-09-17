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

**检测这一步**（图像 → 角点）2026-09-16（H31）补上了**可选依赖路径**，三条后端按序尝试：

1. `cv2.aruco`（`opencv-contrib-python`）—— 支持 ArUco 全家与 **AprilTag 族字典**
   （`DICT_APRILTAG_36h11` 等），所以一套依赖既能认 ArUco 也能认 AprilTag；
2. `pupil_apriltags` / `apriltag`（pyapriltags）—— 纯 AprilTag 检测器，返回的角点顺序与
   `pupil` 的逆时针口径不同，这里统一重排成 `CORNER_ORDER`（tl,tr,br,bl）。

**缺依赖时行为不变**：仍然**不假装能检测** —— 传 `image` 会得到明确报错（写明缺哪些包、
以及"请传检测器输出的 corners_px"），而不是返回一个编出来的角点。
去畸变按**档位声明的模型**分派（`pinhole` 不动 / `brown_conrady` 走 `cv2.undistort` /
`fisheye_equidistant` 走 `cv2.fisheye.undistortImage`）—— 模型是档位里写着的，不在这里猜。

注意 ArUco 与 AprilTag 是两套互不识别（family 不同）的码，`tag_family` 要与场景里的标签一致。
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


#: AprilTag / ArUco 族名（cv2.aruco 的字典常量名）——`tag_family` 只接受这些，不接受"随便传"
DEFAULT_TAG_FAMILY = "DICT_APRILTAG_36h11"


def undistort_image(image: "np.ndarray", intrinsics: dict[str, Any]) -> "np.ndarray":
    """按**档位声明的畸变模型**去畸变（模型是档位里的真值，不在这里猜）。

    * ``pinhole`` —— 无畸变，原样返回；
    * ``brown_conrady`` —— ``cv2.undistort``（radtan k1,k2,p1,p2,k3）；
    * ``fisheye_equidistant`` —— ``cv2.fisheye.undistortImage``（k1..k4）。

    ``cv2`` 是可选依赖：**直通分支（无系数 / pinhole）必须在 import 之前返回**，
    否则没装 cv2 的环境连"无畸变档"都走不通（H31 声明的两态行为，2026-09-17 修正）。
    """

    coefficients = [float(value) for value in (intrinsics.get("distortion") or [])]
    if not coefficients:
        return image
    model = str(intrinsics.get("distortion_model") or "brown_conrady")
    if model == "pinhole":
        return image

    import cv2

    k = np.array([[float(intrinsics["fx"]), 0.0, float(intrinsics["cx"])],
                  [0.0, float(intrinsics["fy"]), float(intrinsics["cy"])],
                  [0.0, 0.0, 1.0]], dtype=np.float64)
    if model == "fisheye_equidistant":
        return cv2.fisheye.undistortImage(image, k, np.asarray(coefficients, dtype=np.float64), Knew=k)
    return cv2.undistort(image, k, np.asarray(coefficients, dtype=np.float64))


def _as_gray(image: "np.ndarray") -> "np.ndarray":
    array = np.asarray(image)
    if array.ndim == 2:
        return array.astype(np.uint8, copy=False)
    if array.ndim == 3 and array.shape[2] >= 3:
        # 只用 numpy 转灰度（BGR 是 OpenCV 的口径，与 web/后端其它地方一致）
        weights = np.array([0.114, 0.587, 0.299], dtype=np.float32)
        return (array[..., :3].astype(np.float32) @ weights).astype(np.uint8)
    raise ValueError(f"图像形状不认识：{array.shape}（需要 HxW 灰度或 HxWx3 BGR）")


def _detect_with_cv2(gray: "np.ndarray", tag_family: str) -> list[dict[str, Any]]:
    import cv2

    constant = getattr(cv2.aruco, tag_family, None)
    if constant is None:
        raise ValueError(f"cv2.aruco 里没有字典 {tag_family!r}（族名要与场景里的标签一致）")
    dictionary = cv2.aruco.getPredefinedDictionary(constant)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(gray)
    found: list[dict[str, Any]] = []
    for index, marker in enumerate(corners):
        # cv2.aruco 的角点顺序本来就是 tl,tr,br,bl（与本模块 CORNER_ORDER 一致）
        points = [[float(point[0]), float(point[1])] for point in marker.reshape(4, 2)]
        found.append({
            "tag_id": _scalar_id(ids[index]) if ids is not None else None,
            "corners_px": points,
            "backend": "cv2.aruco",
        })
    return found


def _scalar_id(value: Any) -> int | None:
    """把检测器给的 id 变成 int —— **两种形状都要认**。

    OpenCV 4.x 给 ``ids`` 形状 ``(N,1)``，5.x 给 ``(N,)``；早先写死 ``ids[index][0]``
    在 5.x 上直接 ``invalid index to scalar variable``（2026-09-16 实测踩到）。
    """

    array = np.asarray(value).reshape(-1)
    return int(array[0]) if array.size else None


def _detect_with_pupil(gray: "np.ndarray", tag_family: str) -> list[dict[str, Any]]:
    """pupil_apriltags / apriltag：只认 AprilTag，角点顺序需**重排**成 tl,tr,br,bl。"""

    try:
        import pupil_apriltags as library  # type: ignore
    except ImportError:  # pragma: no cover - 取决于环境
        import apriltag as library  # type: ignore

    family = tag_family.replace("DICT_APRILTAG_", "tag").lower()  # DICT_APRILTAG_36h11 → tag36h11
    detector = library.Detector(families=family) if hasattr(library, "Detector") else library.Detector(family)
    found: list[dict[str, Any]] = []
    for item in detector.detect(gray):
        # 这些库给的是 (bl, br, tr, tl) 之类的逆时针序 —— 统一按 y 升序 + x 升序排成阅读序，
        # 即 tl（左上）→ tr → br → bl，与 CORNER_ORDER 对齐。
        points = [[float(p[0]), float(p[1])] for p in item.corners]
        ordered = sorted(points, key=lambda point: (round(point[1], 3), round(point[0], 3)))
        top = ordered[:2]
        bottom = ordered[2:]
        top.sort(key=lambda point: point[0])
        bottom.sort(key=lambda point: point[0])
        found.append({
            "tag_id": int(getattr(item, "tag_id", -1)),
            "corners_px": [top[0], top[1], bottom[1], bottom[0]],
            "backend": "pupil_apriltags" if library.__name__ == "pupil_apriltags" else "apriltag",
        })
    return found


def detect_tag_corners(
    image: Any,
    *,
    intrinsics: dict[str, Any],
    tag_family: str = DEFAULT_TAG_FAMILY,
    undistorted: bool = False,
    want_tag_id: int | str | None = None,
) -> dict[str, Any]:
    """**从像素检测标签角点**（H31）：图像 → 去畸变 → 检测 → 统一角点顺序。

    返回 ``{"corners_px": [[u,v]×4], "tag_id": …, "backend": …, "candidates": [...], "undistorted": bool}``；
    一个都没检到时返回 ``corners_px=None``（**不是错误**：没看见标签是正常状态，丢帧判定要吃到它）。
    一条后端都没有 ⇒ 抛 ``requires_optional_dependency`` 风格的明确错误（不编角点）。
    """

    state = image_detector_available()
    if not state["available"]:
        raise ValueError(
            "从图像检测需要可选依赖 "
            f"{', '.join(IMAGE_DETECTOR_PACKAGES)}（当前 {state['packages']}）；"
            "请安装后重试，或改传检测器输出的 corners_px —— 本 provider 不伪造检测结果。"
        )

    working = image if undistorted else undistort_image(np.asarray(image), intrinsics)
    gray = _as_gray(working)
    candidates: list[dict[str, Any]] = []
    backend_errors: list[str] = []
    try:
        candidates = _detect_with_cv2(gray, tag_family)
    except Exception as exc:  # 族名不是 cv2 认识的（如 pupil 的 `tag36h11`）⇒ 交给下一条后端
        backend_errors.append(f"cv2.aruco: {exc}")
    if not candidates and (importlib_util_find_spec("pupil_apriltags") or importlib_util_find_spec("apriltag")):
        try:
            candidates = _detect_with_pupil(gray, tag_family)
        except Exception as exc:
            backend_errors.append(f"apriltag 库: {exc}")
    if not candidates and backend_errors and not any("未检到" in item for item in backend_errors):
        # 两条后端都**跑不起来**（而不是"跑起来了但没看到标签"）⇒ 如实报出来，别让人以为标签不在画面里
        state_hint = "；".join(backend_errors)
        if all("没有字典" in item or "No module" in item or "family" in item for item in backend_errors):
            state_hint += "（族名要与场景里的标签一致：cv2 用 DICT_APRILTAG_36h11，apriltag 库用 tag36h11）"
        raise ValueError(f"检测后端不可用：{state_hint}")
    if want_tag_id is not None and str(want_tag_id) != "":
        candidates = [item for item in candidates if str(item["tag_id"]) == str(want_tag_id)]

    best = candidates[0] if candidates else None
    return {
        "corners_px": best["corners_px"] if best else None,
        "tag_id": best["tag_id"] if best else None,
        "backend": best["backend"] if best else None,
        "candidates": [{"tag_id": item["tag_id"], "backend": item["backend"]} for item in candidates],
        "undistorted": bool(undistorted) or distortion_required(intrinsics),
        "tag_family": tag_family,
    }


def importlib_util_find_spec(module: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module) is not None


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
        self._last_detection: dict[str, Any] | None = None

    def _pose_base(self, position_optical: Sequence[float]) -> list[float]:
        frame = camera_frame_from_sensor(self.sensor)
        rotation = np.asarray(frame["rotation"], dtype=float)
        translate = np.asarray(frame["translate"], dtype=float)
        point = rotation @ np.asarray(optical_to_flu(position_optical), dtype=float) + translate
        return [float(value) for value in point]

    def update(self, reading: Any, time_s: float = 0.0) -> dict[str, Any]:
        """吃一帧检测结果：``{"tag_id": str, "corners_px": [[u,v]×4]}``（空/缺失表示本帧没看到）。"""
        payload = reading if isinstance(reading, dict) else {}
        detected_from = "corners"
        if isinstance(payload.get("image"), (np.ndarray, list, tuple)):
            # H31：装了可选依赖就**真检测**；没装仍然明确报错（不返回编出来的角点）。
            detection = detect_tag_corners(
                payload["image"],
                intrinsics=self.intrinsics,
                tag_family=str(payload.get("tag_family") or DEFAULT_TAG_FAMILY),
                undistorted=bool(payload.get("undistorted", False)),
                want_tag_id=payload.get("tag_id"),
            )
            detected_from = f"image:{detection['backend']}"
            payload = {**payload, "corners_px": detection["corners_px"], "tag_id": detection.get("tag_id")}
            self._last_detection = detection
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
            "detected_from": detected_from,
            "readings": self._readings,
            "time_s": float(time_s),
        }
        return dict(self._last)

    @property
    def last_reading(self) -> dict[str, Any] | None:
        return dict(self._last) if self._last else None
