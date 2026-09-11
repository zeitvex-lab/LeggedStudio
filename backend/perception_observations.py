"""Generic perception observation plugin catalog (Feature 6).

Some perception observations (foot contact, heightfield, depth camera) are
currently inlined in specific robot packages (e.g. Go2's PIE 106x60 depth
camera for stair parkour). This module lifts them into a *generic*, robot- and
package-independent catalog so any profile's policy input can reference a
perception observation item by id.

Each item declares a canonical id, the sensor class it derives from, a width
(dimension) and the scale used at the config level, plus the dot-path that a
policy config would use to enable/attach it. This is the single source of truth
for the Web observation/action mapping board (Feature 3) and the config editor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/perception", tags=["perception"])


@dataclass(frozen=True)
class PerceptionObservationItem:
    id: str
    label: str
    sensor: str                       # proprio | foot_contact | heightfield | depth_camera | lidar
    width: int                        # flat dimension (e.g. 106*60 for PIE depth)
    scale: float
    description: str
    sample_dot_path: str = ""         # config dot-path to attach/enable the item
    meta: dict[str, Any] = field(default_factory=dict)
    obs_source: str = ""              # estimator | proxy | history ("" = not applicable)


# Canonical obs-source decision options for proprio items (Feature 11).
# base_lin_vel can be measured from an estimator, proxied from joint velocities,
# or reconstructed from a history buffer of past states. The Web mapping board
# renders this as a three-way wizard; the chosen value is written into the
# config as the item's obs_source.
OBS_SOURCE_CHOICES: tuple[dict[str, str], ...] = (
    {"value": "estimator", "label": "状态估计器", "hint": "由 IMU/里程计融合估计，最常规，推荐用于平地/低速"},
    {"value": "proxy", "label": "关节速度代理", "hint": "由关节速度映射近似，省去估计器，适合舵机直驱构型"},
    {"value": "history", "label": "历史帧还原", "hint": "用过去若干帧的观测序列还原当前状态，训练时需叠历史帧"},
)


# Canonical catalog of generic perception observation items. Robot packages can
# reference these by id instead of re-implementing them.
PERCEPTION_ITEMS: dict[str, PerceptionObservationItem] = {
    "foot_contact": PerceptionObservationItem(
        id="foot_contact",
        label="足端接触 (Foot Contact)",
        sensor="foot_contact",
        width=4,
        scale=1.0,
        description="四足以二进制/标量表示的接触状态；用于不可穿越与足端稳定约束的底层感知。",
        sample_dot_path="environment.observations.actor.terms.foot_contact",
        meta={"default_legs": 4, "kind": "contact"},
    ),
    "heightfield": PerceptionObservationItem(
        id="heightfield",
        label="地形高度场 (Heightfield)",
        sensor="heightfield",
        width=187,
        scale=1.0,
        description=(
            "机身周围 17×11（0.1 m 步长，1.6 m × 1.0 m）地形高度网格，x 主序；"
            "支撑粗糙地形与上楼决策。网格契约与构造器见 backend/height_scan.py。"
        ),
        sample_dot_path="environment.observations.actor.terms.heightmap",
        meta={
            "kind": "terrain",
            "sample": "measured_points_grid",
            "shape": [17, 11],
            "spacing_m": 0.1,
            "order": "x_major",
            "source": "legged_gym measured_points（HIMLoco / m20_dreamwaq）",
        },
    ),
    "depth_camera": PerceptionObservationItem(
        id="depth_camera",
        label="深度相机 (Depth Camera)",
        sensor="depth_camera",
        width=6360,
        scale=1.0,
        description="PIE 风格 106×60 前向深度相机（87° HFOV，10 列裁剪）；用于楼梯 parkour 等感知任务。",
        sample_dot_path="environment.observations.actor.terms.depth_scan",
        meta={"width_px": 106, "height_px": 60, "hfov_deg": 87.0, "kind": "vision"},
    ),
    "lidar_height_scan": PerceptionObservationItem(
        id="lidar_height_scan",
        label="雷达高度扫描 (LiDAR Height Scan)",
        sensor="lidar",
        width=187,
        scale=1.0,
        description=(
            "把 3D 点云按机身周围 187 个测量点（17×11，0.1 m 步长）聚合 min-z 得到的高度扫描；"
            "网格与 heightfield 完全一致，用于外部雷达链路与内置射线 heightfield 的逐格对齐回归。"
            "构造器与对齐用例见 backend/height_scan.py；标定与内外参约定见 sensor_suite 的 lidar 声明。"
        ),
        sample_dot_path="environment.observations.actor.terms.lidar_height_scan",
        meta={
            "kind": "terrain",
            "grid": "measured_points_grid",
            "grid_shape": [17, 11],
            "grid_size": 187,
            "spacing_m": 0.1,
            "order": "x_major",
            "source_sensor": "lidar",
            "align_with": "heightfield",
            "projection": "min_z_per_cell",
            "value": "base_z - point_z (m)",
        },
    ),
    "base_lin_vel": PerceptionObservationItem(
        id="base_lin_vel",
        label="机身线速度 (Base Lin Vel)",
        sensor="proprio",
        width=3,
        scale=2.0,
        description="机身坐标系下的 (x,y,z) 线速度。观测来源可在 估计器/代理/历史 三选一。",
        sample_dot_path="environment.observations.actor.terms.base_lin_vel",
        obs_source="estimator",
        meta={"observable": "estimator|proxy|history"},
    ),
    "base_ang_vel": PerceptionObservationItem(
        id="base_ang_vel",
        label="机身角速度 (Base Ang Vel)",
        sensor="proprio",
        width=3,
        scale=0.25,
        description="机身坐标系下的 (x,y,z) 角速度。",
        sample_dot_path="environment.observations.actor.terms.base_ang_vel",
    ),
    "projected_gravity": PerceptionObservationItem(
        id="projected_gravity",
        label="投影重力 (Projected Gravity)",
        sensor="proprio",
        width=3,
        scale=1.0,
        description="世界重力在机身上的投影；姿态感知的最简表述。",
        sample_dot_path="environment.observations.actor.terms.projected_gravity",
    ),
    "joint_pos": PerceptionObservationItem(
        id="joint_pos",
        label="关节位置 (Joint Pos)",
        sensor="proprio",
        width=12,
        scale=1.0,
        description="各执行关节的位置（rad / m）。",
        sample_dot_path="environment.observations.actor.terms.joint_pos",
    ),
    "joint_vel": PerceptionObservationItem(
        id="joint_vel",
        label="关节速度 (Joint Vel)",
        sensor="proprio",
        width=12,
        scale=0.05,
        description="各执行关节的速度。",
        sample_dot_path="environment.observations.actor.terms.joint_vel",
    ),
}


def list_perception_items() -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "label": item.label,
            "sensor": item.sensor,
            "width": item.width,
            "scale": item.scale,
            "description": item.description,
            "sample_dot_path": item.sample_dot_path,
            "meta": item.meta,
            "obs_source": item.obs_source,
        }
        for item in PERCEPTION_ITEMS.values()
    ]


@router.get("/items")
async def perception_items():
    """Return the generic perception observation catalog."""
    return {"success": True, "count": len(PERCEPTION_ITEMS), "items": list_perception_items()}


@router.get("/obs-sources")
async def obs_source_choices():
    """Return the canonical obs_source decision options (Feature 11)."""
    return {"success": True, "choices": list(OBS_SOURCE_CHOICES)}


@router.get("/items/{item_id}")
async def perception_item(item_id: str):
    """Return a single perception observation item by id."""
    item = PERCEPTION_ITEMS.get(item_id)
    if item is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown perception item: {item_id}")
    return {"success": True, "item": {
        "id": item.id, "label": item.label, "sensor": item.sensor,
        "width": item.width, "scale": item.scale, "description": item.description,
        "sample_dot_path": item.sample_dot_path, "meta": item.meta,
        "obs_source": item.obs_source,
    }}
