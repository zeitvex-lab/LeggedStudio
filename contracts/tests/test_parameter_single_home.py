"""B2/2 参数单一家：每个参数只能有一个"家"，其余都是派生视图。

要求原文："机器人参数肯定要确定一套，不能多个叠加，而且最好是统一的，成为标准，
后面也好调试。"

本类守护该性质（漂移即失败，而不是靠人工对账）：

  1. ``size_class`` 的家是"质量桶"——由 ``urdf.total_mass_kg`` 经
     :func:`contracts.models.size_class_for_mass` 派生；契约里的存量声明不得与之分歧
     （实测 lite3 声明 L 而质量 6.25kg、g1 声明 L 而 33.3kg）。
  2. ``mass_source`` 的家是 ``morphology.mass_source``（类型化枚举
     ``mjcf_compiled``|``urdf_inertial``）；``urdf.mass_source`` 只是**投影**，
     不得保留 v2 的自由文本（manual/estimated/mj_model/mjcf-sum/mjcf_inertial_sum）。
  3. 合并后的契约必须携带 ``morphology``——否则 B4 的 ``foot_type`` / ``wheel_indices``
     / ``actuator_type`` 到不了任何消费者（实测修复前 14 个包**全部缺失**）。
  4. ``locomotion_type`` 由 morphology 派生（另见 ``test_locomotion_view``）。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.contract_loader import load_training_contract
from contracts.models import size_class_for_mass

WORKSPACE = Path(__file__).resolve().parents[2]
ROBOTS = WORKSPACE / "assets" / "robots"

# mass_source 的规范枚举（contracts/schema/robot-contract-3.0.schema.json 的 morphology）
MASS_SOURCES = ("mjcf_compiled", "urdf_inertial")


class ParameterSingleHomeTest(unittest.TestCase):
    def _packages(self) -> list[str]:
        return sorted(
            p.name for p in ROBOTS.iterdir() if (p / "contract_v3.json").exists()
        )

    def _v3(self, package: str) -> dict:
        return json.loads(
            (ROBOTS / package / "contract_v3.json").read_text(encoding="utf-8-sig")
        )

    def _v2(self, package: str) -> dict:
        return json.loads(
            (ROBOTS / package / "contract.json").read_text(encoding="utf-8-sig")
        )

    def test_size_class_matches_mass_bucket(self) -> None:
        """size_class 必须等于质量桶——两侧存量声明都不得漂移。"""

        for package in self._packages():
            mass = (self._v2(package).get("urdf") or {}).get("total_mass_kg")
            expected = size_class_for_mass(mass)
            self.assertIsNotNone(expected, f"{package} 缺 total_mass_kg，无法派生 size_class")
            with self.subTest(package=package, side="v3"):
                self.assertEqual(
                    self._v3(package).get("size_class"), expected.value,
                    f"{package}/contract_v3.json 的 size_class 与质量 {mass} 不符",
                )
            with self.subTest(package=package, side="v2"):
                self.assertEqual(
                    self._v2(package).get("size_class"), expected.value,
                    f"{package}/contract.json 的 size_class 与质量 {mass} 不符",
                )

    def test_mass_source_uses_canonical_enum(self) -> None:
        for package in self._packages():
            with self.subTest(package=package):
                self.assertIn(
                    (self._v3(package).get("morphology") or {}).get("mass_source"),
                    MASS_SOURCES,
                )

    def test_merged_contract_carries_morphology(self) -> None:
        """合并契约必须带 morphology：B4 的构型字段是经它传播的。"""

        for package in self._packages():
            merged = load_training_contract(ROBOTS / package)
            morphology = merged.get("morphology")
            with self.subTest(package=package):
                self.assertIsInstance(morphology, dict)
                self.assertTrue(morphology, f"{package} 的合并契约缺 morphology")
                self.assertIn(
                    morphology.get("actuator_type"),
                    ("position", "velocity", "hybrid", "bam"),
                )
                self.assertIsNotNone(morphology.get("mass_source"))
                if morphology.get("id") == "hand":
                    self.assertIsNone(morphology.get("foot_type"))
                else:
                    self.assertIsNotNone(morphology.get("foot_type"))
                self.assertIsInstance(morphology.get("wheel_indices"), list)

    def test_merged_mass_source_is_projection_of_morphology(self) -> None:
        """urdf.mass_source 是投影，必须与真值逐字相同（不再出现 v2 自由文本）。"""

        for package in self._packages():
            merged = load_training_contract(ROBOTS / package)
            with self.subTest(package=package):
                canonical = (merged.get("morphology") or {}).get("mass_source")
                self.assertEqual((merged.get("urdf") or {}).get("mass_source"), canonical)
                self.assertIn(canonical, MASS_SOURCES)

    def test_merged_size_class_is_derived(self) -> None:
        for package in self._packages():
            merged = load_training_contract(ROBOTS / package)
            expected = size_class_for_mass((merged.get("urdf") or {}).get("total_mass_kg"))
            with self.subTest(package=package):
                self.assertEqual(merged.get("size_class"), expected.value)


if __name__ == "__main__":
    unittest.main()
