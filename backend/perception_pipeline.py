"""渲染 → 检测 → 位姿 的闭环：把 RGB 与几何**对齐到同一台相机**。

**为什么必须对齐**：``POST /api/models/preview``（``backend/model_api.py``）已经能渲染
（``mujoco.Renderer`` + ``update_scene``），但它用 ``mjv_defaultFreeCamera`` **自动取景** ——
那个视角既不在 ``model.cam_*`` 里、也没有对应的内参，于是"渲染出来的画面"和"我们投影算出的
标签角点"**根本不是同一台相机**，检测框无从对齐（画出来必然偏）。本模块只做一件事：
**渲染与投影都走 MJCF 里声明的那台相机**（``data.cam_xpos`` / ``data.cam_xmat`` +
``model.cam_fovy``），这样"图上画的框"与"图里那个东西"必然重合。

**坐标系换算**（MuJoCo → 光学系，实测核对过）：
MuJoCo 相机系是 **x 右 / y 上 / z 后**（看向 -z），而针孔光学系是 **x 右 / y 下 / z 前**，
所以 ``optical = diag(1, -1, -1) @ Rᵀ @ (p_world − cam_pos)``。

**边界（别读错）**：检测结果由 ``backend/synthetic_detector.py`` 提供（几何 + **声明式**噪声），
**不是图像识别** —— 本模块**不解析 RGB 去找标签**，它负责的是"渲染与几何同相机"以及把
两者对齐输出，好让人能**看图检查检测框对不对**。真图像识别仍需 ``opencv-contrib-python``
或 ``apriltag``（``tag_detector.image_detector_available()`` 会如实报 False）。
"""

from __future__ import annotations

import base64
import io
import math
import random
from typing import Any, Sequence

#: 标签四角在标签本体 x-y 平面上的单位坐标（顺序与 tag_detector 的 CORNER_ORDER 一致）
TAG_LOCAL_CORNERS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))


def ensure_render_backend() -> None:
    """必须在 ``import mujoco`` **之前**确定离屏后端（与 backend/__init__ 同一约定）。"""
    from backend.gl_env import ensure_headless_gl

    ensure_headless_gl()


def camera_intrinsics(model: Any, camera_id: int, width: int, height: int) -> dict[str, Any]:
    """由 MJCF 相机推针孔内参：``fovy`` 是**垂直**视场，像素为方形 ⇒ ``fx = fy``。

    这样"渲染用的相机"与"投影用的模型"是同一台——否则 fov 一旦对不上，检测框会整体缩放偏移。
    """
    fovy_deg = float(model.cam_fovy[camera_id])
    if not (0.0 < fovy_deg < 180.0):
        raise ValueError(f"相机 fovy 非法：{fovy_deg}")
    focal = (float(height) / 2.0) / math.tan(math.radians(fovy_deg) / 2.0)
    return {
        "fx": focal,
        "fy": focal,
        "cx": float(width) / 2.0,
        "cy": float(height) / 2.0,
        "width": int(width),
        "height": int(height),
        "distortion_model": "pinhole",
        "distortion": [],
        "source": f"mjcf camera fovy={fovy_deg}",
    }


def world_to_optical(
    points_world: Sequence[Sequence[float]],
    camera_position: Sequence[float],
    camera_rotation: Sequence[Sequence[float]],
) -> list[list[float]]:
    """世界点 → 相机光学系（x 右 / y 下 / z 前）。

    ``camera_rotation`` 是 MuJoCo 的 ``cam_xmat``（列 = 相机 x/y/z 轴在世界系）。
    """
    rotation = [[float(camera_rotation[r][c]) for c in range(3)] for r in range(3)]
    origin = [float(camera_position[i]) for i in range(3)]
    out: list[list[float]] = []
    for point in points_world:
        rel = [float(point[i]) - origin[i] for i in range(3)]
        # Rᵀ @ rel = 世界向量在相机系下的坐标
        cam = [sum(rotation[k][i] * rel[k] for k in range(3)) for i in range(3)]
        # 相机系(x右,y上,z后) → 光学系(x右,y下,z前)
        out.append([cam[0], -cam[1], -cam[2]])
    return out


def tag_corners_world(data: Any, body_id: int, tag_size_m: float) -> list[list[float]]:
    """标签四角的世界坐标：标签平面 = 该 body 的 x-y 平面（z 为法向）。

    注意 ``data.xpos`` / ``data.xmat`` 在 Python 侧是**二维数组**（``(nbody, 3)`` / ``(nbody, 9)``），
    不是浏览器 WASM 那边的扁平数组 —— 照搬前端的 ``xpos[bid*3]`` 写法会索引错位。
    """
    if float(tag_size_m) <= 0.0:
        raise ValueError("tag_size_m 必须为正")
    if int(body_id) < 0:
        raise ValueError("tag body 未找到（body_id < 0）")
    half = float(tag_size_m) / 2.0
    body_mat = [[float(data.xmat[body_id][r * 3 + c]) for c in range(3)] for r in range(3)]
    origin = [float(v) for v in data.xpos[body_id]]
    corners: list[list[float]] = []
    for local_x, local_y in TAG_LOCAL_CORNERS:
        local = (local_x * half, local_y * half, 0.0)
        corners.append([
            origin[i] + sum(body_mat[i][k] * local[k] for k in range(3)) for i in range(3)
        ])
    return corners


