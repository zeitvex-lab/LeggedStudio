"""U9：包扩展训练档案的配方解析（resolve_recipe 豁免）测试。

背景（00_know/05_任务清单.md §U9）：带 entrypoints 的训练档案（deeprobotics_lite3
的 ``lite3-velocity`` 等）由 native_worker 按 ``profile.entrypoints`` 注册
``LeggedStudio-<profile_id>`` 的包扩展任务训练；``profile.task_name``（如
"velocity"）只是产物逻辑名，不在通用 TASKS 表里 —— 此前拿它走
``POST /api/training/resolve-recipe`` 必然 400（unknown task），训练页预览红失败。

钉住三件事：

1. lite3-velocity 档案场景：resolve 不再 400，产物**诚实标注来源**
   （environment.source = package-extension + native_task_id），奖励表不编造
   （不并通用预设，只透传显式覆盖）；
2. 通用 4 任务照常校验，**产物 dump 逐字节同形**（environment 无 source 键 ——
   B9 冒烟门按 canonical digest 比对既有 Run，形状漂移会让全部冒烟证据失效）；
3. fail-closed：未知 profile_id / 档案 task_name 与请求不符 / 档案声明不合法
   （缺 entrypoints、valid=False）/ 跨包歧义 → 仍按未知任务报错。
"""

from __future__ import annotations

import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.mjlab.recipe_registry import resolve_recipe  # noqa: E402


def _lite3_profile_payload() -> dict:
    """训练页 collectConfig 的真实形状（profile 模式，奖励走点路径覆盖）。"""
    return {
        "robot_id": "deeprobotics_lite3",
        "profile_id": "lite3-velocity",
        "algorithm": "PPO",
        "task_name": "velocity",
        "terrain_type": "plane",
        "device": "auto",
        "num_envs": 4096,
        "max_iterations": 1000,
        "learning_rate": 0.0003,
        "save_interval": 100,
        "episode_length_s": None,
        "seed": 0,
        "num_steps": 24,
        "num_minibatches": 4,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_param": 0.2,
        "entropy_coef": 0.01,
        "reward_scales": {},
        "reward_overrides": False,
        "reward_params": {},
        "command_ranges": {},
        "noise": {},
        "curriculum": {},
    }


def _synthetic_profile(**overrides) -> dict:
    """合成的合法包扩展档案（供 mock list_robot_packages 的 fail-closed 用例）。"""
    profile = {
        "profile_id": "synth-ext",
        "task_name": "velocity",
        "algorithm": "PPO",
        "backend": "native_mjlab",
        "schema_version": "training-profile-1.0",
        "entrypoints": {
            "env": "synth_task.env_cfg:synth_flat_env_cfg",
            "runner": "synth_task.env_cfg:synth_runner_cfg",
        },
        "valid": True,
        "validation_errors": [],
    }
    profile.update(overrides)
    return profile


def _packages_with(*profiles) -> list[dict]:
    return [{"robot_id": "synth", "training_profiles": list(profiles)}]


