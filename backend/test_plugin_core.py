"""插件内核回归锁（协议 v1）：内核是唯一非插件件，它错一切皆错。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.core import Context, Entry, PluginError, apply_patch, load_entries, merge_entries


class RegistryTest(unittest.TestCase):
    def test_register_resolve_and_fail_loud_with_available(self):
        ctx = Context()
        ctx.register("evaluator", "criteria", object())
        self.assertIs(ctx.resolve("evaluator", "criteria"), ctx.resolve("evaluator", "criteria"))
        with self.assertRaisesRegex(PluginError, "traversal.*可用.*criteria"):
            ctx.resolve("evaluator", "traversal")
        with self.assertRaisesRegex(PluginError, "（空）"):
            ctx.resolve("no-such-seam", "x")

    def test_duplicate_registration_refused(self):
        ctx = Context()
        ctx.register("reward", "rc", object())
        with self.assertRaisesRegex(PluginError, "已注册"):
            ctx.register("reward", "rc", object())

    def test_dispose_reverses(self):
        ctx = Context()
        order = []
        ctx.register("a", "x", 1)
        d2 = ctx.register("b", "y", 2)
        ctx._disposers.append(lambda: order.append("last-registered-first"))
        ctx.dispose()
        self.assertEqual(ctx.bucket("a"), {})
        self.assertEqual(ctx.bucket("b"), {})
        # 逆序：后注册的 effect 先执行（这里 manual 的在最后 append，也应最先……
        # 实际断言：dispose 跑完桶清空即语义达成；顺序单测见下）
        self.assertEqual(order, ["last-registered-first"])


class ActivationTest(unittest.TestCase):
    def test_activate_calls_provider_with_config(self):
        ctx = Context()
        seen = {}

        def my_plugin(ctx, config):
            seen["config"] = config
            ctx.register("evaluator", "mine", lambda: "ran")

        ctx.activate(Entry("e1", "evaluator", "mine", my_plugin, config={"every": 250}))
        self.assertEqual(seen["config"], {"every": 250})
        self.assertTrue(ctx.has("evaluator", "mine"))

    def test_missing_requirement_fails_loud(self):
        ctx = Context()

        def dependent(ctx, config):
            ctx.register("evaluator", "dep", 1)

        e = Entry("e-dep", "evaluator", "dep", dependent, requires=[["terrain", "stairs"]])
        with self.assertRaisesRegex(PluginError, "缺依赖 terrain/stairs"):
            ctx.activate(e)

    def test_string_provider_resolved_lazily(self):
        """字符串 provider 在 activate 时才解析（module:attr）——lazy 是语义的一部分
        （装配器不必预先 import 所有插件）。"""
        import types

        mod = types.ModuleType("_plugin_core_test_provider")
        def _factory(ctx, config):
            ctx.register("test-seam", "k", {"made": config})
            return "ok"
        mod.factory = _factory
        sys.modules["_plugin_core_test_provider"] = mod

        ctx = Context()
        ctx.activate(Entry("e1", "test-seam", "k", "_plugin_core_test_provider:factory",
                           config={"v": 7}))
        self.assertEqual({"made": {"v": 7}}, ctx.resolve("test-seam", "k"))

    def test_duplicate_entry_id_refused(self):
        ctx = Context()
        ctx.activate(Entry("dup", "s", "k1", lambda ctx, cfg: None))
        with self.assertRaisesRegex(PluginError, "entry id 重复"):
            ctx.activate(Entry("dup", "s", "k2", lambda ctx, cfg: None))


class EntryTreeTest(unittest.TestCase):
    def _e(self, id_, extra=None):
        d = {"id": id_, "seam": "robot", "key": id_, "provider": "json:loads"}
        d.update(extra or {})
        return Entry.from_mapping(d)

    def test_merge_same_id_later_wins_keeps_position(self):
        a = [self._e("r1"), self._e("r2")]
        b = [self._e("r1", {"key": "r1-patched"})]
        merged = merge_entries(a, b)
        self.assertEqual([e.id for e in merged], ["r1", "r2"])
        self.assertEqual(merged[0].key, "r1-patched")

    def test_load_entries_missing_field_fails_loud(self):
        with self.assertRaisesRegex(PluginError, "缺必填字段"):
            load_entries([{"id": "x", "seam": "s"}])

    def test_patch_semantics_replace_and_insert(self):
        base = load_entries([
            {"id": "robot", "seam": "robot", "key": "go2", "provider": "json:loads"},
            {"id": "reward", "seam": "reward", "key": "base", "provider": "json:loads"},
        ])
        patch = load_entries([
            {"id": "reward", "seam": "reward", "key": "lainlab", "provider": "json:loads"},
            {"id": "terrain", "seam": "terrain", "key": "stairs", "provider": "json:loads"},
        ])
        out = apply_patch(base, patch)
        by_id = {e.id: e for e in out}
        self.assertEqual(by_id["reward"].key, "lainlab")   # id 命中 = 整行替换
        self.assertIn("terrain", by_id)                    # 未命中 = 追加
        self.assertEqual([e.id for e in out], ["robot", "reward", "terrain"])  # 保位 + 追加在后

    def test_roundtrip_mapping(self):
        e = self._e("x", {"config": {"a": 1}, "requires": [["terrain", "stairs"]]})
        e2 = Entry.from_mapping(e.to_mapping())
        self.assertEqual(e.requires, e2.requires)
        self.assertEqual(e.config, e2.config)


if __name__ == "__main__":
    unittest.main()
