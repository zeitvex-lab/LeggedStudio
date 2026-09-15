"""D7：契约 v3 构型语义在 UI 可读（形态 / 角色 / 执行器类型 / 足型 / 轮组）。

真值在包内 ``contract_v3.json`` 的 ``morphology`` 块（v2 ``contract.json`` 没有）；
后端 ``list_robot_packages()`` 经 ``_morphology_view`` 把它暴露为 record 的 ``morphology``
字段，前端 ``assets.html`` 的包卡片渲染它。判据：五个语义都能在 UI 读到，且来自契约
真值而非前端硬编码（否则又会出现"页面有、契约没有"的两套真值）。
"""

import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROBOTS = PROJECT_ROOT / "assets" / "robots"

from backend.robot_packages import list_robot_packages  # noqa: E402


class MorphologyViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = {r["robot_id"]: r for r in list_robot_packages()}

    def test_every_package_exposes_contract_v3_morphology(self):
        for robot_id, record in self.records.items():
            with self.subTest(robot=robot_id):
                morph = record.get("morphology") or {}
                self.assertEqual(
                    "contract_v3", morph.get("source"),
                    "每个包都该从包内 contract_v3.json 读到 morphology",
                )
                self.assertIn("id", morph)
                self.assertIn("actuator_type", morph)
                # foot_type 不是每个包都有：wuji_hand 是手（id=hand），没有足型；有则属
                # point/wheel/sole 之一。
                if "foot_type" in morph:
                    self.assertIn(morph["foot_type"], ("point", "wheel", "sole"))

    def test_roles_are_derived_from_leg_pattern(self):
        go2 = self.records["unitree_go2"]["morphology"]
        self.assertEqual(["hip", "thigh", "calf"], go2["roles"])
        g1 = self.records["unitree_g1"]["morphology"]
        self.assertIn("waist_yaw", g1["roles"], "extra_roles 也要并入 roles")

    def test_wheel_groups_marked_only_on_wheel_robots(self):
        wheel = {"deeprobotics_m20", "unitree_b2w", "unitree_go2w", "zex-w", "limx_tron1_wf"}
        for robot_id, record in self.records.items():
            with self.subTest(robot=robot_id):
                count = record["morphology"].get("wheel_count", 0)
                if robot_id in wheel:
                    self.assertGreater(count, 0)
                else:
                    self.assertEqual(0, count)

    def test_morphology_view_matches_on_disk_contract(self):
        # 视图必须等于包内 contract_v3.json 的 morphology 块（不另造真值）。
        for robot_id, record in self.records.items():
            with self.subTest(robot=robot_id):
                disk = json.loads(
                    (ROBOTS / robot_id / "contract_v3.json").read_text(encoding="utf-8-sig")
                )
                expect = dict(disk.get("morphology") or {})
                morph = dict(record["morphology"])
                for key, value in expect.items():
                    self.assertEqual(value, morph.get(key), f"morphology.{key} 应与契约一致")


class MorphologyUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (PROJECT_ROOT / "web" / "assets.html").read_text(encoding="utf-8")

    def test_card_renders_five_semantics(self):
        # 五个语义都要出现在卡片渲染里。
        for token in ("morph.id", "morph.roles", "morph.actuator_type",
                      "morph.foot_type", "morph.wheel_count"):
            self.assertIn(token, self.html, f"卡片必须渲染 {token}")

    def test_morphology_comes_from_backend_not_hardcoded(self):
        self.assertIn("item.morphology", self.html,
                      "形态语义必须来自后端 record 的 morphology 字段")

    def test_missing_contract_does_not_crash_card(self):
        # 后端契约缺失返回 source=missing，前端只在 source==='contract_v3' 时渲染。
        self.assertIn("morph.source==='contract_v3'", self.html)


if __name__ == "__main__":
    unittest.main()
