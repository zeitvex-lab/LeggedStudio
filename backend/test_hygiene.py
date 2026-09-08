"""T0.5 卫生件：注册表独立实例测试（LLoco test_registered_configs_are_independent 同款）。

注册表/工厂两次解析必须返回互不共享可变状态的对象——注册表保存实例、
加载 deepcopy 的纪律一旦被破坏，第二次训练会带着上一次的配置变异启动。
"""

from __future__ import annotations

import unittest

from adapters.mjlab.recipe_registry import get_reward_preset, resolve_recipe


def base_config() -> dict:
    return {
        "task_name": "forward_walk",
        "algorithm": "PPO",
        "num_envs": 64,
        "max_iterations": 5,
        "seed": 1,
        "reward_scales": {"track_linear_velocity": 1.5},
        "command_ranges": {"lin_vel_x": [-1.0, 1.0]},
    }


class RegistryIndependenceTest(unittest.TestCase):
    def test_resolve_recipe_returns_independent_instances(self) -> None:
        first = resolve_recipe(base_config())
        second = resolve_recipe(base_config())

        # 变异第一次的产物，不得影响第二次
        first.reward_scales["track_linear_velocity"] = 99.0
        first.reward_scales["injected"] = 1.0
        first.environment["command_ranges"]["lin_vel_x"] = [-9.0, 9.0]
        first.environment["terrain"]["injected"] = True

        self.assertEqual(second.reward_scales.get("track_linear_velocity"), 1.5)
        self.assertNotIn("injected", second.reward_scales)
        self.assertEqual(second.environment["command_ranges"]["lin_vel_x"], [-1.0, 1.0])
        self.assertNotIn("injected", second.environment["terrain"])

    def test_reward_preset_table_not_mutated(self) -> None:
        preset_before = dict(get_reward_preset("forward_walk"))
        recipe = resolve_recipe(base_config())
        recipe.reward_scales["track_linear_velocity"] = -123.0
        self.assertEqual(get_reward_preset("forward_walk"), preset_before)

    def test_recipe_carries_seed(self) -> None:
        recipe = resolve_recipe(base_config())
        self.assertEqual(recipe.seed, 1)


if __name__ == "__main__":
    unittest.main()
