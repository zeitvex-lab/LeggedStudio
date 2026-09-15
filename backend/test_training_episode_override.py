"""B23：episode_length_s 的「省略 = 任务真值，显式提供才覆盖」语义守卫。

真值层裁决（V2 单一真值 + V4 杜绝静默变差）：任务真值住在 Recipe/训练源码里
（如 microduck standup 的 6s），训练请求链不得用硬默认 20.0 冒充它：

1. ``backend/training/models.py``   —— 请求缺省 None（不再硬默认 20.0），显式给值必须 > 0；
2. ``backend/training/create.py``   —— config 键恒存在、值可为 None（组装惯例同 resume_from）；
3. ``adapters/mjlab/recipe_registry.py`` —— 仅显式提供才把键写进 environment（省略 → 键不存在）；
4. ``adapters/mjlab/native_worker.py``   —— 守卫式覆盖：environment/config 取到 None 时不动 env_cfg。

纯控制面测试：不 import mjlab/torch（native_worker 顶层仅 stdlib，可在控制面 venv 导入）。
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from pydantic import ValidationError

from backend.training.models import CreateTrainingRequest
from adapters.mjlab.recipe_registry import resolve_recipe
from adapters.mjlab.native_worker import apply_training_recipe


def _request(**overrides) -> CreateTrainingRequest:
    return CreateTrainingRequest(contract={}, **overrides)


def _worker_config(*, environment: dict | None, config_episode_length: float | None | object) -> dict:
    """构造 apply_training_recipe 的最小 config（resolved_recipe + 顶层键）。

    ``config_episode_length`` 用 sentinel 区分「键不存在」与「显式 None」。
    """
    config: dict = {
        "resolved_recipe": {
            "task_name": "forward_walk",
            "environment": {} if environment is None else environment,
            "reward_scales": {},
            "algorithm_config": {},
        },
    }
    if config_episode_length is not ...:
        config["episode_length_s"] = config_episode_length
    return config


def _apply(*, environment: dict | None, config_episode_length: float | None | object, source_truth: float = 6.0):
    """跑一遍 apply_training_recipe，返回覆盖后的 env_cfg（standup 6s 真值作底）。"""
    env_cfg = SimpleNamespace(
        episode_length_s=source_truth,
        scene=SimpleNamespace(num_envs=8, terrain=None),
        rewards={},
    )
    rl_cfg = SimpleNamespace()  # 无 algorithm / num_steps_per_env 等 attr → 算法段全跳过
    apply_training_recipe(env_cfg, rl_cfg, _worker_config(
        environment=environment, config_episode_length=config_episode_length,
    ))
    return env_cfg


class RequestModelDefaultsTest(unittest.TestCase):
    """models.py：缺省 = None；显式给值必须 > 0。"""

    def test_default_is_none(self):
        self.assertIsNone(_request().episode_length_s)

    def test_explicit_value_kept_as_float(self):
        self.assertEqual(_request(episode_length_s=10).episode_length_s, 10.0)

    def test_explicit_none_allowed(self):
        self.assertIsNone(_request(episode_length_s=None).episode_length_s)

    def test_zero_rejected(self):
        with self.assertRaises(ValidationError):
            _request(episode_length_s=0)

    def test_negative_rejected(self):
        with self.assertRaises(ValidationError):
            _request(episode_length_s=-6.0)


class CreatePayloadTest(unittest.TestCase):
    """create.py：config["episode_length_s"] 恒存在，值 = 请求值（省略 → None）。

    create.py 的 config 组装内联在 async 端点里，不便直接单测；这里用
    ``model_dump()`` 精确复现它写入 config 的那一行（``request.episode_length_s``）。
    """

    def test_omitted_maps_to_none(self):
        self.assertIsNone(_request().model_dump()["episode_length_s"])

    def test_explicit_maps_to_float(self):
        # UI 路径：预填 profile 真值、显式提交 10 → config 里是 10.0
        self.assertEqual(_request(episode_length_s=10).model_dump()["episode_length_s"], 10.0)


class ResolveRecipeTest(unittest.TestCase):
    """recipe_registry.py：仅显式提供才写键（省略/None → environment 不含该键）。"""

    def _recipe_environment(self, config: dict) -> dict:
        # 与 create.py 的消费方式一致： TrainingRecipe.model_dump(mode="json") 后取 environment
        return resolve_recipe(config).model_dump(mode="json")["environment"]

    def test_key_absent_when_omitted(self):
        environment = self._recipe_environment({"task_name": "forward_walk"})
        self.assertNotIn("episode_length_s", environment)

    def test_key_absent_when_none(self):
        # create.py 现在会写入显式 None —— 同样不得出现在 recipe 里（不是 null）
        environment = self._recipe_environment({"task_name": "forward_walk", "episode_length_s": None})
        self.assertNotIn("episode_length_s", environment)

    def test_explicit_value_written(self):
        environment = self._recipe_environment({"task_name": "forward_walk", "episode_length_s": 10})
        self.assertEqual(environment["episode_length_s"], 10.0)

    def test_explicit_value_coerced_to_float(self):
        environment = self._recipe_environment({"task_name": "forward_walk", "episode_length_s": "12"})
        self.assertEqual(environment["episode_length_s"], 12.0)


class WorkerGuardTest(unittest.TestCase):
    """native_worker.py：None/缺键不动 env_cfg（保留源码真值），非 None 才覆盖。"""

    def test_omitted_keeps_source_truth(self):
        # API 直调省略字段：environment 无键 + config None → standup 的 6s 不被 20s 冒充
        self.assertEqual(_apply(environment=None, config_episode_length=None).episode_length_s, 6.0)

    def test_keys_fully_absent_keeps_source_truth(self):
        # 直连 manager.create_task 的调用方（config 里根本没有该键）→ 同样不动真值
        self.assertEqual(_apply(environment=None, config_episode_length=...).episode_length_s, 6.0)

    def test_environment_value_overrides(self):
        self.assertEqual(_apply(environment={"episode_length_s": 12.0}, config_episode_length=None).episode_length_s, 12.0)

    def test_config_fallback_overrides_when_environment_lacks_key(self):
        self.assertEqual(_apply(environment=None, config_episode_length=10).episode_length_s, 10.0)

    def test_explicit_20_is_distinguishable_from_default(self):
        # 被否决方案①（「≠20 才应用」）的对照：显式 20 必须照常覆盖 6s
        self.assertEqual(_apply(environment={"episode_length_s": 20.0}, config_episode_length=None).episode_length_s, 20.0)

    def test_num_envs_override_unchanged(self):
        # 相邻的 num_envs 是运行层参数（请求默认合法），保持硬默认覆盖——确认未被本次改动波及
        env_cfg = _apply(environment={"num_envs": 64}, config_episode_length=None)
        self.assertEqual(env_cfg.scene.num_envs, 64)


if __name__ == "__main__":
    unittest.main()
