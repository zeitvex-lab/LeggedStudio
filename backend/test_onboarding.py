# -*- coding: utf-8 -*-
"""接入向导（N4 厂商适配包入口）回归锁。

锁五条不变量：
1. 四步读数形状固定（structure/contract/inspection/smoke）且每步带 status+summary；
2. 判据**单一来源**——体检步与 `asset_inspection.inspect_package` 逐值一致
   （不发明第二套判据；契约步与 `deploy_gate_report` 同义）；
3. 未知包 fail-loud（KeyError，不静默返回空——"接入失败却显示全绿"比报错更糟）；
4. 全包一览 fail-soft：单包读数失败只降级该行，counts 自洽；
5. 面板声明驱动：manifest 的 cli.provider 可解析且零参可调用（四投影纪律）。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.onboarding import onboarding_overview, package_onboarding

PROBE_ROBOT = "unitree_go2"


class PackageOnboardingTest(unittest.TestCase):
    def test_known_package_four_steps(self):
        detail = package_onboarding(PROBE_ROBOT)
        self.assertEqual(
            sorted(detail["steps"].keys()),
            ["contract", "inspection", "smoke", "structure"],
        )
        for name, step in detail["steps"].items():
            self.assertIn("status", step, f"{name} 步缺 status")
            self.assertIn("summary", step, f"{name} 步缺 summary")
        # 本容器无训练栈 ⇒ 冒烟如实「没测过」（没测过 ≠ 测失败）
        self.assertEqual(detail["steps"]["smoke"]["status"], "untested")
        self.assertFalse(detail["ready"])
        self.assertEqual(detail["overall"], "untested")

    def test_unknown_package_raises(self):
        with self.assertRaises(KeyError):
            package_onboarding("no_such_robot_zzz")

    def test_inspection_step_matches_single_source(self):
        """体检步 = inspect_package 同一实现（防第二套判据）。"""
        from backend.asset_inspection import inspect_package

        detail = package_onboarding(PROBE_ROBOT)
        root = Path(detail["package_root"])
        report = inspect_package(root)
        step = detail["steps"]["inspection"]
        self.assertEqual(step["overall"], report["overall"])
        self.assertEqual(
            step["family_readiness"]["verdict"],
            (report.get("family_readiness") or {}).get("verdict"),
        )
        self.assertEqual(
            {k: v["status"] for k, v in step["cards"].items()},
            {k: v["status"] for k, v in report["cards"].items()},
        )

    def test_contract_step_matches_deploy_gate(self):
        """契约步 = deploy gate 同一实现（包内 v3/v2 层间一致）。"""
        from backend.deploy_pack import deploy_gate_report

        detail = package_onboarding(PROBE_ROBOT)
        gate = deploy_gate_report(PROBE_ROBOT)
        self.assertEqual(detail["steps"]["contract"]["status"], "pass" if gate["ok"] else "fail")


class OverviewTest(unittest.TestCase):
    def test_overview_covers_all_packages_fail_soft(self):
        from backend.robot_packages import list_robot_packages

        overview = onboarding_overview()
        expected = {str(p.get("robot_id")) for p in list_robot_packages()}
        self.assertEqual({row["robot_id"] for row in overview["packages"]}, expected)
        self.assertEqual(overview["total"], len(expected))
        # counts 自洽：各状态计数之和 = 总数（单包失败也归入 error 行，不丢包）
        self.assertEqual(sum(overview["counts"].values()), overview["total"])
        for row in overview["packages"]:
            self.assertIn("overall", row)
            if row["overall"] != "error":
                self.assertEqual(sorted(row["steps"].keys()), ["contract", "inspection", "smoke", "structure"])

    def test_overview_ttl_cache_serves_fast_and_marks_age(self):
        """TTL 缓存：二次读取走缓存（全量 DoD ≈4.3s，首页等不起），且载荷恒带
        generated_at/age_s——陈旧以秒计可见，不把旧读数伪装成新读数。"""
        import time as _time

        first = onboarding_overview(refresh=True)
        self.assertIn("generated_at", first)
        self.assertAlmostEqual(first["age_s"], 0.0, delta=1.0)
        _time.sleep(0.05)
        second = onboarding_overview()
        self.assertGreater(second["age_s"], 0.0)
        self.assertEqual(second["packages"], first["packages"])
        self.assertEqual(second["generated_at"], first["generated_at"])  # 同一份缓存
        # refresh=True 强制重读：时间戳必须前进
        third = onboarding_overview(refresh=True)
        self.assertGreaterEqual(third["generated_at"], first["generated_at"])


class PanelProjectionTest(unittest.TestCase):
    def test_manifest_provider_resolves_and_callable(self):
        """面板清单的 cli.provider 走真 module:attr 解析且零参可调用（四投影纪律）。"""
        from backend.cli_panels import resolve_provider
        from backend.panel_registry import load_panels

        entry = next((p for p in load_panels() if p.get("id") == "onboarding"), None)
        self.assertIsNotNone(entry, "onboarding 面板未注册（registry/plugins/panel/）")
        provider = resolve_provider(entry["cli"]["provider"])
        payload = provider()
        self.assertIn("packages", payload)
        self.assertEqual(payload["total"], len(payload["packages"]))


class HttpEndpointTest(unittest.TestCase):
    def test_endpoint_ok_and_404(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.robots_api import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        ok = client.get(f"/api/robots/packages/{PROBE_ROBOT}/onboarding")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(sorted(ok.json()["steps"].keys()), ["contract", "inspection", "smoke", "structure"])
        missing = client.get("/api/robots/packages/no_such_robot_zzz/onboarding")
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