def render_rgb(
    model: Any, data: Any, camera_id: int, width: int, height: int
) -> Any:
    """用 MJCF 里那台相机渲染一帧（HWC uint8）。渲染失败按上游口径抛原始异常。"""
    import mujoco

    renderer = mujoco.Renderer(model, height=int(height), width=int(width))
    try:
        renderer.update_scene(data, camera=int(camera_id))
        pixels = renderer.render()
    finally:
        renderer.close()
    return pixels


def png_bytes(pixels: Any) -> bytes:
    """RGB 像素 → PNG（有 PIL 用 PIL；精简控制面环境走自研 zlib 编码，同 model_api 口径）。"""
    import numpy as np

    rgba = np.asarray(pixels, dtype=np.uint8)
    height, width = int(rgba.shape[0]), int(rgba.shape[1])
    try:
        from PIL import Image

        stream = io.BytesIO()
        Image.fromarray(rgba).save(stream, format="PNG")
        return stream.getvalue()
    except ImportError:
        import struct
        import zlib

        rows = b"".join(b"\0" + row.tobytes() for row in rgba)
        header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)

        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b"")
        )


def bright_bbox(
    pixels: Any, threshold: int | None = None, *, ratio: float = 0.5
) -> list[int] | None:
    """在渲染图里找"亮块"的像素包围盒 ``[u0, v0, u1, v1]``（纯 numpy，用来验证框对不对）。

    **阈值默认自适应**（``min + (max − min) × ratio``），因为**绝对阈值不可靠**：
    MuJoCo 渲染的白色几何体带光照与阴影，实测亮度只有 ~190 而不是 255 ——
    写死 200 会得到"图里明明有标签却找不到"（本模块自测第一个版本正是如此失败）。
    场景按"高对比双峰"（深地面 / 白标签）设计时，中点阈值就是最稳的分割。
    """
    import numpy as np

    rgba = np.asarray(pixels, dtype=np.uint8)
    gray = rgba[..., :3].max(axis=-1)
    if gray.size == 0:
        return None
    if threshold is None:
        low, high = float(gray.min()), float(gray.max())
        if high - low < 1e-9:
            return None  # 全平：没有"亮块"可言，别把整幅图当标签
        threshold = low + (high - low) * float(ratio)
    mask = gray >= threshold
    rows, cols = np.nonzero(mask)
    if rows.size == 0:
        return None
    return [int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())]


