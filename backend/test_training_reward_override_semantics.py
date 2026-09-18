"""MECH-2 裁决 A「任务真值优先」：reward_overrides=true 只透传**显式** reward_scales。

背景（2026-09-18 三十轮塑形实验取证，tools/baselines/reward_shaping_experiments.json
§mechanism_findings MECH-2）：请求带 ``reward_scales + reward_overrides=true`` 时，
resolve_recipe 的通用任务分支（adapters/mjlab/recipe_registry.py，``get_reward_preset``
+ ``update``）会把通用 preset（registry/rewards/presets.json：track_angular_velocity=0.5、
body_orientation_l2=-2.0 等）整表并进 recipe；worker（adapters/mjlab/native_worker.py
``apply_training_recipe``）在包 profile 模式（preserve_profile=True）下曾把这张
preset 全表 setattr 进 env_cfg —— go2 任务真值 track_angular_velocity=2.0 /
upright=+1.0（body_orientation_l2 经别名命中 upright）被通用值 0.5 / -2.0 静默顶掉，
任何带 reward_scales 的实验都在"测一个被偷换的任务"。

裁决（详见 native_worker.apply_training_recipe 处注释）：**A 任务真值优先** ——
包声明了自己任务时，通用 preset 只是通用任务的缺省而非权威；reward_overrides=true
只允许请求**显式列出**的 reward_scales 覆盖包任务，其余项一律保留任务真值。
否决 B（显式钉住要求/前端配合）：把复杂度推给调用方，漏列即踩坑，且 A 无技术障碍。

钉住五件事（任务清单 MECH-2 测试要求）：

1. go2 场景回归：reward_scales={track_linear_velocity: 4.0} + reward_overrides=true
   ⇒ track_angular_velocity 仍是任务真值 2.0、upright 仍是 +1.0，显式项照常生效；
2. 显式 reward_scales 项照常覆盖（含别名键 orientation→upright）；
3. 默认路径逐字节同旧：resolve_recipe 无 reward_scales 时奖励表 == presets.json
   原表；worker preserve_profile 无 overrides 时全表丢弃；worker 通用路径照旧全表应用；
4. U9 包扩展豁免路径不受影响（lite3-velocity 奖励表仍只透传显式项）;
5. 两条合并道都测：合并点 1（resolve_recipe 通用分支，preset 照旧并入 recipe ——
   它对通用任务就是任务定义， Worker 侧守卫兜住 profile 场景）与合并点 2
   （apply_training_recipe，本次修复处）串成生产链路验证。

纯控制面测试：不 import mjlab/torch（native_worker 顶层仅 stdlib，控制面 venv 可导入）。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.mjlab.native_worker import apply_training_recipe  # noqa: E402
from adapters.mjlab.recipe_registry import resolve_recipe  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESETS = json.loads(
    (REPO_ROOT / "registry" / "rewards" / "presets.json").read_text(encoding="utf-8-sig")
)["presets"]


def _go2_truth_env_cfg():
    """go2-velocity-flat 任务真值的最小镜像（官方 mjlab 形态词表 + 真值权重）。"""
    return SimpleNamespace(
        episode_length_s=20.0,
        scene=SimpleNamespace(num_envs=64, terrain=None),
        rewards={
            "track_linear_velocity": SimpleNamespace(weight=2.0, params={}),
            "track_angular_velocity": SimpleNamespace(weight=2.0, params={}),
            "upright": SimpleNamespace(weight=1.0, params={}),
            "joint_torques_l2": SimpleNamespace(weight=-0.001, params={}),
        },
        commands={},
    )


def _generic_env_cfg():
    """通用任务（generic_task_builder 用 recipe 建任务）的最小镜像：词表同 preset 键。"""
    return SimpleNamespace(
        episode_length_s=20.0,
        scene=SimpleNamespace(num_envs=64, terrain=None),
        rewards={
            name: SimpleNamespace(weight=999.0, params={})
            for name in PRESETS["forward_walk"]
        },
        commands={},
    )


def _recipe_dump(**request_overrides) -> dict:
    """走真实 resolve_recipe（合并点 1），产出 worker 消费的 resolved_recipe 形状。"""
    payload = {"task_name": "forward_walk", "num_envs": 64}
    payload.update(request_overrides)
    return resolve_recipe(payload).model_dump(mode="json")


def _apply(env_cfg, config: dict, *, preserve_profile: bool):
    rl_cfg = SimpleNamespace()  # 无 algorithm/num_steps_per_env attr → 算法段全跳过
    return apply_training_recipe(env_cfg, rl_cfg, config, preserve_profile=preserve_profile)


class Mech2TaskTruthPriorityTest(unittest.TestCase):
    """① MECH-2 直接回归：profile + reward_overrides=true 下 preset 不得涌入任务真值。"""

    def test_preset_does_not_clobber_go2_task_truth(self):
        # 生产链路：resolve_recipe 通用分支照旧把 preset 并进 recipe（track_ang=0.5、
        # body_orientation_l2=-2.0），叠加显式 track_linear_velocity=4.0。
        resolved = _recipe_dump(reward_scales={"track_linear_velocity": 4.0})
        self.assertEqual(resolved["reward_scales"]["track_angular_velocity"], 0.5)
        self.assertEqual(resolved["reward_scales"]["body_orientation_l2"], -2.0)

        env_cfg = _go2_truth_env_cfg()
        report = _apply(
            env_cfg,
            {"resolved_recipe": resolved, "reward_overrides": True,
             "reward_scales": {"track_linear_velocity": 4.0}},
            preserve_profile=True,
        )
        # 任务真值不动（MECH-2 的直接回归断言）
        self.assertEqual(env_cfg.rewards["track_angular_velocity"].weight, 2.0)
        self.assertEqual(env_cfg.rewards["upright"].weight, 1.0)
        self.assertEqual(env_cfg.rewards["joint_torques_l2"].weight, -0.001)
        # 显式项照常生效
        self.assertEqual(env_cfg.rewards["track_linear_velocity"].weight, 4.0)
        # 任务词表不被增删（preset 独有项 unmatched 跳过，不造新 term）
        self.assertEqual(
            set(env_cfg.rewards),
            {"track_linear_velocity", "track_angular_velocity", "upright", "joint_torques_l2"},
        )
        self.assertEqual(report["reward_terms_applied"], 1)

    def test_explicit_only_fallback_without_resolved_recipe(self):
        # 无 resolved_recipe 的直连调用方：config.reward_scales 本就是显式项，语义不变。
        env_cfg = _go2_truth_env_cfg()
        _apply(
            env_cfg,
            {"reward_overrides": True, "reward_scales": {"track_linear_velocity": 4.0}},
            preserve_profile=True,
        )
        self.assertEqual(env_cfg.rewards["track_angular_velocity"].weight, 2.0)
        self.assertEqual(env_cfg.rewards["upright"].weight, 1.0)
        self.assertEqual(env_cfg.rewards["track_linear_velocity"].weight, 4.0)

    def test_none_valued_explicit_scale_is_ignored(self):
        # None = 请求未钉住该项 → 不写权重（任务真值保留），也不再让 float(None) 炸合并。
        env_cfg = _go2_truth_env_cfg()
        _apply(
            env_cfg,
            {"resolved_recipe": {"environment": {}, "reward_scales": {}},
             "reward_overrides": True, "reward_scales": {"upright": None}},
            preserve_profile=True,
        )
        self.assertEqual(env_cfg.rewards["upright"].weight, 1.0)


class ExplicitOverrideStillWorksTest(unittest.TestCase):
    """② 显式 reward_scales 项照常覆盖（那是显式意图，含别名键）。"""

    def test_explicit_canonical_and_alias_keys_override_truth(self):
        resolved = _recipe_dump(
            reward_scales={"track_angular_velocity": 3.0, "orientation": -0.5}
        )
        env_cfg = _go2_truth_env_cfg()
        _apply(
            env_cfg,
            {"resolved_recipe": resolved, "reward_overrides": True,
             "reward_scales": {"track_angular_velocity": 3.0, "orientation": -0.5}},
            preserve_profile=True,
        )
        self.assertEqual(env_cfg.rewards["track_angular_velocity"].weight, 3.0)
        self.assertEqual(env_cfg.rewards["upright"].weight, -0.5)  # orientation 别名 → upright
        # 未钉住项仍留任务真值
        self.assertEqual(env_cfg.rewards["track_linear_velocity"].weight, 2.0)


class DefaultPathUnchangedTest(unittest.TestCase):
    """③ 默认路径逐字节同旧（防行为漂移）：三条既有路径一条不动。"""

    def test_resolve_recipe_default_reward_table_is_preset_verbatim(self):
        # 合并点 1 默认形态：无 reward_scales → recipe 奖励表 == presets.json 原表。
        recipe = resolve_recipe({"task_name": "forward_walk", "num_envs": 64})
        self.assertEqual(recipe.reward_scales, PRESETS["forward_walk"])

    def test_resolve_recipe_with_scales_still_overlays_preset(self):
        # 合并点 1 带 scales 的形态也同旧（preset 并入 + 显式覆盖）——它对通用任务
        # 就是任务定义；profile 场景由合并点 2（worker）守卫。
        recipe = resolve_recipe(
            {"task_name": "forward_walk", "num_envs": 64,
             "reward_scales": {"track_linear_velocity": 4.0}}
        )
        expected = dict(PRESETS["forward_walk"])
        expected["track_linear_velocity"] = 4.0
        self.assertEqual(recipe.reward_scales, expected)

    def test_profile_mode_without_overrides_drops_everything(self):
        # worker 默认路径：reward_overrides 缺省/False → 全表丢弃，任务真值原封不动
        #（连请求带了 reward_scales 也照旧不生效 —— 与修复前语义一致）。
        resolved = _recipe_dump()
        for overrides in (False, None):
            env_cfg = _go2_truth_env_cfg()
            config = {"resolved_recipe": resolved,
                      "reward_scales": {"track_linear_velocity": 4.0}}
            if overrides is not None:
                config["reward_overrides"] = overrides
            _apply(env_cfg, config, preserve_profile=True)
            self.assertEqual(env_cfg.rewards["track_angular_velocity"].weight, 2.0)
            self.assertEqual(env_cfg.rewards["upright"].weight, 1.0)
            self.assertEqual(env_cfg.rewards["track_linear_velocity"].weight, 2.0)

    def test_generic_task_path_still_applies_full_recipe_table(self):
        # 通用任务（preserve_profile=False）：preset 表就是任务定义，照旧全表应用。
        resolved = _recipe_dump()
        env_cfg = _generic_env_cfg()
        _apply(env_cfg, {"resolved_recipe": resolved}, preserve_profile=False)
        for name, weight in PRESETS["forward_walk"].items():
            self.assertEqual(env_cfg.rewards[name].weight, weight)

    def test_generic_worker_fallback_to_config_scales_unchanged(self):
        # 通用路径 + 无 resolved_recipe：照旧回退 config.reward_scales（既有测试
        # adapters/mjlab/test_native_worker_recipe.py 的场景，此处同形锁住）。
        env_cfg = _generic_env_cfg()
        _apply(
            env_cfg,
            {"reward_scales": {"track_linear_velocity": 2.0}},
            preserve_profile=False,
        )
        self.assertEqual(env_cfg.rewards["track_linear_velocity"].weight, 2.0)


class PackageExtensionExemptionRegressionTest(unittest.TestCase):
    """④ U9 包扩展豁免路径不受影响（lite3-velocity 真实内置包数据）。"""

    def test_lite3_with_scales_and_overrides_echoes_explicit_only(self):
        payload = {
            "robot_id": "deeprobotics_lite3",
            "profile_id": "lite3-velocity",
            "task_name": "velocity",
            "algorithm": "PPO",
            "num_envs": 4096,
            "reward_scales": {"action_rate_l2": -0.05},
            "reward_overrides": True,
        }
        recipe = resolve_recipe(payload)
        # 豁免路径本就不并 preset、只透传显式项 —— MECH-2 修复前后一致。
        self.assertEqual(recipe.reward_scales, {"action_rate_l2": -0.05})
        self.assertEqual(recipe.environment["source"], "package-extension")


class MergeChainTest(unittest.TestCase):
    """⑤ 两条合并道串成生产链路：resolve（合并点 1）→ worker（合并点 2）。"""

    def test_full_chain_generic_recipe_into_profile_worker(self):
        # 三十轮实验的原链路（task_name=forward_walk + 包 profile）：合并点 1 照旧，
        # 合并点 2 兜住 —— 最终生效的奖励 = 任务真值 + 显式项。
        resolved = _recipe_dump(reward_scales={"track_linear_velocity": 4.0})
        env_cfg = _go2_truth_env_cfg()
        _apply(
            env_cfg,
            {"resolved_recipe": resolved, "reward_overrides": True,
             "reward_scales": {"track_linear_velocity": 4.0}},
            preserve_profile=True,
        )
        self.assertEqual(env_cfg.rewards["track_linear_velocity"].weight, 4.0)
        self.assertEqual(env_cfg.rewards["track_angular_velocity"].weight, 2.0)
        self.assertEqual(env_cfg.rewards["upright"].weight, 1.0)


if __name__ == "__main__":
    unittest.main()
