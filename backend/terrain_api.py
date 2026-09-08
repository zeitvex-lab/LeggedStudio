"""场景与地图库 API（T4.2，批次 4 / M5）。

backend/terrain_gen（ArenaX 移植）的 HTTP 面：
  GET  /api/terrain/catalog   5 种地形 + 11 种障碍组件目录
  POST /api/terrain/generate  参数化生成场景 → XML + 高度图 PNG + JSON 元数据三件套
  GET  /api/terrain/scenes    已保存场景（Scenario Contract 注册表）
  POST /api/terrain/scenes    保存场景条目（地形参数 + 元数据 → Scenario Contract）

场景落盘 workspace/scenes/<scene_id>/（XML/PNG/metadata），注册表 registry.json
与 contracts/scenario-contract-1.1 的 terrain 字段直接对应（报告 9 §1.3）。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.terrain_gen import (
    SUPPORTED_ELEMENT_TYPES,
    SUPPORTED_TERRAIN_TYPES,
    TerrainConfig,
    export_mujoco,
    generate_terrain,
)

router = APIRouter(prefix="/api/terrain", tags=["terrain"])

ROOT = Path(__file__).resolve().parents[1]
SCENES_DIR = ROOT / "workspace" / "scenes"
REGISTRY = SCENES_DIR / "registry.json"
SCENE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class GenerateRequest(BaseModel):
    kind: str = "flat"
    rows: int = Field(default=32, ge=8, le=256)
    cols: int = Field(default=32, ge=8, le=256)
    seed: int = 0
    obstacle_count: int = Field(default=3, ge=0, le=64)
    scene_id: str | None = None


class SceneEntryRequest(BaseModel):
    scene_id: str
    label: str
    terrain_kind: str
    seed: int = 0
    command_limits: dict[str, float] = Field(default_factory=lambda: {"vx": 1.0, "vy": 1.0, "wz": 1.0})
    termination: dict[str, Any] = Field(default_factory=dict)
    assessment: dict[str, Any] = Field(default_factory=dict)


def _registry_rows() -> list[dict]:
    if not REGISTRY.exists():
        return []
    try:
        rows = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
        return rows if isinstance(rows, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_registry(rows: list[dict]) -> None:
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@router.get("/catalog")
async def terrain_catalog():
    return {
        "success": True,
        "terrain_types": list(SUPPORTED_TERRAIN_TYPES),
        "element_types": list(SUPPORTED_ELEMENT_TYPES),
        "note": "地形 5 种 + 障碍组件 11 种（ArenaX terrain_generator 移植，报告 9 §1）",
    }


@router.post("/generate")
async def generate_scene(request: GenerateRequest):
    if request.kind not in SUPPORTED_TERRAIN_TYPES:
        raise HTTPException(status_code=422, detail=f"不支持的地形类型 {request.kind}；可选：{', '.join(SUPPORTED_TERRAIN_TYPES)}")
    scene_id = request.scene_id or f"{request.kind}_{request.seed}_{int(time.time())}"
    if not SCENE_ID_PATTERN.fullmatch(scene_id):
        raise HTTPException(status_code=422, detail=f"scene_id {scene_id!r} 不合法（^[a-z0-9][a-z0-9_-]*$）")
    out_dir = SCENES_DIR / scene_id
    out_dir.mkdir(parents=True, exist_ok=True)
    terrain = generate_terrain(TerrainConfig(
        kind=request.kind, rows=request.rows, cols=request.cols,
        seed=request.seed, obstacle_count=request.obstacle_count,
    ))
    paths = export_mujoco(terrain, out_dir)
    manifest = {
        "scene_id": scene_id,
        "terrain_kind": request.kind,
        "seed": request.seed,
        "rows": request.rows,
        "cols": request.cols,
        "files": {key: Path(value).name for key, value in paths.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"success": True, "scene_id": scene_id, "out_dir": str(out_dir), **manifest}


@router.get("/scenes")
async def list_scenes():
    return {"success": True, "scenes": _registry_rows()}


@router.post("/scenes")
async def save_scene_entry(entry: SceneEntryRequest):
    if not SCENE_ID_PATTERN.fullmatch(entry.scene_id):
        raise HTTPException(status_code=422, detail=f"scene_id {entry.scene_id!r} 不合法")
    rows = [row for row in _registry_rows() if row.get("scene_id") != entry.scene_id]
    rows.append({
        "schema_version": "scenario-contract-1.1",
        "scene_id": entry.scene_id,
        "label": entry.label,
        "terrain": {"kind": entry.terrain_kind, "seed": entry.seed},
        "command_limits": entry.command_limits,
        "termination": entry.termination,
        "assessment": entry.assessment,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _save_registry(rows)
    return {"success": True, "scene_id": entry.scene_id, "total": len(rows)}