def render_and_detect(
    model: Any,
    data: Any,
    *,
    camera_id: int,
    tag_body_id: int,
    tag_size_m: float,
    width: int,
    height: int,
    noise: Any = None,
    rng: random.Random | None = None,
    z_min: float = 0.05,
) -> dict[str, Any]:
    """闭环：**渲染一帧** → 由几何算出带噪检测角点 → 反解位姿 → 输出可对齐的框。

    返回里同时给 ``truth_corners_px``（无噪声投影）与 ``detected_corners_px``（带噪），
    便于"看图检查检测误差"；``bbox_px`` 是渲染图里亮块的包围盒，用于验证两者同相机。
    """
    from backend.synthetic_detector import DetectionNoise, detect_from_optical
    from backend.perception_providers.tag_detector import pose_from_corners

    intrinsics = camera_intrinsics(model, camera_id, width, height)
    corners_world = tag_corners_world(data, tag_body_id, tag_size_m)
    corners_optical = world_to_optical(
        corners_world,
        [float(v) for v in data.cam_xpos[camera_id]],
        [[float(data.cam_xmat[camera_id][r * 3 + c]) for c in range(3)] for r in range(3)],
    )

    # 无噪声投影（真值框）
    truth = detect_from_optical(corners_optical, intrinsics, noise=DetectionNoise(), z_min=z_min)
    # 带噪检测（"检测器会给出的那一组角点"）
    detected = detect_from_optical(
        corners_optical, intrinsics, noise=noise or DetectionNoise(), rng=rng, z_min=z_min
    )

    result: dict[str, Any] = {
        "camera_id": int(camera_id),
        "intrinsics": intrinsics,
        "tag_body_id": int(tag_body_id),
        "corners_world": [[round(v, 6) for v in corner] for corner in corners_world],
        "corners_optical": [[round(v, 6) for v in corner] for corner in corners_optical],
        "truth_corners_px": truth["corners_px"],
        "detected_corners_px": detected["corners_px"],
        "detected": bool(detected["detected"]),
        "detection_reason": detected["reason"],
        "noise": detected.get("noise"),
        # 自报边界：几何检测，不是图像识别
        "source": "render+synthetic_detector",
        "image_based": False,
    }

    if detected["detected"]:
        pose = pose_from_corners(
            detected["corners_px"], intrinsics, tag_size_m, undistorted=True
        )
        result["pose_optical"] = {
            "position": [round(float(v), 6) for v in pose["position_optical"]],
            "in_plane_rotation_rad": pose.get("in_plane_rotation_rad"),
            "reprojection_error_px": pose.get("reprojection_error_px"),
        }

    try:
        pixels = render_rgb(model, data, camera_id, width, height)
    except BaseException as exc:  # GL 不可用等：渲染是可选能力，如实报错不吞
        result["render_error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["bbox_px"] = bright_bbox(pixels)
    result["image_png_base64"] = base64.b64encode(png_bytes(pixels)).decode("ascii")
    result["width"], result["height"] = int(width), int(height)
    return result


#: 自检场景：深色地面 + 白色标签 + 一台正对标签的相机。
#: 标签做大、做近、正对，是为了让"图里那块白"与"投影四角"都稳定可判。
#:
#: **`quat` 不能省**：标签面默认在 body 的 x-y 平面（法向 +z，即朝上），而相机是**水平**看 +y 的
#: —— 不旋转就只看到标签的**侧边**，投影退化成一条线、渲染图里也找不到亮块
#: （本模块自检第一个版本就是这么"失败"的：几何全对，场景摆错了）。
#: 绕 x 轴 +90° ⇒ 法向由 +z 变为 −y，正对相机。
SELFTEST_SCENE = """
<mujoco>
  <worldbody>
    <geom name="floor" type="plane" size="5 5 .1" rgba="0.15 0.15 0.2 1"/>
    <body name="tag" pos="0 0 0.6" quat="0.7071068 0.7071068 0 0">
      <geom name="tag_face" type="box" size="0.08 0.08 0.004" rgba="1 1 1 1"/>
    </body>
    <camera name="front" pos="0 -0.9 0.6" xyaxes="1 0 0 0 0 1"/>
  </worldbody>
</mujoco>
"""


def perception_pipeline_selftest(width: int = 320, height: int = 240) -> dict[str, Any]:
    """自检：内参 / 坐标换算 / 投影落在画面内 / 渲染亮块与投影包围盒**同相机**。

    渲染不可用时**如实报告**（不抛），因为离屏 GL 在部分环境里本来就没有。
    """
    from backend.gl_env import offscreen_render_status

    ensure_render_backend()
    import mujoco
    import numpy as np

    model = mujoco.MjModel.from_xml_string(SELFTEST_SCENE)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "front")
    tag_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "tag")

    available, reason = offscreen_render_status()
    report: dict[str, Any] = {
        "render_available": available,
        "render_reason": reason,
        "camera_id": int(camera_id),
        "tag_body_id": int(tag_id),
    }
    result = render_and_detect(
        model, data, camera_id=camera_id, tag_body_id=tag_id,
        tag_size_m=0.16, width=width, height=height,
    )
    report["intrinsics"] = result["intrinsics"]
    report["truth_corners_px"] = result["truth_corners_px"]
    report["detected"] = result["detected"]

    truth = result["truth_corners_px"] or []
    inside = [
        all(0.0 <= corner[0] < width and 0.0 <= corner[1] < height for corner in truth)
    ]
    report["truth_corners_inside_image"] = bool(truth) and inside[0]
    if result.get("render_error"):
        report["verdict"] = "skip" if not available else "fail"
        report["render_error"] = result["render_error"]
        return report

    bbox = result.get("bbox_px")
    report["bbox_px"] = bbox
    us = [corner[0] for corner in truth]
    vs = [corner[1] for corner in truth]
    truth_box = [min(us), min(vs), max(us), max(vs)] if truth else None
    # 先记下投影外接框：即使后面判 fail，诊断信息也已经在报告里了。
    report["truth_bbox_px"] = [round(v, 2) for v in truth_box] if truth_box else None
    if not truth_box or bbox is None:
        report["verdict"] = "fail"
        report["detail"] = "投影角点或渲染亮块缺一"
        return report
    # 亮块（实心标签）应**包住**投影四角的外接框：标签面是实心的，白区不会比它小。
    margin = 6.0
    report["bbox_covers_projection"] = bool(
        bbox[0] <= truth_box[0] + margin
        and bbox[1] <= truth_box[1] + margin
        and bbox[2] >= truth_box[2] - margin
        and bbox[3] >= truth_box[3] - margin
    )
    report["verdict"] = (
        "pass"
        if report["truth_corners_inside_image"] and report["bbox_covers_projection"]
        else "fail"
    )
    return report
