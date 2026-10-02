"""插件内核（协议 v1）——本系统**唯一的非插件件**（00_know/08 §1，≤300 行硬上限）。

## 四个原语（不做多余的事——dsh 教训只在需要处长出来）

* **Seam**：扩展点桶名（robot/terrain/reward/algorithm/task/evaluator/…，冻结清单见
  `00_know/08` §1）。`ctx.register(seam, key, provider)` 注册，`ctx.resolve(seam, key)`
  解析——解析不到 fail-loud 并列出可用项（不静默、不猜）。
* **provider**：`(ctx, config) -> Any` 的可调用（或 `module:attr` 字符串，装载时解析）。
  它在调用中向 ctx 注册自己的产出（env cfg 装配器/评测器/导出器…），**注册即 effect**：
  返回 disposer 的登记进作用域，`ctx.dispose()` 逆序执行。
* **requires**：provider 声明依赖的 (seam, key) 列表；activate 前验证，缺 = fail-loud
  （不排队不等待——训练装配是同步一次性的，等待语义无意义）。
* **entry 树 + patch**：一次装配 = entry 列表
  ``{id, seam, key, provider, config?, requires?}``；patch 按 id 定位**整行替换**或
  插入，后写胜。层叠来源（族基线→机型包→档案→CLI）由调用方按序传列表实现。

## 铁律（与 dsh 同款纪律）

* **fail-loud**：未知 seam/key/缺依赖/entry 重复 id，全部抛错——不静默、不猜、不默认。
* **注册皆可逆**：没有 disposer 的注册不允许存在（内核不强制返回值，但 dispose 顺序保证）。
* **内核零业务**：不 import 本仓任何模块；机型/配方/评测器全是插件，不是内核知识。
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import Any

__all__ = ["PluginError", "Entry", "Context", "load_entries", "merge_entries", "apply_patch"]


class PluginError(RuntimeError):
    """插件协议错误（fail-loud 的载体：消息必须说清『缺什么/有什么可选项』）。"""


def _resolve_attr(spec: str) -> Callable:
    """`module:attr` → 可调用（装载期解析，失败带原话）。"""
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise PluginError(f"provider 必须是 `module:attr` 形式，得到 {spec!r}")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise PluginError(f"{module_name} 没有 {attr!r}（provider 解析失败）") from exc


class Entry:
    """一次插件挂载（entry 树的一行）。"""

    __slots__ = ("id", "seam", "key", "provider", "config", "requires")

    def __init__(self, id: str, seam: str, key: str, provider: str | Callable,
                 config: dict | None = None, requires: list[tuple[str, str]] | None = None):
        self.id = str(id)
        self.seam = str(seam)
        self.key = str(key)
        self.provider = provider
        self.config = dict(config or {})
        self.requires = [tuple(r) for r in (requires or [])]

    @classmethod
    def from_mapping(cls, raw: Mapping) -> "Entry":
        try:
            requires = [tuple(r) for r in (raw.get("requires") or [])]
            return cls(id=str(raw["id"]), seam=str(raw["seam"]), key=str(raw["key"]),
                       provider=raw["provider"], config=raw.get("config"), requires=requires)
        except KeyError as exc:
            raise PluginError(f"entry 缺必填字段 {exc}（raw={dict(list(raw.items())[:4])}…）") from exc

    def to_mapping(self) -> dict:
        return {"id": self.id, "seam": self.seam, "key": self.key,
                "provider": self.provider if isinstance(self.provider, str) else repr(self.provider),
                "config": dict(self.config), "requires": [list(r) for r in self.requires]}


class Context:
    """装配作用域：seam 注册表 + 已激活插件集合 + 可逆 effect 栈。"""

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, Any]] = {}
        self._providers: dict[str, Any] = {}          # f"{seam}:{key}" -> provider 产出
        self._disposers: list[Callable[[], None]] = []
        self._entries: dict[str, Entry] = {}

    # -- 注册与解析 --------------------------------------------------------
    def register(self, seam: str, key: str, value: Any) -> Callable[[], None]:
        """向 seam 桶注册一个产出（**注册即 effect**：返回 disposer）。"""
        bucket = self._buckets.setdefault(str(seam), {})
        if str(key) in bucket:
            raise PluginError(f"{seam}/{key} 已注册（重复挂载；换 key 或先 dispose）")
        bucket[str(key)] = value
        def _disposer() -> None:
            self._buckets.get(str(seam), {}).pop(str(key), None)
        self._disposers.append(_disposer)
        return _disposer

    def resolve(self, seam: str, key: str) -> Any:
        bucket = self._buckets.get(str(seam))
        if bucket is None or str(key) not in bucket:
            available = ", ".join(sorted(bucket or {})) or "（空）"
            raise PluginError(f"{seam}/{key} 未注册（可用：{available}）")
        return bucket[str(key)]

    def has(self, seam: str, key: str) -> bool:
        return str(key) in self._buckets.get(str(seam), {})

    def bucket(self, seam: str) -> dict[str, Any]:
        return dict(self._buckets.get(str(seam), {}))

    # -- 插件挂载 ----------------------------------------------------------
    def activate(self, entry: Entry) -> Any:
        """装载一个 entry：验依赖 → 解析 provider → 调用（provider 自行 register）。"""
        if entry.id in self._entries:
            raise PluginError(f"entry id 重复：{entry.id}")
        for r_seam, r_key in entry.requires:
            if not self.has(r_seam, r_key):
                raise PluginError(
                    f"entry {entry.id} 缺依赖 {r_seam}/{r_key}"
                    f"（可用：{', '.join(sorted(self._buckets.get(r_seam, {})) or '（空）')}）"
                    "——请把它排在前面，或检查 registry")
        provider = entry.provider
        if isinstance(provider, str):
            provider = _resolve_attr(provider)
        result = provider(self, entry.config)
        self._entries[entry.id] = entry
        return result

    def activate_entries(self, entries: list[Entry]) -> list[Any]:
        return [self.activate(e) for e in entries]

    def dispose(self) -> None:
        """逆序执行全部 disposer（作用域销毁；装配一次性，训练完即弃）。"""
        for disposer in reversed(self._disposers):
            disposer()
        self._disposers.clear()
        self._buckets.clear()
        self._entries.clear()

    def entries(self) -> dict[str, Entry]:
        return dict(self._entries)


# ---------------------------------------------------------------------------
# entry 树装载：合并 + patch（id 定位整行替换 / 插入，后写胜）
# ---------------------------------------------------------------------------

def merge_entries(*layers: list[Entry]) -> list[Entry]:
    """多层 entry 列表合并（同 id = 后层整行覆盖前层，保持首见位置）。"""
    by_id: dict[str, Entry] = {}
    order: list[str] = []
    for layer in layers:
        for entry in layer:
            if entry.id not in by_id:
                order.append(entry.id)
            by_id[entry.id] = entry
    return [by_id[i] for i in order]


def apply_patch(base: list[Entry], patch: list[Entry]) -> list[Entry]:
    """patch：id 命中 = 整行替换（保位），未命中 = 追加（dsh patch 语义的行级子集）。"""
    patched = merge_entries(base, patch)
    return patched


def load_entries(raw: list[Mapping]) -> list[Entry]:
    return [Entry.from_mapping(r) for r in raw]
