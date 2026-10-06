# -*- coding: utf-8 -*-
"""插件内核 v2 回归锁（协议 v2，00_know/08 v3.0 §4.2）——内核是唯一非插件件，它错一切皆错。

覆盖 v1 没有的四块：服务上下文平面 API、事件五模式、mount 拓扑装载、fail-loud 环检测。
v1 兼容面由 ``backend/test_plugin_core.py`` 守（门面 ``plugins/core.py``）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.runtime import Context, Entry, PluginError, load_entries, mount


class ServiceContextTest(unittest.TestCase):
    def test_flat_and_two_part_api_share_storage(self):
        """provide/get（v2 平面）与 register/resolve（v1 二段）是同一存储——不是两套。"""
        ctx = Context()
        ctx.provide("panel/home", {"title": "首页"})
        self.assertEqual({"title": "首页"}, ctx.resolve("panel", "home"))
        ctx.register("panel", "robot", 1)
        self.assertEqual(1, ctx.get("panel/robot"))
        self.assertIsNone(ctx.try_get("panel/missing"))

    def test_get_missing_lists_available_fail_loud(self):
        ctx = Context()
        ctx.provide("skill/velocity", object())
        with self.assertRaisesRegex(PluginError, "skill/jump.*可用.*velocity"):
            ctx.get("skill/jump")


class EventBusTest(unittest.TestCase):
    def test_emit_notifies_in_order(self):
        ctx = Context()
        seen: list[str] = []
        ctx.on("train.start", lambda rid: seen.append(f"a:{rid}"))
        ctx.on("train.start", lambda rid: seen.append(f"b:{rid}"))
        ctx.emit("train.start", "run-1")
        self.assertEqual(["a:run-1", "b:run-1"], seen)

    def test_waterfall_wraps_and_can_short_circuit(self):
        ctx = Context()
        ctx.on("gate.check", lambda v, next: next(v + 1))          # 包装：透传 +1
        ctx.on("gate.check", lambda v, next: v * 2 if v < 5 else v)  # 短路：小值翻倍；大值原样通过
        self.assertEqual(8, ctx.waterfall("gate.check", 3))        # 3 → next(4) → 短路 8
        self.assertEqual(6, ctx.waterfall("gate.check", 5))        # 5 → next(6) → 通过 6

    def test_serial_collects_returns_in_order(self):
        ctx = Context()
        ctx.on("audit.run", lambda: "a")
        ctx.on("audit.run", lambda: "b")
        self.assertEqual(["a", "b"], ctx.serial("audit.run"))

    def test_bail_first_non_none_wins(self):
        ctx = Context()
        ctx.on("deploy.gate", lambda pkg: None)                     # 弃权
        ctx.on("deploy.gate", lambda pkg: f"deny:{pkg}" if pkg == "bad" else None)
        self.assertEqual("deny:bad", ctx.bail("deploy.gate", "bad"))
        self.assertIsNone(ctx.bail("deploy.gate", "good"))

    def test_listener_disposal_unsubscribes(self):
        ctx = Context()
        calls: list[str] = []
        off = ctx.on("ev", lambda: calls.append("x"))
        off()
        ctx.emit("ev")
        self.assertEqual([], calls)


class MountTest(unittest.TestCase):
    def _entries(self):
        # 声明序故意反着写：依赖者在前——mount 必须按 requires 拓扑重排
        return [
            Entry("app", "app", "main", lambda ctx, cfg: ctx.register("app", "main", "up"),
                  requires=[("panel", "home")]),
            Entry("panel-home", "panel", "home", lambda ctx, cfg: ctx.register("panel", "home", "up")),
        ]

    def test_mount_orders_by_requires_not_declaration(self):
        ctx = mount(self._entries())
        self.assertEqual("up", ctx.get("panel/home"))
        self.assertEqual("up", ctx.get("app/main"))

    def test_mount_cycle_fails_loud(self):
        a = Entry("a", "s", "k1", lambda ctx, cfg: None, requires=[("s", "k2")])
        b = Entry("b", "s", "k2", lambda ctx, cfg: None, requires=[("s", "k1")])
        with self.assertRaisesRegex(PluginError, "成环"):
            mount([a, b])

    def test_mount_missing_preset_service_fails_loud(self):
        e = Entry("x", "s", "k", lambda ctx, cfg: None, requires=[("terrain", "stairs")])
        with self.assertRaisesRegex(PluginError, "缺依赖 terrain/stairs"):
            mount([e])

    def test_string_provider_resolved_via_importlib(self):
        import types

        mod = types.ModuleType("_runtime_kernel_test_provider")
        mod.factory = lambda ctx, cfg: ctx.register("t", "k", cfg)
        sys.modules["_runtime_kernel_test_provider"] = mod
        try:
            ctx = mount([Entry("e", "t", "k", "_runtime_kernel_test_provider:factory",
                               config={"v": 9})])
            self.assertEqual({"v": 9}, ctx.get("t/k"))
        finally:
            del sys.modules["_runtime_kernel_test_provider"]

    def test_provider_module_not_importable_fails_loud(self):
        e = Entry("e", "t", "k", "no.such.module.zzz:fn")
        with self.assertRaisesRegex(PluginError, "不可导入"):
            mount([e])

    def test_load_entries_accepts_flat_string_requires(self):
        entries = load_entries([
            {"id": "x", "seam": "s", "key": "k", "provider": "json:loads",
             "requires": ["terrain/stairs"]},
        ])
        self.assertEqual([("terrain", "stairs")], entries[0].requires)


class DisposeTest(unittest.TestCase):
    def test_dispose_unwinds_services_and_listeners(self):
        ctx = Context()
        order: list[str] = []
        d = ctx.provide("a/x", 1)
        ctx._disposers.append(lambda: order.append("last"))
        d()  # 显式撤销首个注册
        self.assertIsNone(ctx.try_get("a/x"))
        ctx.dispose()
        self.assertEqual(["last"], order)


if __name__ == "__main__":
    unittest.main()
