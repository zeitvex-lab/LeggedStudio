"""机身周围高度扫描网格：契约 + 两条取数路径 + 逐格对齐回归。

网格定义取自上游 legged_gym 家族（本仓已收录的两处来源互相印证）：

- ``00_resources/HIMLoco/legged_gym/legged_gym/envs/base/legged_robot_config.py:55-57``
  ``measure_heights = True``、``measured_points_x = -0.8 … 0.8``（17 个，步长 0.1）、
  ``measured_points_y = -0.5 … 0.5``（11 个）；
- ``assets/robots/deeprobotics_m20/training/source/m20_dreamwaq/config.py:66-68``
  注释逐字写明 "``x -0.8..0.8, y -0.5..0.5 at 0.1 m -> 17 x 11``"，并给出
  ``GridPatternCfg(size=(1.6, 1.0), resolution=0.1)``、``ray_alignment="yaw"``。

排列按上游 ``legged_robot._init_height_points`` 的
``torch.meshgrid(x, y)`` + ``flatten()``：**x 主序**，``index = i_x * 11 + i_y``，
坐标在机身系（x 前、y 左），共 **187** 点。这与本仓训练侧声明的
``terrain_dim = 187``（如 ``assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2/contract.py:22``）
一致。

同一网格上给出两条取数路径，用于「外部雷达（点云）」与「内置射线 heightfield」
的**逐格对齐回归**：

1. :func:`build_height_scan_from_points` —— 3D 点云按格子聚合 ``min z``（雷达链路）；
2. :func:`build_height_scan_from_terrain` —— 在网格点上精确采样地形（内置射线链路）。

取值约定与上游一致：``value = base_z - terrain_z``（米，机身越高值越大），
可选裁剪与缩放（HIMLoco 训练侧为 ``clip(-1, 1) * obs_scales.height_measurements``，
其中 ``height_measurements = 5.0``）——本模块默认返回**未缩放的原始米值**，
缩放留在策略侧，便于对齐回归直接比较。

纯 Python 实现（无 numpy）：控制面保持轻依赖，网格规模只有 187 格。
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable, Sequence

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/perception/height-scan", tags=["perception"])

GRID_SPACING_M = 0.1
MEASURED_POINTS_X: tuple[float, ...] = tuple(round(-0.8 + 0.1 * i, 10) for i in range(17))
MEASURED_POINTS_Y: tuple[float, ...] = tuple(round(-0.5 + 0.1 * i, 10) for i in range(11))
GRID_SHAPE: tuple[int, int] = (len(MEASURED_POINTS_X), len(MEASURED_POINTS_Y))
GRID_POINTS: int = GRID_SHAPE[0] * GRID_SHAPE[1]

# 上游训练侧口径（仅记录，便于策略侧对齐；本模块默认不施加）
TRAIN_OBS_CLIP: tuple[float, float] = (-1.0, 1.0)
TRAIN_OBS_SCALE = 5.0

SOURCE = (
    "legged_gym measured_points grid via 00_resources/HIMLoco "
    "(legged_robot_config.py:55-57) and "
    "assets/robots/deeprobotics_m20/training/source/m20_dreamwaq/config.py:66-68"
)

Point3 = Sequence[float]
TerrainFn = Callable[[float, float], float]


def grid_spec() -> dict[str, Any]:
    """网格契约的自描述（供 API / 文档 / 契约校验使用）。"""
    return {
        "points": GRID_POINTS,
        "shape": list(GRID_SHAPE),
        "spacing_m": GRID_SPACING_M,
        "order": "x_major",
        "frame": "base_link",
        "axes": {"x": "forward", "y": "left"},
        "extent_m": {
            "x": [MEASURED_POINTS_X[0], MEASURED_POINTS_X[-1]],
            "y": [MEASURED_POINTS_Y[0], MEASURED_POINTS_Y[-1]],
        },
        "value": "base_z - terrain_z (m, 未缩放)",
        "train_obs_clip": list(TRAIN_OBS_CLIP),
        "train_obs_scale": TRAIN_OBS_SCALE,
        "align_with": "heightfield",
        "source": SOURCE,
    }


def grid_offsets() -> list[tuple[float, float]]:
    """机身系网格偏移，按上游 x 主序（``index = i_x * 11 + i_y``）。"""
    return [(x, y) for x in MEASURED_POINTS_X for y in MEASURED_POINTS_Y]


def world_grid_points(base_xy: Sequence[float], base_yaw: float = 0.0) -> list[tuple[float, float]]:
    """187 个测量点的世界坐标（同一 x 主序），供点云侧对齐与调试使用。"""
    return [
        _to_world(float(base_xy[0]), float(base_xy[1]), base_yaw, off_x, off_y)
        for off_x, off_y in grid_offsets()
    ]


def _index_of(offset_x: float, offset_y: float) -> int | None:
    """把机身系偏移映射到网格索引；不在网格内返回 None。"""
    ix = round((offset_x - MEASURED_POINTS_X[0]) / GRID_SPACING_M)
    iy = round((offset_y - MEASURED_POINTS_Y[0]) / GRID_SPACING_M)
    if not 0 <= ix < GRID_SHAPE[0] or not 0 <= iy < GRID_SHAPE[1]:
        return None
    if abs(MEASURED_POINTS_X[ix] - offset_x) > GRID_SPACING_M / 2 + 1e-9:
        return None
    if abs(MEASURED_POINTS_Y[iy] - offset_y) > GRID_SPACING_M / 2 + 1e-9:
        return None
    return ix * GRID_SHAPE[1] + iy


def _to_base_frame(point: Point3, base_xy: Sequence[float], base_yaw: float) -> tuple[float, float, float]:
    dx = float(point[0]) - float(base_xy[0])
    dy = float(point[1]) - float(base_xy[1])
    cos_y, sin_y = math.cos(-base_yaw), math.sin(-base_yaw)
    return dx * cos_y - dy * sin_y, dx * sin_y + dy * cos_y, float(point[2])


def _to_world(base_x: float, base_y: float, base_yaw: float, off_x: float, off_y: float) -> tuple[float, float]:
    cos_y, sin_y = math.cos(base_yaw), math.sin(base_yaw)
    return base_x + off_x * cos_y - off_y * sin_y, base_y + off_x * sin_y + off_y * cos_y


def _finish(raw: list[float], *, clip: tuple[float, float] | None, scale: float) -> list[float]:
    out = list(raw)
    if clip is not None:
        low, high = clip
        out = [min(max(value, low), high) for value in out]
    if scale != 1.0:
        out = [value * scale for value in out]
    return [round(value, 9) for value in out]


def build_height_scan_from_points(
    points: Iterable[Point3],
    base_xy: Sequence[float],
    base_z: float,
    base_yaw: float = 0.0,
    *,
    clip: tuple[float, float] | None = None,
    scale: float = 1.0,
    fill: float = 0.0,
    max_range: float | None = None,
    aggregate: str = "min",
) -> list[float]:
    """点云 → 187 维高度扫描（雷达链路）。

    每个网格单元聚合落入其中点的 ``z``：``aggregate="min"`` 取最低点（与
    ``perception_observations`` 中 ``lidar_height_scan`` 声明的
    ``min_z_per_cell`` 一致），``"max"``/``"mean"`` 便于交叉验证。
    空单元填 ``fill``。
    """
    if aggregate not in {"min", "max", "mean"}:
        raise ValueError(f"unsupported aggregate: {aggregate!r}")
    if len(base_xy) != 2:
        raise ValueError("base_xy must be (x, y)")

    buckets: dict[int, list[float]] = {}
    for point in points:
        if len(point) < 3:
            continue
        skip = False
        if max_range is not None:
            dx = float(point[0]) - float(base_xy[0])
            dy = float(point[1]) - float(base_xy[1])
            skip = math.hypot(dx, dy) > max_range
        if skip:
            continue
        off_x, off_y, z = _to_base_frame(point, base_xy, base_yaw)
        index = _index_of(off_x, off_y)
        if index is not None:
            buckets.setdefault(index, []).append(z)

    raw: list[float] = []
    for index in range(GRID_POINTS):
        zs = buckets.get(index)
        if not zs:
            raw.append(fill)
            continue
        if aggregate == "min":
            z = min(zs)
        elif aggregate == "max":
            z = max(zs)
        else:
            z = sum(zs) / len(zs)
        raw.append(float(base_z) - z)
    return _finish(raw, clip=clip, scale=scale)


def build_height_scan_from_terrain(
    terrain_height: TerrainFn,
    base_xy: Sequence[float],
    base_z: float,
    base_yaw: float = 0.0,
    *,
    clip: tuple[float, float] | None = None,
    scale: float = 1.0,
) -> list[float]:
    """地形函数精确采样 → 187 维高度扫描（内置射线 heightfield 链路）。"""
    if len(base_xy) != 2:
        raise ValueError("base_xy must be (x, y)")
    raw: list[float] = []
    for off_x, off_y in grid_offsets():
        world_x, world_y = _to_world(float(base_xy[0]), float(base_xy[1]), base_yaw, off_x, off_y)
        raw.append(float(base_z) - float(terrain_height(world_x, world_y)))
    return _finish(raw, clip=clip, scale=scale)


def align_height_scans(
    reference: Sequence[float],
    candidate: Sequence[float],
    *,
    tolerance: float,
) -> dict[str, Any]:
    """逐格比较两条 187 维高度扫描，返回偏差统计与判定。"""
    if len(reference) != len(candidate):
        raise ValueError(f"维度不一致：{len(reference)} vs {len(candidate)}")
    diffs = [abs(float(a) - float(b)) for a, b in zip(reference, candidate)]
    worst = max(range(len(diffs)), key=lambda i: diffs[i]) if diffs else 0
    max_abs = max(diffs) if diffs else 0.0
    return {
        "cells": len(diffs),
        "max_abs_diff": max_abs,
        "mean_abs_diff": (sum(diffs) / len(diffs)) if diffs else 0.0,
        "worst_index": worst,
        "worst_offset": list(grid_offsets()[worst]) if diffs else None,
        "tolerance": tolerance,
        "within_tolerance": max_abs <= tolerance + 1e-12,
    }


def _sample_terrain(terrain_height: TerrainFn, base_xy: Sequence[float], base_yaw: float, *, step: float) -> list[Point3]:
    """在机身周围按 ``step`` 采样地形，模拟雷达点云（世界系）。"""
    points: list[Point3] = []
    span = 1.6
    n = int(round(span / step))
    cx, cy = float(base_xy[0]), float(base_xy[1])
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            world_x = cx + i * step
            world_y = cy + j * step
            points.append((world_x, world_y, terrain_height(world_x, world_y)))
    return points


def alignment_selftest(*, step: float = 0.02) -> dict[str, Any]:
    """用合成地形跑「点云 vs 射线」逐格对齐回归。

    每个用例给出期望上界 ``bound``（来自采样离散化分析，见各用例注释）：
    - ``flat``：平面，两条链路必须**完全一致**（差 0）；
    - ``slope_10pct``：10% 斜坡，单元内 min-z 与格点采样的差 ≤ 1 格 × 坡度 = 0.01 m；
    - ``step_0.2``：0.2 m 台阶，跨界单元最多差一个台阶高（0.2 m）；
    - ``yaw_45deg``：平面 + 机身偏航 45°，仍需完全一致（校验旋转与索引一致性）。
    """
    yaw = math.radians(45.0)
    base_xy = (0.3, -0.2)
    base_z = 0.45
    # 台阶边界刻意切在单元内部（距单元中心 0.03 m），以便暴露离散化差异：
    # 单元中心在高侧、而单元内最低采样点落在低侧 → 该单元差一个台阶高。
    step_y = base_xy[1] - 0.03
    # (name, terrain, bound, base_yaw, note)
    cases: list[tuple[str, TerrainFn, float, float, str]] = [
        ("flat", lambda x, y: 0.0, 0.0, 0.0, "平面：两条链路必须完全一致"),
        ("slope_10pct", lambda x, y: 0.1 * y, GRID_SPACING_M * 0.1 + 1e-9, 0.0,
         "10% 斜坡：单元内离散化上界 = 1 格 × 坡度 = 0.01 m"),
        ("step_0.2", lambda x, y: 0.2 if y > step_y else 0.0, 0.2 + 1e-9, 0.0,
         "0.2 m 台阶（边界切在单元内部）：跨界单元最多差一个台阶高"),
        ("yaw_45deg", lambda x, y: 0.0, 0.0, yaw,
         "平面 + 45° 机身偏航：旋转与索引必须一致"),
    ]

    results = []
    for name, terrain, bound, case_yaw, note in cases:
        reference = build_height_scan_from_terrain(terrain, base_xy, base_z, case_yaw)
        candidate = build_height_scan_from_points(
            _sample_terrain(terrain, base_xy, case_yaw, step=step), base_xy, base_z, case_yaw
        )
        report = align_height_scans(reference, candidate, tolerance=bound)
        report.update({"name": name, "note": note, "bound": bound, "sample_step_m": step})
        results.append(report)

    failures = [case["name"] for case in results if not case["within_tolerance"]]
    return {
        "success": True,
        "grid": grid_spec(),
        "cases": results,
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
    }


def terrain_function_from_map(terrain_map: Any) -> TerrainFn:
    """把 ``backend.terrain_gen`` 的 ``TerrainMap`` 适配成地形高度函数（纯 Python 双线性采样）。

    约定与 terrain_gen 的 arena 一致：世界 ``x ∈ [-length/2, length/2]`` 映射到**列**、
    ``y ∈ [-width/2, width/2]`` 映射到**行**，以单元中心为采样锚点，越界按边界钳制；
    高度 = 归一化值 × ``config.height``（``TerrainMap.heights`` 为 0..1）。
    """
    heights = terrain_map.heights
    config = terrain_map.config
    rows, cols = int(config.rows), int(config.cols)
    length, width, height = float(config.length), float(config.width), float(config.height)

    def sample(x: float, y: float) -> float:
        col = min(max((x + length / 2.0) / length * cols - 0.5, 0.0), cols - 1.0)
        row = min(max((y + width / 2.0) / width * rows - 0.5, 0.0), rows - 1.0)
        c0, r0 = int(math.floor(col)), int(math.floor(row))
        c1, r1 = min(c0 + 1, cols - 1), min(r0 + 1, rows - 1)
        fx, fy = col - c0, row - r0
        v00, v10 = float(heights[r0][c0]), float(heights[r0][c1])
        v01, v11 = float(heights[r1][c0]), float(heights[r1][c1])
        value = (v00 * (1 - fx) + v10 * fx) * (1 - fy) + (v01 * (1 - fx) + v11 * fx) * fy
        return value * height

    return sample


def map_alignment_selftest(*, kind: str = "noise", seed: int = 0, step: float = 0.02) -> dict[str, Any]:
    """用**项目自己的地形生成器**跑一次对齐回归（真实地形，非合成函数）。

    期望上界由该地形的最大局部坡度推导：单元半对角线 0.0707 m + 采样格点
    ``step·√2/2``，即 ``bound = max_slope × (0.0707 + step·0.7071) × 1.05``。
    """
    from backend.terrain_gen.generators import generate_terrain
    from backend.terrain_gen.models import TerrainConfig

    config = TerrainConfig(kind=kind, rows=128, cols=128, length=8.0, width=8.0, height=0.8, seed=seed)
    terrain_map = generate_terrain(config)
    terrain = terrain_function_from_map(terrain_map)

    cell_x, cell_y = config.length / config.cols, config.width / config.rows
    max_slope = 0.0
    heights = terrain_map.heights
    for row in range(config.rows):
        for col in range(config.cols - 1):
            grade = abs(float(heights[row][col + 1]) - float(heights[row][col])) * config.height / cell_x
            max_slope = max(max_slope, grade)
    for row in range(config.rows - 1):
        for col in range(config.cols):
            grade = abs(float(heights[row + 1][col]) - float(heights[row][col])) * config.height / cell_y
            max_slope = max(max_slope, grade)

    base_xy, base_z, yaw = (0.0, 0.0), 0.6, 0.0
    bound = max_slope * (0.0707 + step * 0.7071) * 1.05
    reference = build_height_scan_from_terrain(terrain, base_xy, base_z, yaw)
    candidate = build_height_scan_from_points(
        _sample_terrain(terrain, base_xy, yaw, step=step), base_xy, base_z, yaw
    )
    report = align_height_scans(reference, candidate, tolerance=bound)
    report.update(
        {
            "name": f"project_terrain_{kind}",
            "terrain": {"kind": kind, "seed": seed, "shape": [config.rows, config.cols],
                        "length_m": config.length, "width_m": config.width, "height_m": config.height},
            "max_slope": max_slope,
            "bound": bound,
            "sample_step_m": step,
            "note": "项目地形生成器 + 双线性采样；上界由最大局部坡度推导",
        }
    )
    return {
        "success": True,
        "grid": grid_spec(),
        "verdict": "pass" if report["within_tolerance"] else "fail",
        "case": report,
    }


@router.get("/grid")
async def height_scan_grid():
    """返回机身高度扫描网格契约（187 点，x 主序，机身系，0.1 m）。"""
    spec = grid_spec()
    return {"success": True, "grid": spec}


@router.get("/selftest")
async def height_scan_selftest(step: float = 0.02):
    """跑「点云 vs 射线」逐格对齐回归（合成地形，离线可复现）。"""
    if not 0.005 <= step <= 0.1:
        raise HTTPException(status_code=400, detail="step 需在 [0.005, 0.1] 之间")
    return alignment_selftest(step=step)


@router.get("/selftest-map")
async def height_scan_selftest_map(kind: str = "noise", seed: int = 0, step: float = 0.02):
    """用项目地形生成器（``backend/terrain_gen``）跑对齐回归。"""
    from backend.terrain_gen.models import SUPPORTED_TERRAIN_TYPES

    if kind not in SUPPORTED_TERRAIN_TYPES:
        raise HTTPException(status_code=400, detail=f"kind 需为 {', '.join(SUPPORTED_TERRAIN_TYPES)}")
    if not 0.005 <= step <= 0.1:
        raise HTTPException(status_code=400, detail="step 需在 [0.005, 0.1] 之间")
    return map_alignment_selftest(kind=kind, seed=seed, step=step)
