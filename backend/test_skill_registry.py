# -*- coding: utf-8 -*-
"""B6/B7：技能注册表数据化验收。

* B6：skill-recipe-2.0 schema + registry/skills + registry/rewards +
  base/override 合并解析器。**Phase 6（2026-10-07）**：机型补丁**迁出技能注册表** ——
  技能注册表只放**族级基座**，机型差异的家是 profile 层（`assets/robots/<id>/training/profiles/`，
  支持 extends/overrides）。旧 `patches/zex-w-rough.json` 与 profile 在 11 个共享键上
  **逐值相等**（B6 对拍即证），该证据转为 `ZexwRoughProfileSnapshotTest` 的迁移快照。
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

    def test_merge_semantics(self) -> None:
        merged = deep_merge({"a": {"b": 1, "c": 2}, "l": [1, 2]}, {"a": {"b": 9, "d": 3}, "l": [3]})
        self.assertEqual(merged, {"a": {"b": 9, "c": 2, "d": 3}, "l": [3]})

    def _with_synthetic_skills(self, skills: dict[str, dict]):
        """把 SKILLS_DIR 临时换成合成注册表（返回上下文管理器）。"""
        import tempfile
        from contextlib import contextmanager

        from backend import skill_registry

        @contextmanager
        def _ctx():
            original = skill_registry.SKILLS_DIR
            with tempfile.TemporaryDirectory() as tmp:
                skills_dir = Path(tmp) / "skills"
                skills_dir.mkdir()
                (skills_dir / "index.json").write_text(json.dumps({
                    "schema": "skill-index-1.0",
                    "skills": [{"recipe_id": rid, "path": f"{rid}.json"} for rid in skills],
                }), encoding="utf-8")
                for rid, doc in skills.items():
                    (skills_dir / f"{rid}.json").write_text(json.dumps(doc), encoding="utf-8")
                skill_registry.SKILLS_DIR = skills_dir
                # 两个 lru_cache 必须先失效，否则读到上一组测试留下的真注册表
                skill_registry.skill_manifest.cache_clear()
                skill_registry._skill_files.cache_clear()
                try:
                    yield skill_registry
                finally:
                    skill_registry.SKILLS_DIR = original
                    skill_registry.skill_manifest.cache_clear()
                    skill_registry._skill_files.cache_clear()

        return _ctx()

    def test_resolve_follows_extends_chain(self) -> None:
        """extends 链语义（合成样本：真机型补丁迁出后，这里继续钉住合并规则）。"""
        with self._with_synthetic_skills({
            "base": {
                "schema": "skill-recipe-2.0", "recipe_id": "base", "display_name": "base",
                "episode_length_s": 20.0, "num_envs": 4096,
                "runner": {"learning_rate": 0.001, "gamma": 0.99},
            },
            "patch": {
                "schema": "skill-recipe-2.0", "recipe_id": "patch", "display_name": "patch",
                "extends": "base", "num_envs": 2048, "runner": {"learning_rate": 0.0008},
            },
        }) as registry:
            merged = registry.resolve_skill("patch")
        self.assertEqual(merged["recipe_id"], "patch")
        self.assertEqual(merged["episode_length_s"], 20.0, "base 字段带过来")
        self.assertEqual(merged["num_envs"], 2048, "patch 覆盖 base（标量）")
        self.assertEqual(merged["runner"]["learning_rate"], 0.0008, "patch 覆盖 base（嵌套键）")
        self.assertEqual(merged["runner"]["gamma"], 0.99, "base 未覆盖的嵌套键保留（深合并）")

    def test_extends_cycle_is_rejected(self) -> None:
        with self._with_synthetic_skills({
            "a": {"schema": "skill-recipe-2.0", "recipe_id": "a", "display_name": "a", "extends": "b"},
            "b": {"schema": "skill-recipe-2.0", "recipe_id": "b", "display_name": "b", "extends": "a"},
        }) as registry:
            with self.assertRaises(SkillRegistryError):
                registry.resolve_skill("a")

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
        self.assertNotIn("zex-w-rough", skill_ids,
                         "机型补丁不进技能注册表（Phase 6：家是 profile 层）")


class MachinePatchHomeTest(unittest.TestCase):
    """Phase 6 规则：机型补丁的家是 **profile 层**，不是技能注册表。"""

    def test_registry_holds_only_family_level_bases(self) -> None:
        entries = skill_manifest()["skills"]
        ids = {item["recipe_id"] for item in entries}
        self.assertIn("velocity_base", ids)
        for item in entries:
            with self.subTest(recipe_id=item["recipe_id"]):
                self.assertNotEqual(
                    "patch", item.get("role"),
                    "技能注册表只放族级基座；机型补丁请放 profile 层（Phase 6）",
                )

    def test_patches_dir_is_retired(self) -> None:
        patches = WORKSPACE / "registry" / "skills" / "patches"
        found = sorted(p.name for p in patches.glob("*.json")) if patches.is_dir() else []
        self.assertEqual([], found, "registry/skills/patches/ 已退役（机型补丁迁 profile 层）")


class ZexwRoughProfileSnapshotTest(unittest.TestCase):
    """Phase 6 迁移证据：机型补丁迁出后，真值仍在 profile 层且**逐值不变**。

    下面这些值 = 被删除的 `registry/skills/patches/zex-w-rough.json` 在 B6 对拍里
    被证明与 profile **逐值相等**的那些键（对拍：git 历史里本文件旧的
    ``VelocityBaseZexwMergeParityTest``，11 个共享键）。迁出后 profile 是唯一家 ——
    锁在这里防"顺手清掉"，也防"迁移后配置悄悄变了"。
    """

    EXPECTED_SCALARS = {
        "task_name": "rough_terrain",
        "terrain_type": "rough",
        "algorithm": "PPO",
        "num_envs": 2048,
        "episode_length_s": 20.0,
        "decimation": 4,
        "seed": 42,
        "command_ranges": {
            "lin_vel_x": [-1.0, 1.0],
            "lin_vel_y": [-1.0, 1.0],
            "ang_vel_z": [-1.0, 1.0],
        },
    }

    @staticmethod
    def _profile() -> dict:
        return json.loads(
            (WORKSPACE / "assets/robots/zex-w/training/profiles/zex-w-rough.json")
            .read_text(encoding="utf-8-sig")
        )

    def test_profile_carries_the_migrated_scalars(self) -> None:
        profile = self._profile()
        for key, expected in self.EXPECTED_SCALARS.items():
            with self.subTest(key=key):
                self.assertEqual(expected, profile.get(key))

    def test_profile_carries_the_migrated_terrain_and_curriculum(self) -> None:
        profile = self._profile()
        self.assertEqual(profile["terrain"]["sub_terrains"]["rc_wall"], 0.15)
        self.assertEqual(profile["terrain"]["num_rows"], 10)
        self.assertEqual(profile["terrain"]["num_cols"], 20)
        curriculum = profile["curriculum"]
        self.assertEqual("terrain_levels_obstacle_release", curriculum["terrain_levels"])
        self.assertEqual([-0.5, 0.5], curriculum["command_initial_range"])
        self.assertEqual(curriculum["command_delta"], 0.05)
        self.assertEqual(curriculum["command_target_ratio"], 0.8)
        self.assertEqual(
            curriculum["terrain_release_env_steps"],
            [[4800, ["random_grid"]], [12000, ["pyramid_stairs_inv"]], [16800, ["rc_wall"]]],
        )

    def test_profile_carries_the_migrated_runner(self) -> None:
        runner = self._profile()["runner"]
        self.assertEqual(runner["learning_rate"], 0.0008)
        self.assertEqual(runner["entropy_coef"], 0.003)
        self.assertEqual(runner["max_iterations"], 20000)
        self.assertEqual(runner["hidden_dims"], [512, 256, 128])


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
                json.dumps({"schema": "skill-recipe-2.0", "recipe_id": "listed",
                            "display_name": "listed"}), encoding="utf-8")
            (skills_dir / "orphan.json").write_text(
                json.dumps({"schema": "skill-recipe-2.0", "recipe_id": "orphan",
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