class PackageExtensionRecipeTest(unittest.TestCase):
    """resolve_recipe 的包扩展豁免（真实内置包数据）。"""

    def test_lite3_velocity_profile_resolves_without_error(self):
        """U9 主场景：lite3-velocity 档案 payload 不再 400（unknown task velocity）。"""
        recipe = resolve_recipe(_lite3_profile_payload())
        self.assertEqual(recipe.task_name, "velocity")
        self.assertEqual(recipe.algorithm, "PPO")
        self.assertEqual(recipe.backend, "native_mjlab")

    def test_lite3_recipe_honestly_labels_package_extension_source(self):
        """产物诚实标注来源：environment.source + native_task_id（与 worker 注册名同式）。"""
        recipe = resolve_recipe(_lite3_profile_payload())
        self.assertEqual(recipe.environment.get("source"), "package-extension")
        self.assertEqual(recipe.environment.get("native_task_id"), "LeggedStudio-lite3-velocity")

    def test_lite3_recipe_does_not_fabricate_reward_table(self):
        """不编造奖励表：通用预设不并入，只透传请求显式提供的覆盖。"""
        payload = _lite3_profile_payload()
        self.assertEqual(resolve_recipe(payload).reward_scales, {})
        payload["reward_scales"] = {"action_rate_l2": -0.02}
        self.assertEqual(resolve_recipe(payload).reward_scales, {"action_rate_l2": -0.02})

    def test_lite3_recipe_respects_episode_length_semantics(self):
        """B23 语义同通用路径：显式提供才写键，None → 键不存在。"""
        payload = _lite3_profile_payload()
        self.assertNotIn("episode_length_s", resolve_recipe(payload).environment)
        payload["episode_length_s"] = 24.0
        self.assertEqual(resolve_recipe(payload).environment["episode_length_s"], 24.0)

    def test_generic_task_payload_with_extension_profile_stays_generic(self):
        """task_name 在通用表内的请求一律走通用路径（豁免只兜本会 400 的请求）。"""
        payload = _lite3_profile_payload()
        payload["task_name"] = "forward_walk"
        recipe = resolve_recipe(payload)
        self.assertEqual(recipe.task_name, "forward_walk")
        self.assertNotIn("source", recipe.environment)
        self.assertTrue(recipe.reward_scales)  # 通用预设照常并入

    def test_generic_recipe_dump_shape_unchanged(self):
        """通用配方 dump 逐键同形（B9 冒烟证据防漂移）：environment 无 source/native_task_id。"""
        dump = resolve_recipe({"task_name": "trot", "num_envs": 64}).model_dump(mode="json")
        self.assertEqual(
            set(dump["environment"].keys()),
            {"num_envs", "terrain_type", "terrain", "command_ranges", "noise", "curriculum", "reward_params"},
        )

    def test_unknown_task_without_profile_fails_closed(self):
        """无 profile_id 的未知任务照旧报错（错误文案不变）。"""
        with self.assertRaises(ValueError) as ctx:
            resolve_recipe({"task_name": "velocity"})
        self.assertIn("unknown task velocity", str(ctx.exception))

    def test_unknown_profile_id_fails_closed(self):
        """profile_id 查不到 → 不豁免，照旧报错。"""
        with self.assertRaises(ValueError) as ctx:
            resolve_recipe({"task_name": "velocity", "profile_id": "no-such-profile"})
        self.assertIn("unknown task velocity", str(ctx.exception))


class PackageExtensionFailClosedTest(unittest.TestCase):
    """豁免判据逐条 fail-closed（mock 包索引，不碰真实包数据）。"""

    def _resolve_with_packages(self, config: dict, *profiles: dict):
        with mock.patch("backend.robot_packages.list_robot_packages", return_value=_packages_with(*profiles)):
            return resolve_recipe(config)

    def test_profile_without_entrypoints_fails_closed(self):
        with self.assertRaises(ValueError) as ctx:
            self._resolve_with_packages(
                {"task_name": "velocity", "profile_id": "synth-ext"},
                _synthetic_profile(entrypoints=None),
            )
        self.assertIn("unknown task velocity", str(ctx.exception))

    def test_env_entrypoint_missing_fails_closed(self):
        with self.assertRaises(ValueError):
            self._resolve_with_packages(
                {"task_name": "velocity", "profile_id": "synth-ext"},
                _synthetic_profile(entrypoints={"env": "synth_task.env_cfg:synth_flat_env_cfg"}),
            )

    def test_invalid_profile_fails_closed(self):
        with self.assertRaises(ValueError):
            self._resolve_with_packages(
                {"task_name": "velocity", "profile_id": "synth-ext"},
                _synthetic_profile(valid=False, validation_errors=["entrypoints must be an object"]),
            )

    def test_task_name_mismatch_fails_closed(self):
        """请求 task_name 与档案声明的产物逻辑名不一致 → 不豁免。"""
        with self.assertRaises(ValueError):
            self._resolve_with_packages(
                {"task_name": "velocity", "profile_id": "synth-ext"},
                _synthetic_profile(task_name="something_else"),
            )

    def test_ambiguous_profile_across_packages_fails_closed(self):
        """同名 profile_id 跨包歧义 → 不豁免（宁可报错也不能猜错任务）。"""
        with mock.patch(
            "backend.robot_packages.list_robot_packages",
            return_value=_packages_with(_synthetic_profile(), _synthetic_profile()),
        ):
            with self.assertRaises(ValueError):
                resolve_recipe({"task_name": "velocity", "profile_id": "synth-ext"})


class ResolveRecipeEndpointTest(unittest.TestCase):
    """HTTP 层：训练页预览链路（POST /api/training/resolve-recipe）。"""

    def test_resolve_recipe_endpoint_accepts_lite3_profile_payload(self):
        from fastapi.testclient import TestClient

        from backend.api_complete import app

        response = TestClient(app).post("/api/training/resolve-recipe", json=_lite3_profile_payload())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["valid"])
        recipe = payload["recipe"]
        self.assertEqual(recipe["task_name"], "velocity")
        self.assertEqual(recipe["environment"]["source"], "package-extension")

    def test_resolve_recipe_endpoint_still_rejects_unknown_task(self):
        from fastapi.testclient import TestClient

        from backend.api_complete import app

        response = TestClient(app).post("/api/training/resolve-recipe", json={"task_name": "velocity"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
