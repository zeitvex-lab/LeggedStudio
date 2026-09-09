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
    sensor: str                       # proprio | foot_contact | heightfield | depth_camera
    width: int                        # flat dimension (e.g. 106*60 for PIE depth)
    scale: float
    description: str
    sample_dot_path: str = ""         # config dot-path to attach/enable the item
    meta: dict[str, Any] = field(default_factory=dict)


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
        width=180,
        scale=1.0,
        description="机身周围采样地形高度网格（egomotion 局部窗）；支撑粗糙地形与上楼决策。",
        sample_dot_path="environment.observations.actor.terms.heightmap",
        meta={"kind": "terrain", "sample": "radial_grid"},
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
    "base_lin_vel": PerceptionObservationItem(
        id="base_lin_vel",
        label="机身线速度 (Base Lin Vel)",
        sensor="proprio",
        width=3,
        scale=2.0,
        description="机身坐标系下的 (x,y,z) 线速度。",
        sample_dot_path="environment.observations.actor.terms.base_lin_vel",
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
        }
        for item in PERCEPTION_ITEMS.values()
    ]


@router.get("/items")
async def perception_items():
    """Return the generic perception observation catalog."""
    return {"success": True, "count": len(PERCEPTION_ITEMS), "items": list_perception_items()}


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
    }}
