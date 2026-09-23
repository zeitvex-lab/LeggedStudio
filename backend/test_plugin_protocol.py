"""T6.1/T6.3 DoD：ls_plugin 协议测试——16 包全过校验、脚手架→校验闭环、
三谓词匹配、catalog 汇总。"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.plugin_protocol import (
    generate_catalog,
    match_profiles,
    scaffold_package,
    validate_package,
)

WORKSPACE = Path(__file__).resolve().parents[1]
ROBOTS = WORKSPACE / "assets" / "robots"


class ValidatePackagesTest(unittest.TestCase):
    def test_all_builtin_packages_pass_validation(self) -> None:
        for package_dir in sorted(p for p in ROBOTS.iterdir() if (p / "contract_legacy_v2.json").exists()):
            with self.subTest(package=package_dir.name):
                report = validate_package(package_dir)
                self.assertTrue(report["ok"], f"{package_dir.name}: {report['errors']}")


class ScaffoldRoundtripTest(unittest.TestCase):
    def test_scaffold_then_validate(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = scaffold_package(Path(tmp), "my_robot")
            report = validate_package(path)
            self.assertTrue(report["ok"], report["errors"])
            contract_truth = (path / "contract.json").read_text(encoding="utf-8")
            self.assertIn('"robot_id": "my_robot"', contract_truth)

    def test_duplicate_scaffold_rejected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            scaffold_package(Path(tmp), "my_robot")
            with self.assertRaises(ValueError):
                scaffold_package(Path(tmp), "my_robot")


class ThreePredicateMatchTest(unittest.TestCase):
    CONTRACT = {
        "robot_id": "unitree_go2",
        "morphology": {"id": "quadruped_12dof"},
        "joints": {"actuated": [{"name": f"{leg}_{role}_joint", "role": role} for leg in ("FL",) for role in ("hip", "thigh", "calf")]},
        "action": {"joint_order": [f"{leg}_{role}_joint" for leg in ("FL",) for role in ("hip", "thigh", "calf")]},
    }

    def test_matching_predicates(self) -> None:
        profiles = [
            {"profile_id": "universal", "requires_morphology": [], "requires_roles": []},
            {"profile_id": "quad_only", "requires_morphology": ["quadruped_12dof"], "requires_roles": ["hip"]},
            {"profile_id": "wheel_only", "requires_morphology": ["wheel_leg_16dof"]},
            {"profile_id": "needs_wheel_role", "requires_roles": ["wheel"]},
            {"profile_id": "dim_mismatch", "action_dim": 16},
        ]
        result = match_profiles(self.CONTRACT, profiles)
        by_id = {item["profile_id"]: item for item in result["profiles"]}
        self.assertTrue(by_id["universal"]["compatible"])
        self.assertTrue(by_id["quad_only"]["compatible"])
        self.assertFalse(by_id["wheel_only"]["compatible"])
        self.assertFalse(by_id["needs_wheel_role"]["compatible"])
        self.assertFalse(by_id["dim_mismatch"]["compatible"])


class CatalogTest(unittest.TestCase):
    def test_catalog_covers_packages_with_hashes(self) -> None:
        packages = sorted(p for p in ROBOTS.iterdir() if (p / "contract_legacy_v2.json").exists())
        catalog = generate_catalog(packages)
        # family-arch 收敛后内置包恰为 8（4 四足 + 4 轮足）：候选目录与目录条目精确相等，
        # 每个包都必须进目录且带模型哈希（原 ≥14 的旧口径随收敛更新）。
        self.assertEqual(
            [p.name for p in packages],
            sorted(entry["package_id"] for entry in catalog["packages"]),
        )
        for entry in catalog["packages"]:
            self.assertTrue(entry["valid"], f"{entry['package_id']}: invalid")
            self.assertTrue(entry["model_sha256"])
        self.assertEqual(catalog["schema_version"], "ls-plugin-catalog-1.0")


if __name__ == "__main__":
    unittest.main()
