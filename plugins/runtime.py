"""插件内核 v2（协议 v2，``00_know/08`` v3.0 §4.2）——本系统**唯一的非插件件**。

## 三原语（cordis 语义 / Python 单进程实现）

* **服务上下文**：插件向 ctx 声明服务（``ctx.provide(key, value)``），别的插件按 key
  取用（``ctx.get(key)``，缺即 fail-loud 并列出可用项）。**装载顺序由 requires 驱动**
  （:func:`mount` 拓扑排序），不写死 boot 序列——dsh 的 ``inject`` 语义。
* **事件五模式**：``emit``（观察）/ ``waterfall``（中间件链，可短路）/ ``parallel``
  （并发观察；单进程同步内核 = 逐个调用，首个异常即抛）/ ``serial``（顺序执行，收返回值
  列表）/ ``bail``（顺序投票，首个非 None 即中止并胜出）。
* **patch**：entry 树按 id **整行替换**或插入，后写胜（:func:`apply_patch`）——不做
  merge：merge 产生"半覆盖"，正是缩放事故（0.35/0.5）那一类静默漂移的病根。

## 与 v1 的关系

v1 的 Seam 桶（``register(seam, key, v)`` / ``resolve(seam, key)``）就是服务上下文的
``"seam/key"`` 二段写法——**同一存储，不是两套 API**。v1 独立门面 ``plugins/core.py``
已随死件清理退役（2026-10-06：唯一 import 方是它自己的测试）；v1 语义的存量断言
折叠进 ``backend/test_plugin_runtime.py::RegistryCompatTest``。

## 铁律（不变式，``backend/test_plugin_kernel_purity.py`` 机器守卫）

* **内核零业务**：不 import 本仓任何模块（只标准库）；不出现机型/族/功能 id。
* **fail-loud**：未知服务 / 缺依赖 / entry 重复 id / provider 解析失败，全部抛
  :class:`PluginError`——不静默、不猜、不默认。
* **注册皆可逆**：disposer 逆序执行（``ctx.dispose()``）。
* **≤400 行**：能力只在被需要时长出来（dsh 教训）。
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

__all__ = [
    "PluginError", "Entry", "Context", "load_entries", "merge_entries", "apply_patch", "mount",
    "resolve_attr",
]


class PluginError(RuntimeError):
    """插件协议错误（fail-loud 的载体：消息必须说清『缺什么/有什么可选项』）。"""


def resolve_attr(spec: str) -> Callable:
    """``module:attr`` → 可调用（**真 importlib**，装载期解析，失败带原话）。

    这是全仓 provider 声明解析的**唯一实现**（一个真值）——产品面（面板 CLI/HTTP）
    与装配面都委托它，不许各写一份 importlib。
    """
    module_name, sep, attr = spec.partition(":")
    if not sep or not module_name or not attr:
        raise PluginError(f"provider 必须是 `module:attr` 形式，得到 {spec!r}")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise PluginError(f"provider 模块不可导入：{module_name!r}（{exc}）") from exc
    fn = getattr(module, attr, None)
    if not callable(fn):
        available = sorted(
            k for k in dir(module)
            if callable(getattr(module, k, None)) and not k.startswith("_")
        )
        raise PluginError(f"{module_name} 没有 {attr!r}（provider 解析失败；可用：{available}）")
    return fn


def _service_key(seam: str, key: str) -> str:
    return f"{seam}/{key}"


class Entry:
    """一次插件挂载（entry 树的一行）。requires 兼容 ``(seam, key)`` 与 ``"seam/key"``。"""

    __slots__ = ("id", "seam", "key", "provider", "config", "requires")

    def __init__(self, id: str, seam: str, key: str, provider: str | Callable,
                 config: dict | None = None, requires: Sequence | None = None):
        self.id = str(id)
        self.seam = str(seam)
        self.key = str(key)
        self.provider = provider
        self.config = dict(config or {})
        self.requires = [tuple(r) if not isinstance(r, str) else tuple(r.split("/", 1))
                         for r in (requires or [])]

    @classmethod
    def from_mapping(cls, raw: Mapping) -> "Entry":
        try:
            requires = [tuple(r) if not isinstance(r, str) else r for r in (raw.get("requires") or [])]
            return cls(id=str(raw["id"]), seam=str(raw["seam"]), key=str(raw["key"]),
                       provider=raw["provider"], config=raw.get("config"), requires=requires)
        except KeyError as exc:
            raise PluginError(f"entry 缺必填字段 {exc}（raw={dict(list(raw.items())[:4])}…）") from exc

    def to_mapping(self) -> dict:
        return {"id": self.id, "seam": self.seam, "key": self.key,
                "provider": self.provider if isinstance(self.provider, str) else repr(self.provider),
                "config": dict(self.config), "requires": [list(r) for r in self.requires]}


class Context:
    """装配作用域：服务注册表 + 事件总线 + 可逆 effect 栈。

    服务键统一为 ``"seam/key"``（v1 二段写法与 v2 平面写法同一存储）。
    """

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, Any]] = {}
        self._disposers: list[Callable[[], None]] = []
        self._entries: dict[str, Entry] = {}
        self._listeners: dict[str, list[Callable]] = {}

    # -- 服务上下文（v2 平面 API；与 v1 二段 API 同一存储） ------------------
    def provide(self, key: str, value: Any) -> Callable[[], None]:
        """声明一个服务（键 ``"seam/key"``）。返回 disposer（注册即 effect）。"""
        seam, _, sub = str(key).partition("/")
        return self.register(seam, sub, value)

    def get(self, key: str) -> Any:
        seam, _, sub = str(key).partition("/")
        return self.resolve(seam, sub)

    def try_get(self, key: str) -> Any:
        seam, _, sub = str(key).partition("/")
        bucket = self._buckets.get(seam)
        return None if bucket is None else bucket.get(sub)

    # -- v1 二段 API（兼容门面语义） -----------------------------------------
    def register(self, seam: str, key: str, value: Any) -> Callable[[], None]:
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

    # -- 事件五模式 ----------------------------------------------------------
    def on(self, event: str, listener: Callable) -> Callable[[], None]:
        """订阅事件（注册即 effect：返回 disposer，dispose 时随作用域撤销）。"""
        self._listeners.setdefault(str(event), []).append(listener)
        def _disposer() -> None:
            try:
                self._listeners.get(str(event), []).remove(listener)
            except ValueError:
                pass
        self._disposers.append(_disposer)
        return _disposer

    def emit(self, event: str, *args: Any) -> None:
        """观察：按订阅序调用，无返回值。"""
        for listener in list(self._listeners.get(str(event), [])):
            listener(*args)

    def parallel(self, event: str, *args: Any) -> None:
        """并发观察：单进程同步内核 = 逐个调用（语义与顺序无关），异常即抛。"""
        self.emit(event, *args)

    def serial(self, event: str, *args: Any) -> list[Any]:
        """顺序执行：收每个监听者的返回值（按订阅序）。"""
        return [listener(*args) for listener in list(self._listeners.get(str(event), []))]

    def bail(self, event: str, *args: Any) -> Any:
        """投票：按订阅序调用，首个非 None 返回值即中止并胜出；全 None 则 None。"""
        for listener in list(self._listeners.get(str(event), [])):
            verdict = listener(*args)
            if verdict is not None:
                return verdict
        return None

    def waterfall(self, event: str, payload: Any) -> Any:
        """中间件链：监听者签名 ``(payload, next)``——调 ``next(v)`` 继续传递，不调即短路。"""
        listeners = list(self._listeners.get(str(event), []))
        def _chain(index: int, value: Any) -> Any:
            if index >= len(listeners):
                return value
            delegated: dict[str, Any] = {}
            def _next(v: Any) -> Any:
                delegated["result"] = _chain(index + 1, v)
                return delegated["result"]
            out = listeners[index](value, _next)
            return delegated.get("result", out)
        return _chain(0, payload)

    # -- 挂载 ----------------------------------------------------------
    def activate(self, entry: Entry) -> Any:
        """装载一个 entry：验依赖 → 解析 provider → 调用（provider 自行 register）。"""
        if entry.id in self._entries:
            raise PluginError(f"entry id 重复：{entry.id}")
        for r_seam, r_key in entry.requires:
            if not self.has(r_seam, r_key):
                raise PluginError(
                    f"entry {entry.id} 缺依赖 {r_seam}/{r_key}"
                    f"（可用：{', '.join(sorted(self._buckets.get(r_seam, {})) or ['（空）'])}）"
                    "——请把它排在前面，或检查 registry"
                )
        provider = entry.provider
        if isinstance(provider, str):
            provider = resolve_attr(provider)
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
        self._listeners.clear()

    def entries(self) -> dict[str, Entry]:
        return dict(self._entries)


# ---------------------------------------------------------------------------
# entry 树：合并 + patch（id 定位整行替换 / 插入，后写胜） + 拓扑装载
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
    """patch：id 命中 = 整行替换（保位），未命中 = 追加（后写胜，不 merge）。"""
    return merge_entries(base, patch)


def load_entries(raw: list[Mapping]) -> list[Entry]:
    return [Entry.from_mapping(r) for r in raw]


def _require_keys(entry: Entry) -> list[tuple[str, str]]:
    return [(str(s), str(k)) for s, k in entry.requires]


def mount(entries: list[Entry]) -> Context:
    """**拓扑装载**：按 requires（服务可用性）排序后逐个 activate。

    排序稳定（同层保持声明序）；requires 指向**其它 entry 的 provides**（即
    ``"seam/key"``）或已存在服务。环 = fail-loud（列出成环成员）。
    """
    by_id = {e.id: e for e in entries}
    if len(by_id) != len(entries):
        dupes = sorted({e.id for e in entries if [x.id for x in entries].count(e.id) > 1})
        raise PluginError(f"entry id 重复：{', '.join(dupes)}")

    def _provides(e: Entry) -> str:
        return _service_key(e.seam, e.key)

    provides_map = {_provides(e): e.id for e in entries}
    deps: dict[str, set[str]] = {}
    for e in entries:
        wanted = set()
        for seam, key in _require_keys(e):
            service = _service_key(seam, key)
            if service in provides_map:
                wanted.add(provides_map[service])
            # 不在 entry 集合里的依赖 = 预置服务，拓扑层置 0（activate 时仍会 fail-loud 校验）
        deps[e.id] = wanted

    ordered: list[str] = []
    done: set[str] = set()
    pending = {e.id for e in entries}
    while pending:
        ready = sorted(i for i in pending if deps[i] <= done)
        if not ready:
            cycle = sorted(pending)
            raise PluginError(f"entry 依赖成环（requires 互相等待）：{', '.join(cycle)}")
        for i in ready:
            ordered.append(i)
            done.add(i)
            pending.discard(i)

    ctx = Context()
    for entry_id in ordered:
        ctx.activate(by_id[entry_id])
    return ctx
