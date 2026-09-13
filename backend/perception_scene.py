"""场景 → 地形高度场来源（浏览器侧"感知"的数据来源，服务端唯一解析）。

**为什么需要它**：浏览器 sim2sim 跑的是 WASM 里的 MuJoCo，但 vendored 的 `mujoco.js`
**没有导出射线接口**（`mj_ray` 只存在于 wasm 符号里，JS 侧未确证导出），所以浏览器侧
暂时拿不到机载高度扫描。折中做法是**同源地形数据**：浏览器只上传自身位姿，由服务端用
**同一份场景地形**算出高度扫描再做分类——这样"分类与切换"仍然只有一处实现
（`terrain_classifier` + `skill_switch`），不会因为端不同而口径漂移。

**诚实边界（必须跟着结果一起展示）**：

* 这**不是机载感知**——浏览器侧的依据是"场景地形数据 + 位姿"，不是射线/深度；
  真正的机载射线留给原生链路（MuJoCo 传感器）与后续 WASM 导出确认后；
* 场景必须是**可复现**的：`workspace/scenes/<id>/manifest.json` 里要记下生成参数；
  记不全就标 `reproducible: partial`（例如旧 manifest 没记 `obstacle_count`，按 0 复现
  可能与原场景不同）；
* **未知场景直接报错**，绝不"按平地处理"（那种静默兜底会让分类恒为 flat，看起来一切正常）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENES_DIR = ROOT / "workspace" / "scenes"

#: 有确定高度场的内置场景（与 backend.scenario_maps.MAPS 的 flat 对应）
FLAT_SCENE_IDS = frozenset({"flat"})


class SceneTerrainError(ValueError):
    """场景没有可用的高度场来源（不静默按平地处理）。"""


def scene_terrain_source(scene_id: str, *, scenes_dir: Path | None = None) -> dict[str, Any]:
    """解析场景 → ``{"terrain": callable, "kind", "source", "reproducible", "note"}``。

    抛 :class:`SceneTerrainError`：未知场景 / manifest 缺关键参数 / 地形类型不支持。
    """
    scene_id = str(scene_id or "").strip()
    if not scene_id:
        raise SceneTerrainError("scene_id 不能为空")
    if scene_id in FLAT_SCENE_IDS:
        return {
            "scene_id": scene_id,
            "kind": "flat",
            "terrain": lambda x, y: 0.0,
            "source": "builtin:flat",
            "reproducible": "full",
            "note": "平面场景：高度恒为 0（分类必然为 flat，这是真值而不是兜底）",
        }

    manifest_path = (scenes_dir or DEFAULT_SCENES_DIR) / scene_id / "manifest.json"
    if not manifest_path.is_file():
        raise SceneTerrainError(
            f"场景 {scene_id!r} 没有高度场来源：{manifest_path} 不存在。"
            "请先用 POST /api/terrain/generate 生成场景，或改用 flat。"
            "（这里**不**按平地处理——否则分类会恒为 flat，看起来一切正常）"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SceneTerrainError(f"场景 manifest 不可解析：{manifest_path}（{exc}）") from exc

    kind = str(manifest.get("terrain_kind") or "")
    rows, cols = manifest.get("rows"), manifest.get("cols")
    if not kind or rows is None or cols is None:
        raise SceneTerrainError(
            f"场景 {scene_id!r} 的 manifest 缺 terrain_kind/rows/cols，无法复现地形：{manifest_path}"
        )

    from backend.terrain_gen import SUPPORTED_TERRAIN_TYPES, TerrainConfig, generate_terrain
    from backend.height_scan import terrain_function_from_map

    if kind not in SUPPORTED_TERRAIN_TYPES:
        raise SceneTerrainError(
            f"场景 {scene_id!r} 的地形类型 {kind!r} 不在支持列表 {sorted(SUPPORTED_TERRAIN_TYPES)}"
        )

    obstacle_count = manifest.get("obstacle_count")
    reproducible = "full" if obstacle_count is not None else "partial"
    note = (
        "manifest 记录了完整生成参数，可精确复现"
        if reproducible == "full"
        else "manifest 未记录 obstacle_count，按 0 复现：与原始场景可能存在障碍差异"
    )
    terrain_map = generate_terrain(TerrainConfig(
        kind=kind,
        rows=int(rows),
        cols=int(cols),
        seed=int(manifest.get("seed") or 0),
        obstacle_count=int(obstacle_count or 0),
    ))
    return {
        "scene_id": scene_id,
        "kind": kind,
        "terrain": terrain_function_from_map(terrain_map),
        "source": str(manifest_path),
        "reproducible": reproducible,
        "manifest": {
            "terrain_kind": kind,
            "rows": int(rows),
            "cols": int(cols),
            "seed": int(manifest.get("seed") or 0),
            "obstacle_count": int(obstacle_count or 0),
        },
        "note": note,
    }


def height_scan_at(
    scene_id: str,
    base_xy: list[float] | tuple[float, float],
    *,
    base_z: float,
    base_yaw: float = 0.0,
    scenes_dir: Path | None = None,
) -> tuple[list[float], dict[str, Any]]:
    """在给定位姿上做**同源地形**的 187 维高度扫描（内置射线链路口径）。"""
    from backend.height_scan import build_height_scan_from_terrain

    source: dict[str, Any] = scene_terrain_source(scene_id, scenes_dir=scenes_dir)
    sample: Callable[[float, float], float] = source["terrain"]
    scan = build_height_scan_from_terrain(sample, list(base_xy), float(base_z), float(base_yaw))
    meta = {key: value for key, value in source.items() if key != "terrain"}
    return scan, meta
