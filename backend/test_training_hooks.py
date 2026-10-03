"""training_hooks 回归锁（Phase 3）：钩子是训练循环的切点，fail-soft 纪律必须钉死。"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab import training_hooks as th


class LoadHooksTest(unittest.TestCase):
    def test_valid_declaration(self):
        hooks = th.load_hooks({"hooks": {"on_checkpoint": [
            {"call": "tools.trend_probe_hook:run", "config": {"trend_ratio": 0.2}}]}}, "on_checkpoint")
        self.assertEqual(1, len(hooks))
        self.assertEqual("tools.trend_probe_hook:run", hooks[0]["call"])

    def test_missing_hooks_config_is_empty(self):
        self.assertEqual([], th.load_hooks({}, "on_checkpoint"))
        self.assertEqual([], th.load_hooks({"hooks": {}}, "on_checkpoint"))

    def test_wrong_shape_is_ignored_not_fatal(self):
        self.assertEqual([], th.load_hooks({"hooks": {"on_checkpoint": "nope"}}, "on_checkpoint"))
        self.assertEqual([], th.load_hooks({"hooks": {"on_checkpoint": [{"no_call": 1}]}}, "on_checkpoint"))

    def test_unknown_point_is_empty(self):
        self.assertEqual([], th.load_hooks({"hooks": {"on_iteration": []}}, "on_iteration"))


class RunHooksTest(unittest.TestCase):
    def test_consumer_receives_ctx_and_runs(self):
        seen = {}
        mod = types.ModuleType("_hook_test_mod")

        def factory(ctx, **config):
            seen["ctx"] = ctx
            seen["config"] = config

        mod.run = factory
        sys.modules["_hook_test_mod"] = mod
        th.run_hooks("on_checkpoint", [{"call": "_hook_test_mod:run", "config": {"k": 1}}],
                     {"run_dir": "/tmp/x", "iteration": 250})
        self.assertEqual(250, seen["ctx"]["iteration"])
        self.assertEqual({"k": 1}, seen["config"])

    def test_failing_hook_does_not_raise(self):
        mod = types.ModuleType("_hook_test_mod_bad")

        def boom(ctx, **config):
            raise RuntimeError("探针炸了")

        mod.run = boom
        sys.modules["_hook_test_mod_bad"] = mod
        th.run_hooks("on_checkpoint", [{"call": "_hook_test_mod_bad:run"}], {})  # 不抛 = 通过


if __name__ == "__main__":
    unittest.main()
