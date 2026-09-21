"""H18：Episode 回放 API（只读）。

* `GET /api/episode/list` —— 有哪些 episode（含步数/指令/时间）
* `GET /api/episode/{run}/{conn}/{episode}` —— 一集的 manifest + 逐步记录 + **"预测 vs 实际"叠加**

记录根目录取 `LEGGED_STUDIO_EPISODE_DIR`，缺省落在数据目录下的 `episodes/`（与其它运行产物同处）。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.episode_recorder import (
    EPISODE_SCHEMA_VERSION,
    _atomic_write_json,
    _utc_now_iso_ms,
    build_overlay,
    list_episodes,
    read_episode,
)

router = APIRouter(prefix="/api/episode", tags=["episode"])


def episode_root() -> Path:
    """记录根目录（可用 LEGGED_STUDIO_EPISODE_DIR 覆盖；否则用数据目录）。"""

    override = os.environ.get("LEGGED_STUDIO_EPISODE_DIR")
    if override:
        return Path(override)
    # 解析规则唯一实现见 backend/paths.data_dir；**默认值**留给这里（Episode 存档之家）
    from backend.paths import data_dir

    return data_dir(default=Path.home() / ".legged_studio") / "episodes"


@router.post("/import")
async def import_episode(payload: dict[str, Any]) -> dict[str, Any]:
    """**浏览器运行**产出的 episode 落盘（B4 的写侧）。

    此前 `EpisodeRecorder` 只在测试里被实例化：服务端 `/api/navigation/run` 没有 UI 触发，
    于是 `/api/episode/list` 结构上恒空、回放页永远显示空态。现在浏览器场景跑完把
    轨迹 + 判据摘要 POST 到这里，按**同一套目录布局**落盘（`read_episode` 直接能读），
    回放页的"预测 vs 实际"因此第一次有真数据。

    记录字段沿用 LightNav 语义：`waypoints` = 该步**指令**位置（世界系），
    `pointing.actual` = 该步**实测**位置。浏览器运行没有相机标定，
    故 `overlay_forward_offset` 恒为 None（未标定就别假装准）。
    """

    run = str(payload.get("run") or "").strip()
    conn = str(payload.get("conn") or "").strip()
    records = payload.get("records")
    if not run or "/" in run or "\\" in run or run in {".", ".."}:
        raise HTTPException(status_code=400, detail="run 非法（不允许路径分隔符）")
    if not conn or "/" in conn or "\\" in conn or conn in {".", ".."}:
        raise HTTPException(status_code=400, detail="conn 非法（不允许路径分隔符）")
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=400, detail="records 必须是非空数组")

    episode_no = int(payload.get("episode") or 1)
    root = episode_root()
    directory = root / f"run_{run}" / conn / f"episode_{episode_no:03d}"
    # 已存在就拒绝覆盖： episode 是证据，静默改写证据比没有证据更坏
    if (directory / "manifest.json").is_file():
        raise HTTPException(
            status_code=409,
            detail=f"episode 已存在：{directory}（不覆盖；换一个 run/conn 或 episode 号）",
        )

    manifest = dict(payload.get("manifest") or {})
    manifest.setdefault("schema", EPISODE_SCHEMA_VERSION)
    manifest.setdefault("created_at", _utc_now_iso_ms())
    manifest["conn"] = conn
    manifest["episode"] = episode_no
    manifest.setdefault("task", "scenario")
    manifest.setdefault("overlay_forward_offset", None)  # 浏览器运行未做相机标定
    manifest.setdefault("extra", {})
    manifest["extra"] = dict(manifest["extra"])
    manifest["extra"]["origin"] = "browser-wasm"

    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(directory / "manifest.json", manifest)
    written = 0
    with open(directory / "actions.jsonl", "w", encoding="utf-8") as stream:
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            row = dict(record)
            row.setdefault("step", index)
            row.setdefault("seq", index)
            row.setdefault("received_at", _utc_now_iso_ms())
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
        stream.flush()
        os.fsync(stream.fileno())
    _atomic_write_json(directory / "actions.json", [r for r in records if isinstance(r, dict)])

    return {
        "success": True,
        "run": f"run_{run}",
        "conn": conn,
        "episode": episode_no,
        "steps": written,
        "dir": str(directory),
        "replay_url": f"/web/sim2sim/episode_replay.html?run=run_{run}&conn={conn}&episode={episode_no}",
    }


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
