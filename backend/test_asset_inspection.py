"""T1.1 DoD：体检五卡引擎测试。

- Go2 五卡可用且整体无 fail（无官方参考源时电机卡仅展示角色分组）
- Lite3 电机卡红标已知漂移（包 24/24/36 vs 官方 40/40/65，docs/DEEPROBOTICS_PORTING）
- M20 电机卡红标（76.4/76.4/76.4 vs 官方 MJCF ctrlrange 200/200/300）
"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.asset_inspection import inspect_package

WORKSPACE = Path(__file__).resolve().parents[1]
ROBOTS = WORKSPACE / "assets" / "robots"


class FiveCardInspectionTest(unittest.TestCase):
    def test_go2_cards_available_without_fail(self) -> None:
        report = inspect_package(ROBOTS / "unitree_go2")
        self.assertEqual(report["robot_id"], "unitree_go2")
        self.assertNotEqual(report["cards"]["mass"]["status"], "fail")
        self.assertNotEqual(report["cards"]["collision"]["status"], "fail")
        self.assertNotEqual(report["cards"]["inertia"]["status"], "fail")
        self.assertNotEqual(report["cards"]["joints"]["status"], "fail")
        self.assertEqual(report["cards"]["motor"]["status"], "pass")
        self.assertIsNone(report["cards"]["motor"]["official_source"])

    def test_go2_mass_cross_sources_agree(self) -> None:
        report = inspect_package(ROBOTS / "unitree_go2")
        mass = report["cards"]["mass"]
        self.assertIn("compiled_mujoco", mass["sources"])
        self.assertEqual(mass["status"], "pass")
        values = list(mass["sources"].values())
        spread = (max(values) - min(values)) / min(values)
        self.assertLessEqual(spread, 0.20)

    def test_lite3_motor_card_flags_official_drift(self) -> None:
        report = inspect_package(ROBOTS / "deeprobotics_lite3")
        motor = report["cards"]["motor"]
        self.assertEqual(motor["status"], "fail")
        flagged = {(item["role"], item["param"]) for item in motor["diffs"]}
        # 包 24/24/36 vs 官方 40/40/65：力矩限三项必须全部红标
        self.assertIn(("hipx", "effort"), flagged)
        self.assertIn(("hipy", "effort"), flagged)
        self.assertIn(("knee", "effort"), flagged)
        # 刚度已与官方一致（30.0 = isaac 资产 ∩ sdk_deploy ∩ ONNX，见
        # 00_know/全部机型_参数来源对照与标准.md §2.1），不得再红标
        self.assertNotIn(("hipx", "stiffness"), flagged)

    def test_m20_motor_card_flags_official_drift(self) -> None:
        report = inspect_package(ROBOTS / "deeprobotics_m20")
        motor = report["cards"]["motor"]
        self.assertEqual(motor["status"], "fail")
        flagged = {(item["role"], item["param"]) for item in motor["diffs"]}
        self.assertIn(("knee", "effort"), flagged)
        # 轮 21.6 vs 20 在 ±10% 内，不得误报
        self.assertNotIn(("wheel", "effort"), flagged)

    def test_overall_reflects_worst_card(self) -> None:
        lite3 = inspect_package(ROBOTS / "deeprobotics_lite3")
        self.assertEqual(lite3["overall"], "fail")


if __name__ == "__main__":
    unittest.main()
