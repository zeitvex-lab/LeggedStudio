# -*- coding: utf-8 -*-
"""面板 CLI 投影回归：注册表声明 ↔ provider 模块必须一一对得上。

一切皆插件的落点：面板的 CLI 表面完全声明驱动。这里锁三条不变量——
1) 注册表里每条 cli.provider 都能解析到真实函数（声明不许指向虚空）；
2) 声明格式漂移 / 未知函数 → fail-loud（不静默降级）；
3) 每个 provider 调用都返回 JSON 可序列化 dict（panel 命令的打印契约）。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.cli_panels import resolve_provider
from backend.panel_registry import load_panels

_ROOT = Path(__file__).resolve().parents[1]


class ProviderResolutionTest(unittest.TestCase):
    def test_every_declared_provider_resolves(self):
        for panel in load_panels():
            cli = panel.get("cli") or {}
            if not cli.get("provider"):
                continue  # 没有 CLI 投影的面板是合法声明（Web/桌面 only）
            fn = resolve_provider(cli["provider"])  # 不许抛
            self.assertTrue(callable(fn), panel["id"])

    def test_unknown_provider_fails_loud(self):
        with self.assertRaises(ValueError):
            resolve_provider("backend.cli_panels:definitely_missing")

    def test_foreign_prefix_fails_loud(self):
        with self.assertRaises(ValueError):
            resolve_provider("somewhere.else:fn")

    def test_providers_return_json_serializable(self):
        # 纯数据读数，不碰 GPU/训练——全部离线可跑；只验证形状不验证数值。
        for name in ("home_status", "packages_list", "training_list", "config_list",
                     "navmap_list", "artifacts_list"):
            payload = resolve_provider(f"backend.cli_panels:{name}")()
            self.assertIsInstance(payload, dict, name)
            json.dumps(payload, ensure_ascii=False)  # 不可序列化会在这里炸

    def test_deploy_summary_reports_blockers_not_exceptions(self):
        # 部署门禁对每个包都要给出裁决行（blockers 进数据，不许让异常逃出去）
        payload = resolve_provider("backend.cli_panels:deploy_summary")()
        self.assertIn("robots", payload)
        for row in payload["robots"]:
            self.assertIn("ok", row)
            self.assertIn("blockers", row)


if __name__ == "__main__":
    unittest.main()
