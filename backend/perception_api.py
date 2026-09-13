"""感知闭环的 HTTP 面（S6）：provider 清单 + 地形判定与切换决定。

两个入口：

* ``GET  /api/perception/providers``        —— provider 清单（权威注册表的内容 + 自检）；
* ``POST /api/perception/terrain/evaluate`` —— 按场景 + 位姿做地形判定，并给出切换决定。

**为什么用"场景 + 位姿"而不是上传点云**：浏览器侧 vendored 的 MuJoCo WASM 没有确证导出
射线接口，拿不到机载高度扫描；而服务端有**唯一实现**的高度扫描构造器
（`backend/height_scan.py`）与地形数据（`backend/perception_scene.py`）。浏览器只上传位姿，
判定与切换仍只有一处实现——不会因为端不同而口径漂移。

**fail-closed**：未知场景 / 无法复现的场景直接报错（不按平地处理），
返回值里带 `reproducible` 与 `source`，让调用方能把"依据是什么"显示出来。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.perception_providers import PerceptionProviderError, provider_selftest, provider_specs
from backend.perception_scene import SceneTerrainError, height_scan_at
from backend.skill_switch import plan_switch

router = APIRouter(prefix="/api/perception", tags=["perception"])

DEFAULT_BASE_LIMITS = {"vx": 0.9, "vy": 0.5, "wz": 0.85}


class TerrainEvaluateRequest(BaseModel):
    """按场景与位姿求地形判定（浏览器导航闭环用）。"""

    scene_id: str = Field(description="场景 id：flat 或 workspace/scenes/<id> 下已生成的场景")
    base_xy: list[float] = Field(default_factory=lambda: [0.0, 0.0], min_length=2, max_length=2)
    base_z: float = Field(default=0.45, description="机身高度（米），用于 value = base_z - terrain_z")
    base_yaw: float = 0.0
    base_limits: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_BASE_LIMITS))
    available_policies: list[str] = Field(default_factory=list)
    provider_id: str = "terrain_classifier"


@router.get("/providers")
async def perception_providers() -> dict[str, Any]:
    """感知 provider 权威清单（含自检与未登记文件诊断）。"""
    try:
        specs = [spec.to_dict() for spec in provider_specs()]
    except PerceptionProviderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "count": len(specs), "providers": specs, "selftest": provider_selftest()}


@router.post("/terrain/evaluate")
async def evaluate_terrain_endpoint(request: TerrainEvaluateRequest) -> dict[str, Any]:
    """地形判定 + 切换决定（服务端唯一实现：provider + skill_switch）。"""
    try:
        scan, scene_meta = height_scan_at(
            request.scene_id, request.base_xy, base_z=request.base_z, base_yaw=request.base_yaw
        )
    except SceneTerrainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        from backend.perception_providers import resolve_provider

        provider = resolve_provider(request.provider_id)
    except PerceptionProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reading = provider.update(scan, 0.0)
    switch = plan_switch(
        reading.get("action"),
        base_limits=request.base_limits,
        available_policies=request.available_policies,
    )
    return {
        "success": True,
        "scene": scene_meta,
        "reading": reading,
        "switch": switch,
        "height_scan_points": len(scan),
        "note": (
            "依据 = 场景地形数据 + 上传的位姿（**不是机载射线/深度**）；"
            "机载感知留给原生链路。空场景高度场不可复现时会报错而不是按平地处理。"
        ),
    }
