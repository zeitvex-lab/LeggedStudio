"""运行时档位 HTTP 入口（H8 / H9 / H10）。

三份注册表（相机档位、运动指令档位、到达判据）都已有纯函数实现与离线自检，
这里只做薄封装，让工作台/高级仿真页能直接读到**同一份数字**：

* ``GET  /api/limits/motion``                 运动指令档位
* ``POST /api/limits/motion/clamp``           裁剪 + 提示（超限/死区/非有限值）
* ``POST /api/limits/motion/resolve``         死区 → 裁剪 → 加减速限幅 全链路
* ``GET  /api/limits/arrival``                当前生效的到达阈值（单一真值）
* ``POST /api/limits/arrival/waypoint``       航点到达判定
* ``POST /api/limits/arrival/visual-dock``    视觉停靠判定
* ``GET  /api/limits/selftest``               三份自检合并报告
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.arrival_criteria import (
    arrival_selftest,
    effective_thresholds,
    visual_dock_arrival,
    waypoint_arrival,
)
from backend.camera_projection import camera_projection_selftest, distortion_impact
from backend.motion_commands import (
    motion_command_profiles,
    motion_command_selftest,
    resolve_command,
    timeout_policy,
)
from backend.runtime_registry import RegistryError, registry_snapshot

router = APIRouter(prefix="/api/limits", tags=["limits"])


class MotionCommand(BaseModel):
    vx: float = Field(default=0.0)
    vy: float = Field(default=0.0)
    yaw_rate: float = Field(default=0.0)


class ClampRequest(BaseModel):
    command: dict[str, float]
    profile: str | None = None
    previous: dict[str, float] | None = None
    dt: float | None = Field(default=None, gt=0.0)


class WaypointArrivalRequest(BaseModel):
    position_xy: list[float] = Field(min_length=2, max_length=2)
    target_xy: list[float] = Field(min_length=2, max_length=2)
    heading_rad: float | None = None
    target_heading_rad: float | None = None
    consecutive_ticks: int = Field(default=0, ge=0)
    tolerance_m: float | None = Field(default=None, gt=0.0)


class VisualDockRequest(BaseModel):
    lateral_m: float
    forward_m: float
    yaw_error_rad: float
    lost_frame_s: float = Field(default=0.0, ge=0.0)


@router.get("/registry")
async def limits_registry():
    """三份档位注册表的装载状态（含路径与可选 id），供页面提示"数据来自哪里"。"""
    try:
        return {"success": True, **registry_snapshot()}
    except RegistryError as exc:  # pragma: no cover - 仅在文件被删时触发
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/motion")
async def motion_profiles():
    """运动指令档位（H9）：限速 / 频率 / 超时 / 死区 / 加减速。"""
    return {
        "success": True,
        "source": "registry/motion_commands.json",
        "profiles": motion_command_profiles(),
        "timeout_policy": timeout_policy(),
    }


@router.post("/motion/clamp")
async def motion_clamp(request: ClampRequest):
    """裁剪一条运动指令：超限被裁并给出提示，低于死区置零，非有限值拒绝。"""
    result = resolve_command(
        request.command,
        previous=request.previous,
        dt=request.dt,
        profile=request.profile,
    )
    if result.get("command") is None and result.get("accepted") is False:
        # 非法指令不是服务端错误而是「被拒」：返回 200 + accepted=false，
        # 让调用方（遥控前端）自己决定是丢弃还是告警，避免前端把 4xx 当网络故障。
        return {"success": False, **result}
    return {"success": True, **result}


@router.get("/arrival")
async def arrival_criteria_view():
    """当前生效的到达判据（H10 单一真值）。"""
    return {"success": True, **effective_thresholds()}


@router.post("/arrival/waypoint")
async def arrival_waypoint(request: WaypointArrivalRequest):
    """航点到达判定：位置 + 停航向 + 连续稳定拍。"""
    return {
        "success": True,
        "verdict": waypoint_arrival(
            request.position_xy,
            request.target_xy,
            heading_rad=request.heading_rad,
            target_heading_rad=request.target_heading_rad,
            consecutive_ticks=request.consecutive_ticks,
            tolerance_m=request.tolerance_m,
        ),
    }


@router.post("/arrival/visual-dock")
async def arrival_visual_dock(request: VisualDockRequest):
    """视觉停靠判定：横向 / 前向 / 航向容差 + 丢帧时长。"""
    return {
        "success": True,
        "verdict": visual_dock_arrival(
            lateral_m=request.lateral_m,
            forward_m=request.forward_m,
            yaw_error_rad=request.yaw_error_rad,
            lost_frame_s=request.lost_frame_s,
        ),
    }


@router.get("/selftest")
async def limits_selftest():
    """三份自检合并（H8 相机畸变 / H9 指令整形 / H10 到达判据）。"""
    camera = camera_projection_selftest()
    motion = motion_command_selftest()
    arrival = arrival_selftest()
    verdicts = {
        "camera_projection": camera["verdict"],
        "motion_commands": motion["verdict"],
        "arrival_criteria": arrival["verdict"],
    }
    return {
        "success": True,
        "verdict": "pass" if all(v == "pass" for v in verdicts.values()) else "fail",
        "verdicts": verdicts,
        "distortion_impact": {
            pid: distortion_impact(pid)["max_delta_px"]
            for pid in ("ideal-pinhole-1920x1080", "go2-front-fisheye-1920x1080")
        },
        "cases": {"camera_projection": camera["cases"], "motion_commands": motion["cases"], "arrival_criteria": arrival["cases"]},
    }
