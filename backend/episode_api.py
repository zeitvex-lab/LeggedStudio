"""H18：Episode 回放 API（只读）。

* `GET /api/episode/list` —— 有哪些 episode（含步数/指令/时间）
* `GET /api/episode/{run}/{conn}/{episode}` —— 一集的 manifest + 逐步记录 + **"预测 vs 实际"叠加**

记录根目录取 `LEGGED_STUDIO_EPISODE_DIR`，缺省落在数据目录下的 `episodes/`（与其它运行产物同处）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.episode_recorder import EPISODE_SCHEMA_VERSION, build_overlay, list_episodes, read_episode

router = APIRouter(prefix="/api/episode", tags=["episode"])


def episode_root() -> Path:
    """记录根目录（可用 LEGGED_STUDIO_EPISODE_DIR 覆盖；否则用数据目录）。"""

    override = os.environ.get("LEGGED_STUDIO_EPISODE_DIR")
    if override:
        return Path(override)
    data_dir = os.environ.get("LEGGED_STUDIO_DATA_DIR")
    base = Path(data_dir) if data_dir else Path.home() / ".legged_studio"
    return base / "episodes"


@router.get("/list")
async def list_episode_runs() -> dict[str, Any]:
    root = episode_root()
    episodes = list_episodes(root)
    return {
        "success": True,
        "schema": EPISODE_SCHEMA_VERSION,
        "root": str(root),
        "count": len(episodes),
        "episodes": episodes,
    }


@router.get("/{run}/{conn}/{episode}")
async def get_episode(run: str, conn: str, episode: int) -> dict[str, Any]:
    # 只允许三段名字，防止 ../ 拼出目录穿越（只读接口也不该能被用来读任意文件）
    for label, value in (("run", run), ("conn", conn)):
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise HTTPException(status_code=400, detail=f"非法的 {label}：{value}")
    directory = episode_root() / run / conn / f"episode_{int(episode):03d}"
    try:
        payload = read_episode(directory)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    overlay = build_overlay(payload["manifest"], payload["records"])
    return {
        "success": True,
        "schema": EPISODE_SCHEMA_VERSION,
        "manifest": payload["manifest"],
        "records": payload["records"],
        "step_count": len(payload["records"]),
        # 崩在半步上的痕迹要露出来（"这集的数据不完整"是事实，不藏）
        "truncated_records": payload["truncated_records"],
        "overlay": overlay,
    }
