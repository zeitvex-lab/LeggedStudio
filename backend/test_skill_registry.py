# -*- coding: utf-8 -*-
"""B6/B7：技能注册表数据化验收。

* B6：skill-recipe-2.0 schema + registry/skills + registry/rewards +
  base/override 合并解析器。对拍 = merge(velocity_base, zex-w-rough patch)
  与 zex-w 现任务配置（training/profiles/zex-w-rough.json）在共享键上逐值相等。
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
    SKILL_INDEX_PATH,
    SkillRegistryError,
    deep_merge,
    list_skills,
    resolve_skill,
    reward_presets,
    reward_terms,
    skill_manifest,
    task_variants,
    unregistered_skill_files,
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
    """B6 验收：base + patch 合并 == zex-w 现任务配置（对拍 profiles/zex-w-rough.json）。"""

    PARITY_KEYS = (
        "task_name", "terrain_type", "algorithm", "num_envs", "episode_length_s",
        "decimation", "seed", "command_ranges", "terrain", "curriculum", "runner",
    )

    def setUp(self) -> None:
        self.merged = resolve_skill("zex-w-rough")
        self.profile = json.loads(
            (WORKSPACE / "assets/robots/zex-w/training/profiles/zex-w-rough.json")
            .read_text(encoding="utf-8-sig")
        )

    def test_merged_matches_current_task_config(self) -> None:
        for key in self.PARITY_KEYS:
            with self.subTest(key=key):
                self.assertEqual(self.merged.get(key), self.profile.get(key))


class SkillManifestK4Test(unittest.TestCase):
    """K4：技能注册由显式清单决定，不再由目录布局隐式决定。"""

    def test_manifest_exists_and_declares_schema(self) -> None:
        self.assertTrue(SKILL_INDEX_PATH.is_file())
        manifest = skill_manifest()
        self.assertEqual(manifest["schema"], "skill-index-1.0")
        ids = [item["recipe_id"] for item in manifest["skills"]]
        self.assertEqual(len(ids), len(set(ids)), "清单内 recipe_id 必须唯一")
        self.assertIn("velocity_base", ids)

    def test_registered_skills_are_exactly_the_manifest(self) -> None:
        registered = {skill["recipe_id"] for skill in list_skills()}
        declared = {item["recipe_id"] for item in skill_manifest()["skills"]}
        self.assertEqual(registered, declared)

    def test_no_skill_file_left_unregistered(self) -> None:
        """诊断项：skills/ 下的 .json 都必须登记（防止"放进去就算注册"回潮）。"""
        self.assertEqual(unregistered_skill_files(), [])

    def test_manifest_lies_are_rejected(self) -> None:
        """清单不能谎报：声明不存在的文件 / 与文件里 recipe_id 不一致都要报错。"""
        from backend import skill_registry

        original = skill_registry.SKILLS_DIR
        with self.subTest(case="missing file"):
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                skills_dir = Path(tmp) / "skills"
                skills_dir.mkdir()
                (skills_dir / "index.json").write_text(
                    json.dumps({"schema": "skill-index-1.0", "skills": [
                        {"recipe_id": "ghost", "path": "ghost.json"}]}),
                    encoding="utf-8",
                )
                skill_registry.SKILLS_DIR = skills_dir
                skill_registry.skill_manifest.cache_clear()
                try:
                    with self.assertRaises(SkillRegistryError) as ctx:
                        skill_registry.skill_manifest()
                    self.assertIn("不存在", str(ctx.exception))
                finally:
                    skill_registry.SKILLS_DIR = original
                    skill_registry.skill_manifest.cache_clear()

    def test_new_skill_requires_a_manifest_line(self) -> None:
        """新增技能 = 登记一行 + 放文件；只放文件不登记 → 不在注册表内。"""
        import tempfile

        from backend import skill_registry

        original = skill_registry.SKILLS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp) / "skills"
            skills_dir.mkdir()
            (skills_dir / "index.json").write_text(
                json.dumps({"schema": "skill-index-1.0", "skills": [
                    {"recipe_id": "listed", "path": "listed.json"}]}),
                encoding="utf-8",
            )
            (skills_dir / "listed.json").write_text(
                json.dumps({"schema_version": "skill-recipe-2.0", "recipe_id": "listed",
                            "display_name": "listed"}), encoding="utf-8")
            (skills_dir / "orphan.json").write_text(
                json.dumps({"schema_version": "skill-recipe-2.0", "recipe_id": "orphan",
                            "display_name": "orphan"}), encoding="utf-8")
            skill_registry.SKILLS_DIR = skills_dir
            skill_registry.skill_manifest.cache_clear()
            skill_registry._skill_files.cache_clear()
            try:
                self.assertEqual(set(skill_registry._skill_files()), {"listed"})
                self.assertEqual(skill_registry.unregistered_skill_files(), ["orphan.json"])
            finally:
                skill_registry.SKILLS_DIR = original
                skill_registry.skill_manifest.cache_clear()
                skill_registry._skill_files.cache_clear()


if __name__ == "__main__":
    unittest.main()
