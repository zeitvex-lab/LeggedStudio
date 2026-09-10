"""B2 契约单轨：``locomotion_type`` 必须等于由 v3 morphology 派生的值（漂移 CI）。

这个测试是**漂移守护**：v2 的四值枚举与 v3 的 morphology 曾长期并存并互相漂移
（``microduck`` 是 ``legs=2`` 的双足却写着 ``P``=四足点足）。收敛后
``locomotion_type`` 只是派生视图，因此"存量值 ≠ 派生值"必须直接失败，而不是靠人工发现。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.contract_loader import load_training_contract, merge_v3_over_v2
from contracts.locomotion_view import LOCOMOTION_ENUM, locomotion_type_from_contract

WORKSPACE = Path(__file__).resolve().parents[2]
ROBOTS = WORKSPACE / "assets" / "robots"

# 全量期望表（由 morphology 推出）。改动任何机型的运动形态都会在这里显形。
EXPECTED = {
    "deeprobotics_lite3": "P",
    "deeprobotics_m20": "W",
    "limx_tron1_pf": "B",
    "limx_tron1_sf": "B",
    "limx_tron1_wf": "W",
    "microduck": "B",
    "unitree_b2": "P",
    "unitree_b2w": "W",
    "unitree_g1": "B",
    "unitree_go1": "P",
    "unitree_go2": "P",
    "unitree_go2w": "W",
    "wuji_hand": "H",
    "zex-w": "W",
}


class LocomotionViewTest(unittest.TestCase):
    def _packages(self) -> list[str]:
        return sorted(
            p.name for p in ROBOTS.iterdir() if (p / "contract_v3.json").exists()
        )

    def _v3(self, package: str) -> dict:
        return json.loads(
            (ROBOTS / package / "contract_v3.json").read_text(encoding="utf-8-sig")
        )

    def test_derivation_matches_expected_table(self) -> None:
        for package, expected in EXPECTED.items():
            with self.subTest(package=package):
                self.assertEqual(locomotion_type_from_contract(self._v3(package)), expected)

    def test_derived_value_is_a_valid_enum(self) -> None:
        for package in self._packages():
            with self.subTest(package=package):
                self.assertIn(locomotion_type_from_contract(self._v3(package)), LOCOMOTION_ENUM)

    def test_no_drift_between_stored_and_derived(self) -> None:
        """存量值（v3 与 v2 两侧）都必须等于派生值。"""

        for package in self._packages():
            derived = locomotion_type_from_contract(self._v3(package))
            with self.subTest(package=package, side="v3"):
                self.assertEqual(
                    self._v3(package).get("locomotion_type"),
                    derived,
                    f"{package}/contract_v3.json 的 locomotion_type 与 morphology 漂移",
                )
            v2_path = ROBOTS / package / "contract.json"
            if not v2_path.exists():
                continue
            v2 = json.loads(v2_path.read_text(encoding="utf-8-sig"))
            with self.subTest(package=package, side="v2"):
                self.assertEqual(
                    v2.get("locomotion_type"),
                    derived,
                    f"{package}/contract.json 的 locomotion_type 与 v3 morphology 漂移",
                )

    def test_merged_contract_uses_derived_value(self) -> None:
        """合并后的契约（训练侧唯一读取口）必须给出派生值。"""

        for package in self._packages():
            merged = load_training_contract(ROBOTS / package)
            with self.subTest(package=package):
                self.assertEqual(
                    merged["locomotion_type"], locomotion_type_from_contract(self._v3(package))
                )

    def test_unmigrated_contract_keeps_stored_value(self) -> None:
        """无 morphology 的旧契约不猜：沿用存量值，缺失才回落 P。"""

        self.assertEqual(locomotion_type_from_contract({"locomotion_type": "W"}), "W")
        merged = merge_v3_over_v2(None, {"robot_id": "legacy", "locomotion_type": "W"})
        self.assertEqual(merged["locomotion_type"], "W")
        self.assertEqual(locomotion_type_from_contract({"morphology": {}}), "P")

    def test_hand_and_wheel_take_precedence(self) -> None:
        """H 与 W 优先于"腿数"判定——双足轮足仍是 W，灵巧手仍是 H。"""

        hand = {"morphology": {"id": "hand", "legs": 1, "leg_pattern": ["finger1_joint1"]}}
        self.assertEqual(locomotion_type_from_contract(hand), "H")

        wheel_biped = {
            "morphology": {
                "id": "wheel_foot_biped",
                "legs": 2,
                "leg_pattern": ["abad", "hip", "knee", "wheel"],
                "foot_type": "wheel",
            }
        }
        self.assertEqual(locomotion_type_from_contract(wheel_biped), "W")

        sole_biped = {
            "morphology": {
                "id": "biped",
                "legs": 2,
                "leg_pattern": ["hip", "knee", "ankle"],
                "foot_type": "sole",
            }
        }
        self.assertEqual(locomotion_type_from_contract(sole_biped), "B")


if __name__ == "__main__":
    unittest.main()
