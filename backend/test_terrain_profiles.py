"""地形档的**静态**回归锁（仓库 venv / CI 口径，零依赖）。

守：真仓静态审计通过；未知档 fail-closed 且列出可用档；未知族报错；`family_kit` 档必须
指明族；反例注入（未知 kind / family_kit refs 指向不存在的模块）逐条判红。
**装配层**（ready 必须真能装、missing 必须真装不出）在 `adapters/mjlab/test_terrain_profiles_assembly.py`。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import audit_terrain_profiles  # noqa: E402
from adapters.mjlab import terrain_profiles  # noqa: E402


def _entry(**builder) -> dict:
    return {
        "class": "test",
        "summary": "夹具档位",
        "evidence": {"source": "测试夹具"},
        "builder": builder,
        "availability": {"quadruped": "ready", "wheel_leg": "ready"},
    }


class StaticAuditTest(unittest.TestCase):
    def test_real_repo_passes(self):
        report = audit_terrain_profiles.audit()
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(10, len(report["rows"]), "5 档 × 2 族")

    def test_unknown_builder_kind_is_caught(self):
        fake = {"ghost": _entry(kind="magic")}
        with mock.patch.object(terrain_profiles, "profiles", lambda: fake):
            report = audit_terrain_profiles.audit()
        self.assertFalse(report["ok"])
        self.assertTrue(any("未知 builder.kind" in item for item in report["problems"]), report["problems"])

    def test_family_kit_ref_must_exist(self):
        fake = {"ghost": _entry(kind="family_kit", wheel_leg={"terrain_factory": "no.such.module"})}
        with mock.patch.object(terrain_profiles, "profiles", lambda: fake):
            report = audit_terrain_profiles.audit()
        self.assertFalse(report["ok"])
        self.assertTrue(any("指向不存在的模块" in item for item in report["problems"]), report["problems"])

    def test_missing_evidence_is_caught(self):
        fake = {"ghost": {**_entry(kind="flat"), "evidence": {}}}
        with mock.patch.object(terrain_profiles, "profiles", lambda: fake):
            report = audit_terrain_profiles.audit()
        self.assertFalse(report["ok"])
        self.assertTrue(any("evidence.source" in item for item in report["problems"]), report["problems"])


class ResolverTest(unittest.TestCase):
    def test_unknown_profile_lists_available(self):
        with self.assertRaises(terrain_profiles.TerrainProfileError) as ctx:
            terrain_profiles.resolve("nope")
        message = str(ctx.exception)
        self.assertIn("可用档", message)
        self.assertIn("stairs", message)

    def test_unknown_family_is_caught(self):
        with self.assertRaises(terrain_profiles.TerrainProfileError):
            terrain_profiles.availability("stairs", "humanoid")

    def test_family_kit_requires_family(self):
        with self.assertRaises(terrain_profiles.TerrainProfileError):
            terrain_profiles.build_terrain_entity("competition")

    def test_family_kit_quadruped_ready_returns_refs(self):
        # 2026-09-30 起四足 ready（课程三件套上提 kits 共享层）：请求四足构造必须
        # 返回共享层 refs（不得再报错）。防回归：改回 missing 而不删本测试属违规。
        result = terrain_profiles.build_terrain_entity("competition", family="quadruped")
        self.assertEqual(result["kind"], "family_kit")
        refs = result["refs"]
        self.assertIn("adapters.mjlab.kits", str(refs.get("curriculum", "")))


if __name__ == "__main__":
    unittest.main()
