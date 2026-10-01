"""任务档 HTTP 面（高级仿真 = "任务 = 机器人的插件"的运行时入口）。

与 `/api/task-plugins` 的分工（**两层组合，不合并**——registry/tasks 的 note 同一口径）：

* 插件（`backend/task_plugins`）：**感知/命令绑定声明**——这个任务需要哪些传感器、
  命令谁出（policy/planner/script）；
* 任务档（`registry/tasks`，本模块）：**可运行装配**——地图/航点/指令源/判据/
  端口可用性。

两个端点，刻意都很薄（判据在 `backend.task_plugins` 与注册表本身，这里只做组装与
诚实门）：

* ``GET /api/task-profiles`` —— 列出全部任务档，**按浏览器执行器逐档算好可用性**
  （`browser_ok` + `browser_blockers`）⇒ 页面下拉直接消费，不再自己读静态注册表、
  也不再自己猜"哪个端口能跑"；
* ``GET /api/task-profiles/{task_id}/assemble`` —— 把一档组装成**完整场景载荷**
  （可直接喂 applyScenario / 场景编辑器），如实附上插件 readiness 与阻断清单。

诚实纪律（与 task_plugins 同级）：**声明 availability ≠ 这个执行器能跑**——
follow_line 声明了 browser 但 command_source=script 没有浏览器执行器，阻断照实列出；
任务档组装出来一律带回 `blockers`，前端拿到非空就**拒绝应用**并展示原因。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/task-profiles", tags=["task-profiles"])

ROOT = Path(__file__).resolve().parents[1]
PROFILES_FILE = ROOT / "registry" / "tasks" / "profiles.json"

#: 组装场景的默认时长（秒）——任务档未声明 episode 时用；与场景编辑器默认值一致。
DEFAULT_EPISODE_S = 60.0

#: 判据 CLI 按任务类映射（与任务坞此前内嵌的口径同源，收拢到服务端一处）。
CLI_CRITERIA_BY_CLASS: dict[str, str] = {
    "navigation": "python tools/run_task_profile.py --task {task_id}",
    "traversal": "python tools/validate_traversal_progress.py --profile <档案> --checkpoint <model.pt>",
    "velocity": "python tools/check_user_criteria.py --robot <机型> --policy <策略id>",
    "parkour": "python tools/check_user_criteria.py --robot <机型> --policy <策略id>",
    "balance": "python tools/check_user_criteria.py --robot <机型> --policy <策略id>",
}
#: follow 类的判据目前只在浏览器跟跑里看（hold_ratio），headless 未接——如实说，不画饼。
CLI_CRITERIA_FOLLOW = "跟随类判据（hold_ratio）当前仅浏览器跟跑面；headless 工具未接"


class TaskProfileError(Exception):
    """任务档注册表不合法 / id 不存在（fail-closed，带可用清单）。"""


def _load_profiles(path: Path | None = None) -> list[dict[str, Any]]:
    source = Path(path) if path is not None else PROFILES_FILE
    if not source.is_file():
        raise TaskProfileError(f"任务档注册表不存在：{source}")
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    profiles = raw.get("profiles") if isinstance(raw, dict) else None
    if not isinstance(profiles, list) or not profiles:
        raise TaskProfileError("任务档注册表缺少非空 profiles 数组")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in profiles:
        task_id = str(item.get("task_id") or "")
        if not task_id:
            raise TaskProfileError("任务档缺 task_id")
        if task_id in seen:
            raise TaskProfileError(f"任务档 id 重复：{task_id}")
        seen.add(task_id)
        out.append(item)
    return out


def _profile(task_id: str, path: Path | None = None) -> dict[str, Any]:
    profiles = _load_profiles(path)
    for item in profiles:
        if item.get("task_id") == task_id:
            return item
    raise TaskProfileError(
        f"未知任务档 {task_id!r}（可用：{', '.join(p['task_id'] for p in profiles)}）"
    )


def _waypoints_for(profile: dict[str, Any]) -> list[dict[str, float]]:
    """按 waypoints_mode 从地图默认航点派生（**服务端真值**，浏览器不自造）。"""
    from backend.scenario_maps import MAPS

    mode = str((profile.get("assembly") or {}).get("waypoints_mode") or "")
    map_id = str((profile.get("assembly") or {}).get("map_id") or "")
    defaults = (MAPS.get(map_id) or {}).get("default_waypoints") or []
    if not isinstance(defaults, list) or len(defaults) < 2:
        return []
    picked: list[Any]
    if mode == "goal":
        picked = [defaults[0], defaults[-1]]
    elif mode == "default_full":
        picked = list(defaults)
    else:
        return []
    return [{"x": float(p[0]), "y": float(p[1])} for p in picked if isinstance(p, (list, tuple)) and len(p) >= 2]


def _base_scenario(profile: dict[str, Any]) -> dict[str, Any]:
    assembly = profile.get("assembly") or {}
    cls = str(profile.get("class") or "")
    return {
        "schema_version": "scenario-contract-1.1",
        "scenario_id": str(profile.get("task_id") or ""),
        "map_id": str(assembly.get("map_id") or "flat"),
        "mode": "navigation" if cls == "navigation" else "basic",
        "command_source": str(assembly.get("command_source") or "policy"),
        "waypoints": _waypoints_for(profile),
        "episode_length_s": DEFAULT_EPISODE_S,
    }


def _browser_blockers(profile: dict[str, Any], scenario: dict[str, Any]) -> list[str]:
    """这个任务档**浏览器端口**跑不了的**具体原因**（空列表 = 能跑）。

    两道独立闸：端口声明（availability）是产品侧口径，执行器能力（executors 矩阵）
    是 harder truth——声明了 browser 但 command_source 没执行器支持的照旧阻断。
    """
    from backend.executors import _support_gaps, executor as get_executor

    blockers: list[str] = []
    availability = profile.get("availability") or []
    if isinstance(availability, list) and "browser" not in availability:
        blockers.append(f"任务档未声明浏览器端口（availability={availability}）——判据走 headless 工具")
    target = get_executor("browser_wasm")
    blockers.extend(_support_gaps(scenario, target))
    source = str(scenario.get("command_source") or "")
    if source in ("planner", "perception") and len(scenario.get("waypoints") or []) < 2:
        blockers.append(
            f"command_source={source} 需要至少 2 个航点，地图默认航点不足（装配失败）"
        )
    return blockers


def _cli_criteria(profile: dict[str, Any]) -> str:
    cls = str(profile.get("class") or "")
    if cls == "follow":
        return CLI_CRITERIA_FOLLOW
    template = CLI_CRITERIA_BY_CLASS.get(cls)
    if not template:
        return ""
    return template.format(task_id=str(profile.get("task_id") or ""))


def _profile_summary(profile: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": profile.get("task_id"),
        "display_name": profile.get("display_name") or profile.get("task_id"),
        "class": profile.get("class"),
        "summary": profile.get("summary"),
        "availability": profile.get("availability") or [],
        "plugin_id": profile.get("plugin_id"),
        "browser_ok": not _browser_blockers(profile, scenario),
        "browser_blockers": _browser_blockers(profile, scenario),
    }


@router.get("")
async def list_task_profiles() -> dict[str, Any]:
    """列出任务档（含**按浏览器执行器算好**的可用性——诚实到"能不能跑、为什么"）。"""
    try:
        profiles = _load_profiles()
    except TaskProfileError as exc:
        raise HTTPException(status_code=500, detail=f"任务档注册表不合法：{exc}") from exc
    items = [_profile_summary(p, _base_scenario(p)) for p in profiles]
    return {"success": True, "count": len(items), "profiles": items}


class AssembleResponse(BaseModel):
    """组装结果（payload 直出给前端；blockers 非空时前端必须拒绝应用）。"""

    success: bool = True
    task_id: str
    display_name: str = ""
    cls: str = Field(default="", alias="class")
    scenario: dict[str, Any]
    blockers: list[str] = Field(default_factory=list)
    readiness: dict[str, Any] | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)
    cli_criteria: str = ""
    applied: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


@router.get("/{task_id}/assemble")
async def assemble(task_id: str) -> dict[str, Any]:
    """任务档 → 完整场景载荷（**不落盘**，回载荷给调用方）。"""
    try:
        profile = _profile(task_id)
    except TaskProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    scenario = _base_scenario(profile)
    blockers = _browser_blockers(profile, scenario)
    applied: dict[str, Any] = {}
    readiness: dict[str, Any] | None = None

    plugin_id = str(profile.get("plugin_id") or "")
    if plugin_id:
        # 感知/命令绑定委托插件实例化（同一份合并规则，不在这里再写一遍）。
        from backend.task_plugins import TaskPluginError, instantiate_task_plugin

        try:
            inst = instantiate_task_plugin(plugin_id, scenario=scenario)
        except TaskPluginError as exc:
            blockers.append(f"感知插件 {plugin_id} 实例化失败：{exc}")
        else:
            scenario = inst["scenario"]
            readiness = inst["readiness"]
            applied = inst.get("applied") or {}

    return AssembleResponse(
        task_id=str(profile.get("task_id") or ""),
        display_name=str(profile.get("display_name") or ""),
        cls=str(profile.get("class") or ""),
        scenario=scenario,
        blockers=blockers,
        readiness=readiness,
        criteria=profile.get("criteria") or {},
        cli_criteria=_cli_criteria(profile),
        applied=applied,
    ).model_dump(by_alias=True)
