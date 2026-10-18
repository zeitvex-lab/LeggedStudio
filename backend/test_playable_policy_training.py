# -*- coding: utf-8 -*-
"""可试玩策略必须能回溯到训练代码（2026-10-17 用户口径）。

规则：`simulation/config.json` 的每条策略都必须有 `training_ref.profile`，
profile 必须存在且带 `entrypoints.env`；`pretrained_models/index.json` 必须与
包声明同步。没有训练源的“产物-only”策略不允许出现在可试玩清单里。
"""
from __future__ import annotations

import unittest

from tools.audit_playable_policy_training import audit


class PlayablePolicyTrainingTest(unittest.TestCase):
    def test_all_playable_policies_have_training_source(self):
        report = audit()
        self.assertGreater(report["checked"], 0, "没有扫到任何可试玩策略")
        self.assertTrue(report["ok"], "\n".join(
            f"{p.get('robot')}/{p.get('policy')}: {p.get('reason')}"
            for p in report["problems"][:20]
        ))

    def test_no_product_only_training_ref(self):
        report = audit()
        offenders = [
            f"{p['robot']}/{p['policy']}"
            for p in report["policies"]
            if not p.get("profile")
        ]
        self.assertEqual([], offenders, "存在没有 training_ref.profile 的可试玩策略")

    def test_pretrained_index_matches_declared_policies(self):
        report = audit()
        index_problems = [
            p for p in report["problems"]
            if p.get("list") == "pretrained_models/index.json"
        ]
        self.assertEqual([], index_problems)


if __name__ == "__main__":
    unittest.main()
