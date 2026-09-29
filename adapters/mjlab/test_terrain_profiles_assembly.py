"""地形档的**装配层**回归锁（适配器 venv 口径：本文件需要 mjlab）。

仓库纪律同 `adapters/mjlab/test_generic_task_env_smoke.py`——训练栈相关的测试跑在
`adapters/mjlab/.venv`，CI 的零依赖作业里不跑它们。

守的是静态审计判不了的那一半：
* 每档 × 每族：`availability=ready` **必须真能装出来**；`missing` **必须真装不出来**
  （双向对账，避免"声称可用其实不可用"和"能用了却还挂着缺口"）；
* 子地形过滤按声明生效（`stairs` 只留金字塔台阶上/下）；
* 平地档退化为 `terrain_type="plane"`；
* 族 Kit 档（竞赛 / 释放课程）在缺族声明时 fail-closed，指明族时返回该族 refs。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab import terrain_profiles  # noqa: E402


class BuildabilityTest(unittest.TestCase):
    def test_every_declaration_matches_reality(self):
        mismatches: list[str] = []
        for profile_id in terrain_profiles.declared_ids():
            for family in terrain_profiles.FAMILIES:
                status = terrain_profiles.availability(profile_id, family)
                try:
                    terrain_profiles.build_terrain_entity(profile_id, family=family)
                    buildable, error = True, ""
                except Exception as exc:  # noqa: BLE001
                    buildable, error = False, f"{type(exc).__name__}: {exc}"
                if status == "ready" and not buildable:
                    mismatches.append(f"{profile_id}/{family}: 标 ready 但装不出来 —— {error}")
                if status == "missing" and buildable:
                    mismatches.append(f"{profile_id}/{family}: 标 missing 但已能装配")
        self.assertEqual([], mismatches)


class BuilderTest(unittest.TestCase):
    def test_stairs_filters_declared_sub_terrains(self):
        entity = terrain_profiles.build_terrain_entity("stairs")
        self.assertEqual({"pyramid_stairs", "pyramid_stairs_inv"},
                         set(entity.terrain_generator.sub_terrains))

    def test_rough_keeps_full_family(self):
        entity = terrain_profiles.build_terrain_entity("rough")
        names = set(entity.terrain_generator.sub_terrains)
        self.assertIn("random_rough", names)
        self.assertGreater(len(names), 2, "rough 应保留官方整族子地形")

    def test_plane_is_flat(self):
        self.assertEqual("plane", terrain_profiles.build_terrain_entity("plane").terrain_type)

    def test_family_kit_returns_family_refs(self):
        spec = terrain_profiles.build_terrain_entity("competition", family="wheel_leg")
        self.assertEqual("family_kit", spec["kind"])
        self.assertIn("terrain_factory", spec["refs"])

    def test_bad_sub_terrain_is_caught(self):
        entry = {"builder": {"kind": "mjlab_generator", "cfg": "mjlab.terrains.config.ROUGH_TERRAINS_CFG",
                             "sub_terrains": ["no_such_terrain"]},
                 "availability": {"quadruped": "ready", "wheel_leg": "ready"}}
        original = terrain_profiles.resolve
        terrain_profiles.resolve = lambda _pid: entry  # type: ignore[assignment]
        try:
            with self.assertRaises(terrain_profiles.TerrainProfileError):
                terrain_profiles.build_terrain_entity("ghost")
        finally:
            terrain_profiles.resolve = original  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
