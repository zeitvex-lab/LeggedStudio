"""面板 CLI 投影 provider（registry/panels/index.json 的 ``cli.provider`` 落点）。

一切皆插件：面板的 CLI 表面**完全声明驱动**——注册表里每条
``cli: {command, provider}`` 指到本模块的一个函数；CLI 侧只有一条通用
``panel <panel_id>`` 命令，按声明做 module:attr 惰性解析后调用并打印。
新增面板 = 注册表加一行 + 本模块加一个 provider 函数，CLI 零改动。

每个 provider 都是**纯数据函数**（返回 JSON 可序列化对象，不做打印、
不做退出码），并且**复用 backend 同一实现**（单一真值来源）——与 Web
面板走同一份读数，不存在"CLI 看到另一套数据"。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

_PROVIDER_PREFIX = "backend.cli_panels:"


def resolve_provider(spec: str) -> Callable[[], Any]:
    """把 ``backend.cli_panels:fn_name`` 声明解析成可调用（fail-loud）。

    声明缺失、格式不对、目标不存在都直接抛错——绝不静默降级成空结果
    （一条静默成功的面板命令比报错更误导）。
    """
    if not spec.startswith(_PROVIDER_PREFIX):
        raise ValueError(
            f"provider 声明必须是 {_PROVIDER_PREFIX}<fn> 形式，收到 {spec!r}"
        )
    name = spec[len(_PROVIDER_PREFIX):]
    fn = globals().get(name)
    if not callable(fn):
        available = sorted(
            k for k, v in globals().items() if callable(v) and not k.startswith("_")
        )
        raise ValueError(f"provider {spec!r} 不存在；本模块可用：{available}")
    return fn


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1] / "workspace"


def _runs_entries() -> tuple[list[dict[str, Any]], list[str]]:
    """训练 Run 清单读数：与 ``run list`` / ``training list`` 同一实现。"""
    from backend.training import runs

    root = _workspace_root()
    entries: list[dict[str, Any]] = []
    skipped: list[str] = []
    if root.is_dir():
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            if not (child / "run.json").is_file():
                skipped.append(child.name)
                continue
            try:
                record = runs.load_run(child)
            except (TypeError, ValueError, KeyError):
                record = None
            if record is None:
                skipped.append(child.name)
                continue
            entries.append({
                "run_id": record.run_id,
                "robot_id": record.robot_id,
                "seed": record.seed,
                "status": record.status,
                "created_at": record.created_at,
            })
    return entries, skipped


# ---------------------------------------------------------------- providers


def home_status() -> dict[str, Any]:
    """首页状态汇总：机器人包 / 训练 Run / 产物 / 面板 数量一览。"""
    from backend.panel_registry import load_panels
    from backend.policy_artifacts import OUT_DIR, load_index
    from backend.robot_packages import list_robot_packages

    packages = list_robot_packages()
    run_entries, skipped = _runs_entries()
    artifacts = load_index(OUT_DIR)
    return {
        "packages": len(packages),
        "runs": len(run_entries),
        "artifacts": len(artifacts),
        "panels": len(load_panels()),
        "skipped_dirs": len(skipped),
    }


def packages_list() -> dict[str, Any]:
    """机器人工作台：包索引（与 ``packages list`` / Web 同一实现）。"""
    from backend.robot_packages import list_robot_packages

    packages = list_robot_packages()
    return {
        "count": len(packages),
        "packages": [
            {
                "robot_id": p.get("robot_id"),
                "family": p.get("family"),
                "source": p.get("source"),
            }
            for p in packages
        ],
    }


def training_list() -> dict[str, Any]:
    """训练任务：Run 清单（与 ``run list`` 同一实现）。"""
    entries, skipped = _runs_entries()
    return {"count": len(entries), "runs": entries, "skipped": skipped}


def config_list() -> dict[str, Any]:
    """训练配置：任务档案（任务=四轴拼装入口，profiles.json 唯一来源）。"""
    from backend.task_profiles_api import _load_profiles

    profiles = _load_profiles()
    return {
        "count": len(profiles),
        "profiles": [
            {
                "task_id": p.get("task_id"),
                "family": p.get("family"),
                "skill": p.get("skill"),
                "evaluator": p.get("evaluator"),
            }
            for p in profiles
        ],
    }


def simulation_list() -> dict[str, Any]:
    """基础仿真：任务档案 + 浏览器可用性（与 /api/task-profiles 同一实现）。"""
    from backend.task_profiles_api import _browser_blockers, _base_scenario, _load_profiles, _profile_summary

    summaries = []
    for profile in _load_profiles():
        task_id = profile.get("task_id")
        scenario = _base_scenario(profile)
        summaries.append(_profile_summary(profile, scenario))
    blockers_by_task = {}
    for profile in _load_profiles():
        scenario = _base_scenario(profile)
        blockers_by_task[profile.get("task_id")] = _browser_blockers(profile, scenario)
    for item in summaries:
        item["browser_blockers"] = blockers_by_task.get(item.get("task_id")) or []
        item["browser_ready"] = not item["browser_blockers"]
    return {"count": len(summaries), "profiles": summaries}


def navmap_list() -> dict[str, Any]:
    """高级仿真：仿真/导航地图清单（backend.scenario_maps 唯一来源）。"""
    from backend.scenario_maps import MAPS

    return {
        "count": len(MAPS),
        "maps": [
            {"map_id": map_id, **{k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}}
            for map_id, meta in sorted(MAPS.items())
        ],
    }


def deploy_summary() -> dict[str, Any]:
    """部署：全部机器人包的部署契约门禁裁决（deploy_gate_report 同一实现）。"""
    from backend.deploy_pack import RobotPackageNotFound, deploy_gate_report
    from backend.robot_packages import list_robot_packages

    rows: list[dict[str, Any]] = []
    for pkg in list_robot_packages():
        robot_id = pkg.get("robot_id")
        try:
            report = deploy_gate_report(robot_id)
            rows.append({
                "robot_id": robot_id,
                "ok": bool(report.get("ok")),
                "blockers": report.get("blockers") or [],
            })
        except (RobotPackageNotFound, ValueError) as exc:
            rows.append({"robot_id": robot_id, "ok": False, "blockers": [str(exc)]})
    return {
        "count": len(rows),
        "ready": sum(1 for r in rows if r["ok"]),
        "robots": rows,
    }


def artifacts_list() -> dict[str, Any]:
    """策略档案：出库索引（与 ``artifact list`` 同一实现）。"""
    from backend.policy_artifacts import OUT_DIR, load_index

    index = load_index(OUT_DIR)
    artifacts = [
        {
            "artifact_id": artifact_id,
            "kind": entry.get("kind"),
            "produced": entry.get("kind") == "produced",
            "onnx_sha256_prefix": (entry.get("onnx_sha256") or "")[:12] or None,
        }
        for artifact_id, entry in sorted(index.items())
    ]
    return {
        "out_dir": str(OUT_DIR),
        "count": len(artifacts),
        "artifacts": artifacts,
    }
