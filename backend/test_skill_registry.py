# -*- coding: utf-8 -*-
"""B6/B7：技能注册表数据化验收。

* B6：skill-recipe-2.0 schema + registry/skills + registry/rewards +
  base/override 合并解析器。对拍 = merge(velocity_base, zex-w-rough patch)
  与 zex-w 现任务配置（training/profiles/rough.json）在共享键上逐值相等。
* B7：recipe_registry.TASKS 与 env_factory 奖励表由数据驱动——新增技能
  只写 Recipe JSON，不改代码。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from backend.skill_registry import (  # noqa: E402
    SkillRegistryError,
    deep_merge,
    list_skills,
    resolve_skill,
    reward_presets,
    reward_terms,
    task_variants,
)


def _registry(rel: str) -> dict:
    return json.loads((WORKSPACE / "registry" / rel).read_text(encoding="utf-8-sig"))


class SkillRegistryB6Test(unittest.TestCase):
    def test_schema_and_skills_files_exist(self) -> None:
        self.assertTrue((WORKSPACE / "contracts/schema/skill-recipe-2.0.schema.json").exists())
        self.assertTrue((WORKSPACE / "registry/skills/velocity_base.json").exists())
        self.assertTrue((WORKSPACE / "registry/skills/patches/zex-w-rough.json").exists())

    def test_merge_semantics(self) -> None:
        merged = deep_merge({"a": {"b": 1, "c": 2}, "l": [1, 2]}, {"a": {"b": 9, "d": 3}, "l": [3]})
        self.assertEqual(merged, {"a": {"b": 9, "c": 2, "d": 3}, "l": [3]})

    def test_resolve_follows_extends_chain(self) -> None:
        merged = resolve_skill("zex-w-rough")
        self.assertEqual(merged["recipe_id"], "zex-w-rough")
        self.assertEqual(merged["task_name"], "rough_terrain")
        # 来自 base 的字段
        self.assertEqual(merged["algorithm"], "PPO")
        self.assertEqual(merged["episode_length_s"], 20.0)
        self.assertIn("tasks", merged)
        # patch 覆盖 base
        self.assertEqual(merged["num_envs"], 2048)

    def test_unknown_and_cycle_errors(self) -> None:
        with self.assertRaises(SkillRegistryError):
            resolve_skill("no-such-recipe")

    def test_reward_catalog_and_presets_data(self) -> None:
        terms = reward_terms()
        self.assertIn("tracking_lin_vel", terms)
        self.assertFalse(terms["feet_air_time"]["supported"])
        presets = reward_presets()
        for task in ("forward_walk", "trot", "rough_terrain", "stairs"):
            self.assertIn(task, presets)
        self.assertEqual(task_variants()["rough_terrain"]["terrain"], "rough")

    def test_list_tasks_and_skills(self) -> None:
        from adapters.mjlab import recipe_registry

        tasks = {t["id"] for t in recipe_registry.list_tasks()}
        self.assertEqual(tasks, {"forward_walk", "trot", "rough_terrain", "stairs"})
        skill_ids = {s["recipe_id"] for s in list_skills()}
        self.assertIn("velocity_base", skill_ids)
        self.assertIn("zex-w-rough", skill_ids)


class VelocityBaseZexwMergeParityTest(unittest.TestCase):
    """B6 验收：base + patch 合并 == zex-w 现任务配置（对拍 profiles/rough.json）。"""

    PARITY_KEYS = (
        "task_name", "terrain_type", "algorithm", "num_envs", "episode_length_s",
        "decimation", "seed", "command_ranges", "terrain", "curriculum", "runner",
    )

    def setUp(self) -> None:
        self.merged = resolve_skill("zex-w-rough")
        self.profile = json.loads(
            (WORKSPACE / "assets/robots/zex-w/training/profiles/rough.json")
            .read_text(encoding="utf-8-sig")
        )

    def test_merged_matches_current_task_config(self) -> None:
        for key in self.PARITY_KEYS:
            with self.subTest(key=key):
                self.assertEqual(self.merged.get(key), self.profile.get(key))


if __name__ == "__main__":
    unittest.main()
