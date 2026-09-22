"""**任务插件**：加载 + 列出 + 实例化（把"需要传感器的任务"自动补齐成可跑的场景）。

## 一件任务此前要人肉配三处（本模块把它们收成一次调用）

1. **场景 `perception` 开关**（`heightfield` / `depth_camera` / `foot_contact` / `route`）；
2. **recipe 观测项**——由 S2① 的 :func:`backend.perception_binding.generate_recipe_obs_items`
   从上面那几个开关派生（**委托，不另写一套**）；
3. **判据/记录器**（`checks` / `recorders`）。

`instantiate_task_plugin()` 把三者一次补齐，并给出 **readiness**：哪些必需传感器在目录里、
各自能力级到哪一档、以及**声明了但今天没人执行**的判据/记录器有哪些。读这份 readiness
就能回答"这个任务现在到底能不能声称可跑"——**不靠猜，也不靠默认值**。

## 诚实边界（与 `contracts/sensor_plugin_contract` 同级纪律）

* 传感器插件当前**全部止步 `registered`**（原生采集器未实现/未探测）⇒ `readiness.ok`
  只表示"声明可实例化"，`verified` 恒 False 并附原因。**不许因为插件里画了就说能跑。**
* `command_source="perception"` 这类取值：`backend/executors.py` 已登记"两个执行器都不支持"
  ⇒ 实例化时**如实计入 blockers**（A2 的同一口径：契约支持却没人能跑 = 谎言）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts import sensor_plugin_contract as sensors
from contracts.task_plugin_contract import (
    CONSUMED_CHECKS,
    CONSUMED_RECORDERS,
    TASK_PLUGIN_SCHEMA,
    TaskPlugin,
    TaskPluginError,
    validate_task_plugin_payload,
)

ROOT = Path(__file__).resolve().parents[1]
#: 内置注册表（随产品走）
REGISTRY_DIR = ROOT / "registry" / "task_plugins"
REGISTRY_FILE = REGISTRY_DIR / "index.json"


def load_task_plugins(path: Path | None = None) -> dict[str, TaskPlugin]:
    """加载注册表 → `{plugin_id: TaskPlugin}`（**逐条校验**，一条坏就整体拒绝）。"""

    source = Path(path) if path is not None else REGISTRY_FILE
    if not source.is_file():
        raise TaskPluginError(f"任务插件注册表不存在：{source}")
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise TaskPluginError(f"注册表必须是 JSON 对象：{source}")
    declared = raw.get("plugins")
    if not isinstance(declared, list) or not declared:
        raise TaskPluginError(f"注册表缺少非空 plugins 数组：{source}")
    out: dict[str, TaskPlugin] = {}
    for item in declared:
        plugin = validate_task_plugin_payload(item)
        if plugin.plugin_id in out:
            raise TaskPluginError(f"任务插件 id 重复：{plugin.plugin_id}")
        out[plugin.plugin_id] = plugin
    return out


def task_plugin(plugin_id: str, *, path: Path | None = None) -> TaskPlugin:
    """按 id 取插件；未知 id **fail-closed** 并列出可用 id。"""

    registry = load_task_plugins(path)
    key = str(plugin_id or "")
    if key not in registry:
        raise TaskPluginError(f"未知任务插件 {key!r}（可用：{', '.join(sorted(registry))}）")
    return registry[key]


def _sensor_report(plugin: TaskPlugin) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for requirement in plugin.sensors:
        definition = sensors.plugin_definition(requirement.plugin_id)
        declared = [str(getattr(o, "name", "")) for o in (getattr(definition, "outputs", None) or [])]
        out.append({
            "plugin_id": requirement.plugin_id,
            "required": requirement.required,
            "outputs_used": list(requirement.outputs) or declared,
            "outputs_declared": declared,
            "capability_level": sensors.capability_level_of(requirement.plugin_id),
        })
    return out


def _executor_support(command_source: str | None) -> dict[str, Any]:
    """命令来源有没有执行器支持（A2 口径：契约支持却没人能跑 = 不许放行）。

    真值取自 `backend/executors.py::UNSUPPORTED_CONTRACT_OPTIONS`（**委托，不抄一份**）：
    那里逐项写着"为什么现在没人跑"，这里只做匹配与转述。
    """

    if not command_source:
        return {"command_source": None, "supported": True, "reason": "未声明（沿用场景默认 policy）"}
    try:
        from backend.executors import UNSUPPORTED_CONTRACT_OPTIONS
    except Exception:  # pragma: no cover - 执行器模块不可用时如实标未知，不假装支持
        return {"command_source": command_source, "supported": False,
                "reason": "执行器能力矩阵不可读（无法判定，按不支持处理）"}
    for item in UNSUPPORTED_CONTRACT_OPTIONS:
        if str(item.get("field")) == "command_source" and str(item.get("value")) == command_source:
            why = str(item.get("why") or "没有执行器支持")
            return {"command_source": command_source, "supported": False,
                    # 先点名 **field=value**（可操作），再附 executors.py 里写明的"为什么没人跑"
                    "reason": f"command_source={command_source!r} 没有执行器支持：{why}"}
    return {"command_source": command_source, "supported": True, "reason": ""}


def instantiate_task_plugin(
    plugin_id: str,
    *,
    scenario: dict[str, Any] | None = None,
    load_path: Path | None = None,
) -> dict[str, Any]:
    """把任务插件**实例化**到一份场景上：补齐 `perception` / `command_source` /
    `checks` / `recorders`，并生成 recipe 观测项。

    合并规则（**可预测、可复核**，不搞"谁赢看运气"）：

    * 插件声明的 `perception` 字段**覆盖**基场景同名字段（它就是"这个任务需要什么"的声明），
      并把被改动的字段列进 `applied` 供人核对；
    * 基场景其余字段一律原样保留（任务插件不是场景的第二个真相）；
    * `scenario=None` 时从空白开始（`map_id` 用场景契约默认 `flat`）。
    """

    plugin = task_plugin(plugin_id, path=load_path)
    base: dict[str, Any] = dict(scenario or {})
    if "scenario_id" not in base:
        base["scenario_id"] = plugin.plugin_id.replace("_", "-")

    perception = dict(base.get("perception") or {})
    applied: dict[str, Any] = {}
    patch = plugin.perception.model_dump(exclude_none=True)
    for key, value in patch.items():
        if perception.get(key) != value:
            applied[f"perception.{key}"] = value
        perception[key] = value
    if perception:
        base["perception"] = perception
    if plugin.command_source:
        if base.get("command_source") != plugin.command_source:
            applied["command_source"] = plugin.command_source
        base["command_source"] = plugin.command_source
    if plugin.checks:
        base["checks"] = list(plugin.checks)
        applied["checks"] = list(plugin.checks)
    if plugin.recorders:
        base["recorders"] = list(plugin.recorders)
        applied["recorders"] = list(plugin.recorders)

    # 观测项**委托** S2① 的生成器（同一份 route 语义，不在这里再判一次 A/B 类）
    from backend.perception_binding import generate_recipe_obs_items

    obs_items = generate_recipe_obs_items(perception or None)

    sensor_report = _sensor_report(plugin)
    executor = _executor_support(plugin.command_source)
    levels = {item["capability_level"] for item in sensor_report}
    verified = levels <= {"available", "verified"}
    unconsumed_checks = [c for c in plugin.checks if c not in CONSUMED_CHECKS]
    unconsumed_recorders = [r for r in plugin.recorders if r not in CONSUMED_RECORDERS]
    blockers: list[str] = []
    if not executor["supported"]:
        blockers.append(executor["reason"])
    for item in sensor_report:
        if item["required"] and item["capability_level"] is None:
            blockers.append(f"必需传感器 {item['plugin_id']} 不在传感器插件目录里")
    readiness = {
        # `ok` 只表示"声明完整、可实例化"；能不能**真跑**看 verified 与 blockers
        "ok": not blockers,
        "verified": bool(verified and not blockers),
        "reason": ("传感器能力级全部 ≥ available 且命令来源有执行器支持" if verified and not blockers
                   else "传感器插件当前止步 registered（原生采集器未实现/未探测）"
                        "⇒ 只能声称「声明可实例化」，不许声称「能跑」"),
        "sensor_capability": {item["plugin_id"]: item["capability_level"] for item in sensor_report},
        "executor": executor,
        "unconsumed_checks": unconsumed_checks,
        "unconsumed_recorders": unconsumed_recorders,
        "blockers": blockers,
    }

    return {
        "success": True,
        "plugin_id": plugin.plugin_id,
        "schema_version": plugin.schema_version,
        "task_type": plugin.task_type,
        "scenario": base,
        "obs_items": obs_items,
        "applied": applied,
        "sensors": sensor_report,
        "readiness": readiness,
    }


def list_task_plugins(*, path: Path | None = None) -> list[dict[str, Any]]:
    """列出注册表里的任务插件（含每条的传感器需求与能力级，供页面直接展示）。"""

    registry = load_task_plugins(path)
    out: list[dict[str, Any]] = []
    for plugin_id in sorted(registry):
        plugin = registry[plugin_id]
        out.append({
            "plugin_id": plugin.plugin_id,
            "label": plugin.label,
            "description": plugin.description,
            "version": plugin.version,
            "task_type": plugin.task_type,
            "evidence": plugin.evidence,
            "sensors": _sensor_report(plugin),
            "perception": plugin.perception.model_dump(exclude_none=True),
            "command_source": plugin.command_source,
            "checks": list(plugin.checks),
            "recorders": list(plugin.recorders),
            "executor": _executor_support(plugin.command_source),
        })
    return out


__all__ = [
    "REGISTRY_FILE",
    "TASK_PLUGIN_SCHEMA",
    "instantiate_task_plugin",
    "list_task_plugins",
    "load_task_plugins",
    "task_plugin",
]
