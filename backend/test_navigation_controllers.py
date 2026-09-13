"""控制器目录端点的测试（H14 定位落地：**声明与实测分开**）。

要点：
* 目录里的角色必须自洽（恰好一个 ``product_default``、一个 ``recommended``、一个 ``negative_control``）；
* 每个条目的 ``implementation`` 文件**必须真实存在**（防止"声明指向不存在的实现"）；
* 每个条目的 ``params_source`` 指向的注册表块**必须真实可读**（防止文档漂移）；
* 实测数据来自 H19 基线；基线缺失/损坏时端点是 ``available=false`` 而不是编数字。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.navigation_api import (
    CONTROLLER_CATALOG,
    REGRESSION_BASELINE_PATH,
    controller_measurements,
    list_controllers,
)

ROOT = Path(__file__).resolve().parents[1]


class CatalogShapeTest(unittest.TestCase):
    def test_roles_are_self_consistent(self) -> None:
        roles = [entry["role"] for entry in CONTROLLER_CATALOG]
        self.assertEqual(roles.count("product_default"), 1, "产品默认执行器必须恰好一个")
        self.assertEqual(roles.count("recommended"), 1, "推荐项必须恰好一个")
        self.assertEqual(roles.count("negative_control"), 1, "负面对照必须恰好一个")

    def test_follow_is_the_product_default(self) -> None:
        """产品实际跑的是 H12 的 follow（不是 DWA）——这是 2026-09-13 的定位结论。"""
        default = next(e for e in CONTROLLER_CATALOG if e["role"] == "product_default")
        self.assertEqual(default["name"], "follow")

    def test_dwa_is_the_negative_control(self) -> None:
        dva = next(e for e in CONTROLLER_CATALOG if e["name"] == "dwa")
        self.assertEqual(dva["role"], "negative_control")

    def test_names_are_unique(self) -> None:
        names = [entry["name"] for entry in CONTROLLER_CATALOG]
        self.assertEqual(len(names), len(set(names)))

    def test_implementations_exist_on_disk(self) -> None:
        for entry in CONTROLLER_CATALOG:
            path = ROOT / entry["implementation"]
            self.assertTrue(path.exists(), f"{entry['name']} 的实现不存在：{entry['implementation']}")

    def test_params_source_blocks_are_readable(self) -> None:
        """``registry/motion_commands.json#<block>`` 的块必须真实存在且非空。"""
        from backend.runtime_registry import load_registry

        registry = load_registry("motion_commands")
        for entry in CONTROLLER_CATALOG:
            source = entry["params_source"]
            if "#" not in source:
                continue
            block = source.split("#", 1)[1].split("（")[0].strip()
            self.assertIn(block, registry, f"{entry['name']} 的参数真值块缺失：{block}")
            self.assertTrue(registry[block], f"{entry['name']} 的参数真值块为空：{block}")

    def test_every_entry_carries_evidence(self) -> None:
        for entry in CONTROLLER_CATALOG:
            self.assertTrue(entry.get("evidence"), f"{entry['name']} 缺 evidence")


class MeasurementsTest(unittest.TestCase):
    def test_reads_baseline_when_present(self) -> None:
        if not REGRESSION_BASELINE_PATH.exists():
            self.skipTest("本仓库尚无 H19 基线")
        measured = controller_measurements()
        self.assertTrue(measured["available"])
        self.assertIn("per_controller", measured)

    def test_missing_baseline_is_reported_not_faked(self) -> None:
        with mock.patch(
            "backend.navigation_api.REGRESSION_BASELINE_PATH", Path(tempfile.gettempdir()) / "nope.json"
        ):
            measured = controller_measurements()
        self.assertFalse(measured["available"], "基线缺失必须如实标 available=false")
        self.assertEqual(measured["per_controller"], {})

    def test_corrupt_baseline_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with mock.patch("backend.navigation_api.REGRESSION_BASELINE_PATH", bad):
                measured = controller_measurements()
        self.assertFalse(measured["available"])
        self.assertIn("error", measured)


class EndpointTest(unittest.TestCase):
    def test_endpoint_returns_catalog_and_measurements(self) -> None:
        import asyncio

        payload = asyncio.run(list_controllers())
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["controllers"]), len(CONTROLLER_CATALOG))
        self.assertEqual(payload["product_default"], "follow")
        self.assertEqual(payload["recommended"], "geometric")
        self.assertIn("measurement_source", payload)
        for item in payload["controllers"]:
            self.assertIn("measured", item)

    def test_endpoint_marks_unmeasured_controller(self) -> None:
        """基线里没有的控制器要给出 ``measured_note``，而不是静默 null。"""
        import asyncio

        fake = {
            "source": "x",
            "available": True,
            "per_controller": {"follow": {"pass_rate": 0.8}},
        }
        with mock.patch("backend.navigation_api.controller_measurements", return_value=fake):
            payload = asyncio.run(list_controllers())
        by_name = {item["name"]: item for item in payload["controllers"]}
        self.assertEqual(by_name["follow"]["measured"]["pass_rate"], 0.8)
        self.assertIsNone(by_name["dwa"]["measured"])
        self.assertIn("measured_note", by_name["dwa"])

    def test_recommended_matches_h19_data_when_available(self) -> None:
        """若基线在，**推荐项必须是实测通过率最高的那个** —— 声明不能与实测相左。"""
        if not REGRESSION_BASELINE_PATH.exists():
            self.skipTest("本仓库尚无 H19 基线")
        payload = json.loads(REGRESSION_BASELINE_PATH.read_text(encoding="utf-8"))
        per_controller = payload.get("per_controller") or {}
        if not per_controller:
            self.skipTest("基线里没有 per_controller")
        best = max(per_controller, key=lambda name: per_controller[name]["pass_rate"])
        measured_pass_rate = per_controller[best]["pass_rate"]
        others = [
            stats["pass_rate"] for name, stats in per_controller.items() if name != best
        ]
        if others and max(others) == measured_pass_rate:
            self.skipTest("并列最优，推荐项不唯一")
        self.assertEqual(
            best,
            "geometric",
            f"H19 实测通过率最高的是 {best}。若它不再是 geometric，"
            "CONTROLLER_CATALOG 里的 recommended 必须同步，否则声明与实测相左",
        )


if __name__ == "__main__":
    unittest.main()
