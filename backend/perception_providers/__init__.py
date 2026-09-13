"""感知 provider 协议与注册表（K4 口径：清单即权威）。

**为什么要它**：`scenario_contract` 的 `perception.mount` 只是**声明位**、`perception_observations`
只是**观测项目录**，两者之间**没有运行时模块**——没有"传感器数据 → 结构化输出"的接口、
没有注册表、也没人校验"声明了一个 provider 但实现根本不存在"。于是"接上相机识别 tag / 接上
雷达识别楼梯"这类需求，在架构上无处安放（只能各写各的 while 循环）。

**怎么做的（复用，不造轮子）**：

* 注册范式抄 `00_resources/InstinctMJ/src/instinct_mj/tasks/registry.py`
  —— ``entry_point = "module:Class"`` 字符串注册 + 动态解析；
* 生命周期钩子形状抄 `00_resources/mujoco_ros2_control/.../mujoco_ros2_control_plugins_base.hpp`
  —— ``init / update / on_reset``（只借形状，不引 C++/ROS 运行时；ROS2 运行时本仓笔记已判否）；
* 校验口径抄本仓 K4（`backend/skill_registry.py`）——清单校验 schema、id 唯一、
  **文件/模块必须真实存在**、清单不能谎报；目录下有实现但未登记 = **未注册**
  （由 :func:`unregistered_provider_files` 报出，只作诊断，绝不作为注册来源）；
* 参数（阈值）放在注册表里，代码只做纯函数判定——"数字是数据"。

**fail-closed**：未知 provider_id 直接报错（不回退到某个默认 provider）；清单缺字段 /
entry_point 解析不到 / 实例不满足协议，全部抛 :class:`PerceptionProviderError`。
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

ROOT = Path(__file__).resolve().parents[2]
PROVIDER_DIR = ROOT / "backend" / "perception_providers"
MANIFEST_PATH = ROOT / "registry" / "perception_providers" / "index.json"
MANIFEST_SCHEMA = "perception-provider-index-1.0"
REQUIRED_KEYS = ("provider_id", "entry_point", "sensor", "inputs", "outputs", "params")


class PerceptionProviderError(ValueError):
    """provider 清单不合法 / 未注册 / 实例不满协议。"""


@runtime_checkable
class PerceptionProvider(Protocol):
    """感知 provider 协议（生命周期形状抄 MuJoCo 插件基类）。"""

    provider_id: str

    def init(self, params: dict[str, Any]) -> None:
        """用注册表参数初始化（不清状态）。"""

    def update(self, reading: Any, time_s: float) -> dict[str, Any]:
        """吃一帧传感器数据，吐结构化输出。"""

    def on_reset(self) -> None:
        """环境复位：清掉内部状态（去抖计数、上一帧等）。"""


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    entry_point: str
    sensor: str
    route: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    display_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name or self.provider_id,
            "entry_point": self.entry_point,
            "sensor": self.sensor,
            "route": self.route,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "params": dict(self.params),
        }


def provider_manifest() -> dict[str, Any]:
    """读取并校验清单（K4 口径）。"""
    if not MANIFEST_PATH.is_file():
        raise PerceptionProviderError(
            f"感知 provider 清单缺失：{MANIFEST_PATH}（期望 schema={MANIFEST_SCHEMA}）。"
            "注册以清单为权威，不扫描目录——请从仓库取回该文件。"
        )
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise PerceptionProviderError(f"感知 provider 清单不可解析：{exc}") from exc
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise PerceptionProviderError(
            f"清单 schema 不匹配：{payload.get('schema')!r} != {MANIFEST_SCHEMA!r}"
        )
    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        raise PerceptionProviderError("清单 providers 必须是非空数组")

    seen: set[str] = set()
    for entry in providers:
        if not isinstance(entry, dict):
            raise PerceptionProviderError("providers[] 每项必须是对象")
        missing = [key for key in REQUIRED_KEYS if not entry.get(key)]
        if missing:
            raise PerceptionProviderError(f"{entry.get('provider_id') or '<无名>'}: 缺字段 {missing}")
        provider_id = str(entry["provider_id"])
        if provider_id in seen:
            raise PerceptionProviderError(f"provider_id 重复：{provider_id!r}")
        seen.add(provider_id)
        module_name, _, class_name = str(entry["entry_point"]).partition(":")
        if not module_name or not class_name:
            raise PerceptionProviderError(f"{provider_id}: entry_point 必须是 'module:Class'（得到 {entry['entry_point']!r}）")
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise PerceptionProviderError(f"{provider_id}: 模块不存在 {module_name}（{exc}）") from exc
        if not hasattr(module, class_name):
            raise PerceptionProviderError(f"{provider_id}: 模块 {module_name} 里没有 {class_name}")
    return dict(payload)


def provider_specs() -> list[ProviderSpec]:
    specs = []
    for entry in provider_manifest()["providers"]:
        specs.append(
            ProviderSpec(
                provider_id=str(entry["provider_id"]),
                entry_point=str(entry["entry_point"]),
                sensor=str(entry["sensor"]),
                route=str(entry.get("route") or "external"),
                inputs=dict(entry.get("inputs") or {}),
                outputs=dict(entry.get("outputs") or {}),
                params=dict(entry.get("params") or {}),
                display_name=str(entry.get("display_name") or ""),
            )
        )
    return specs


def provider_spec(provider_id: str) -> ProviderSpec:
    """按 id 取清单条目；未知 id 直接报错（不静默回退到别的 provider）。"""
    for spec in provider_specs():
        if spec.provider_id == provider_id:
            return spec
    available = ", ".join(sorted(spec.provider_id for spec in provider_specs()))
    raise PerceptionProviderError(f"未注册的感知 provider {provider_id!r}；已注册：{available}")


def resolve_provider(provider_id: str, *, reset: bool = True) -> PerceptionProvider:
    """实例化 provider 并把注册表参数灌进去（``init``）。"""
    spec = provider_spec(provider_id)
    module_name, _, class_name = spec.entry_point.partition(":")
    instance = getattr(importlib.import_module(module_name), class_name)()
    if not isinstance(instance, PerceptionProvider):
        raise PerceptionProviderError(
            f"{provider_id}: 实例不满足协议（需要 init / update / on_reset）"
        )
    instance.init(spec.params)
    if reset:
        instance.on_reset()
    return instance


def unregistered_provider_files() -> list[str]:
    """目录下有实现文件但未在清单登记（诊断用，不作注册来源）。"""
    registered = {
        str(spec.entry_point).partition(":")[0].rsplit(".", 1)[-1] + ".py"
        for spec in provider_specs()
    }
    found = []
    for path in sorted(PROVIDER_DIR.glob("*.py")):
        if path.name in ("__init__.py",) or path.name in registered:
            continue
        found.append(path.name)
    return found


def provider_selftest() -> dict[str, Any]:
    """自检：清单可读、每个 provider 可实例化并通过协议检查。"""
    results = []
    for spec in provider_specs():
        try:
            provider = resolve_provider(spec.provider_id)
            ok, error = True, None
        except Exception as exc:  # noqa: BLE001 - 自检要报出任何失败
            ok, error = False, f"{type(exc).__name__}: {exc}"
        results.append({"provider_id": spec.provider_id, "sensor": spec.sensor, "ok": ok, "error": error})
    return {
        "success": True,
        "manifest": str(MANIFEST_PATH.relative_to(ROOT)),
        "count": len(results),
        "providers": results,
        "unregistered_files": unregistered_provider_files(),
        "verdict": "pass" if all(item["ok"] for item in results) and not unregistered_provider_files() else "fail",
    }
