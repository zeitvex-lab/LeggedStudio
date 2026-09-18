"""UniLab 算法插件（HIM / HORA / APPO）单元测试。

来源: adapters/mjlab/algorithms/{him,hora,appo}/ —— 从 UniLab 提取的纯 torch 模块。
覆盖（每算法 >= 3 项）:
  1. 可 import / 可实例化（小尺寸 obs_dim=45 action_dim=12）
  2. 前向输出形状正确
  3. 与标准 PPO 的可区分行为:
     - HIM:  estimator 前向（速度+latent）、update 返回 4 项损失（标准 PPO 无估计器损失）
     - HORA: 共享主干特权 latent 路由（教师特权信息 vs 学生 proprio 历史）
     - APPO: 特权观测路由（actor 45 维 / critic 57 维不同观测）+ V-trace off-policy 修正
"""

from __future__ import annotations

import math
import unittest

try:
    import torch
except ImportError:  # pragma: no cover - control plane environment
    # 控制面（无 torch）下整模块跳过；训练 venv（adapters/mjlab/.venv）下全量运行。
    raise unittest.SkipTest(
        "torch not available; UniLab plugin tests need the training stack"
    )

from adapters.mjlab.algorithms.appo import (
    APPOActor,
    APPOLearner,
    APPOCritic,
    vtrace_advantages,
)
from adapters.mjlab.algorithms.him import (
    HIMActorCritic,
    HIMPPO,
    HIMEstimator,
)
from adapters.mjlab.algorithms.hora import (
    HoraLatentDistiller,
    HoraDistillConfig,
    HoraSharedActorCritic,
    build_hora_ppo,
)

OBS_DIM = 45  # 本体观测（一步）
ACTION_DIM = 12
CRITIC_OBS_DIM = 60  # 特权观测（HIM estimator 需要 >= 48: vel[45:48] + target[3:48]）
PRIV_DIM = 12  # HORA 特权信息
HISTORY = 3  # HIM 观测历史长度 -> actor obs = 135


def _make_him_actor_critic() -> HIMActorCritic:
    torch.manual_seed(0)
    return HIMActorCritic(
        num_actor_obs=OBS_DIM * HISTORY,
        num_critic_obs=CRITIC_OBS_DIM,
        num_one_step_obs=OBS_DIM,
        num_actions=ACTION_DIM,
        actor_hidden_dims=(64, 32),
        critic_hidden_dims=(64, 32),
        estimator={"enc_hidden_dims": (32, 16), "tar_hidden_dims": (32,)},
    )


class HimImportTest(unittest.TestCase):
    def test_import_and_instantiate(self) -> None:
        ac = _make_him_actor_critic()
        self.assertEqual(ac.history_size, HISTORY)
        self.assertEqual(ac.num_one_step_obs, OBS_DIM)
        self.assertEqual(ac.num_actions, ACTION_DIM)
        # HIM 结构特征: actor 输入 = 本步观测 + 估计速度(3) + latent(num_latent)
        first_linear = ac.actor[0]
        self.assertEqual(first_linear.in_features, OBS_DIM + 3 + ac.estimator.num_latent)
        # critic 与 actor 观测不对称
        self.assertEqual(ac.critic[0].in_features, CRITIC_OBS_DIM)

    def test_history_multiple_validation(self) -> None:
        with self.assertRaises(ValueError):
            HIMActorCritic(
                num_actor_obs=OBS_DIM * HISTORY + 1,  # 不是 num_one_step_obs 整数倍
                num_critic_obs=CRITIC_OBS_DIM,
                num_one_step_obs=OBS_DIM,
                num_actions=ACTION_DIM,
            )


class HimForwardTest(unittest.TestCase):
    def test_forward_shapes(self) -> None:
        torch.manual_seed(1)
        ac = _make_him_actor_critic()
        obs_hist = torch.randn(8, OBS_DIM * HISTORY)
        critic_obs = torch.randn(8, CRITIC_OBS_DIM)

        actions = ac.act(obs_hist)
        self.assertEqual(actions.shape, (8, ACTION_DIM))
        values = ac.evaluate(critic_obs)
        self.assertEqual(values.shape, (8, 1))
        log_prob = ac.get_actions_log_prob(actions)
        self.assertEqual(log_prob.shape, (8,))
        inference = ac.act_inference(obs_hist)
        self.assertEqual(inference.shape, (8, ACTION_DIM))

    def test_estimator_forward_and_update(self) -> None:
        """HIM 可区分行为: estimator 前向输出 (vel, latent) 且可独立更新。"""
        torch.manual_seed(2)
        estimator = HIMEstimator(
            temporal_steps=HISTORY,
            num_one_step_obs=OBS_DIM,
            enc_hidden_dims=(32, 16),
            tar_hidden_dims=(32,),
        )
        obs_hist = torch.randn(8, OBS_DIM * HISTORY)
        vel, latent = estimator(obs_hist)
        self.assertEqual(vel.shape, (8, 3))
        self.assertEqual(latent.shape, (8, 16))
        # latent 是 L2 归一化的对比学习嵌入
        self.assertTrue(
            torch.allclose(latent.norm(dim=-1), torch.ones(8), atol=1e-5)
        )
        next_critic_obs = torch.randn(8, CRITIC_OBS_DIM)
        est_loss, swap_loss = estimator.update(obs_hist, next_critic_obs)
        self.assertTrue(math.isfinite(est_loss) and est_loss >= 0.0)
        self.assertTrue(math.isfinite(swap_loss) and swap_loss >= 0.0)

    def test_ppo_update_returns_four_losses(self) -> None:
        """HIM update 返回 (value, surrogate, estimation, swap) —— 标准 PPO 没有后两项。"""
        torch.manual_seed(3)
        ac = _make_him_actor_critic()
        ppo = HIMPPO(
            ac,
            num_learning_epochs=1,
            num_mini_batches=2,
            schedule="fixed",
            desired_kl=None,
            device="cpu",
        )
        num_envs, steps = 4, 8
        ppo.init_storage(
            num_envs=num_envs,
            num_transitions_per_env=steps,
            actor_obs_shape=(OBS_DIM * HISTORY,),
            critic_obs_shape=(CRITIC_OBS_DIM,),
            action_shape=(ACTION_DIM,),
        )
        for _ in range(steps):
            obs = torch.randn(num_envs, OBS_DIM * HISTORY)
            critic_obs = torch.randn(num_envs, CRITIC_OBS_DIM)
            ppo.act(obs, critic_obs)
            ppo.process_env_step(
                torch.randn(num_envs, CRITIC_OBS_DIM),
                torch.randn(num_envs),
                torch.zeros(num_envs),
                {},
            )
        ppo.compute_returns(torch.randn(num_envs, CRITIC_OBS_DIM))
        losses = ppo.update()
        self.assertEqual(len(losses), 4)
        for value in losses:
            self.assertTrue(math.isfinite(value))


class HoraImportTest(unittest.TestCase):
    def test_import_and_instantiate(self) -> None:
        torch.manual_seed(4)
        shared = HoraSharedActorCritic(
            obs_dim=OBS_DIM,
            action_dim=ACTION_DIM,
            priv_info_dim=PRIV_DIM,
            actor_hidden_dims=(64, 32),
            priv_mlp_hidden_dims=(32, 8),
            priv_info_embed_dim=8,
        )
        # HORA 结构特征: 共享 trunk 输入 = obs + 特权 embed
        self.assertEqual(shared.trunk.net[0].in_features, OBS_DIM + 8)
        self.assertEqual(shared.mu_head.out_features, ACTION_DIM)
        self.assertEqual(shared.value_head.out_features, 1)


class HoraForwardTest(unittest.TestCase):
    def _make_shared(self, student: bool = False) -> HoraSharedActorCritic:
        torch.manual_seed(5)
        return HoraSharedActorCritic(
            obs_dim=OBS_DIM,
            action_dim=ACTION_DIM,
            priv_info_dim=PRIV_DIM,
            actor_hidden_dims=(64, 32),
            priv_mlp_hidden_dims=(32, 8),
            priv_info_embed_dim=8,
            use_student_encoder=student,
            proprio_hist_len=30,
            proprio_frame_dim=OBS_DIM,
        )

    def test_forward_shapes_and_tensor_path_consistency(self) -> None:
        shared = self._make_shared()
        obs = {
            "actor": torch.randn(8, OBS_DIM),
            "priv_info": torch.randn(8, PRIV_DIM),
        }
        mean, core = shared.policy_mean(obs, prefer_student=False)
        value, _ = shared.value(obs, prefer_student=False)
        self.assertEqual(mean.shape, (8, ACTION_DIM))
        self.assertEqual(value.shape, (8, 1))
        self.assertEqual(core.trunk_latent.shape, (8, 32))
        self.assertEqual(core.privileged_latent.shape, (8, 8))
        # tensor-only 快捷路径与 dict 路径一致
        mean_tensors = shared.policy_mean_from_tensors(
            obs["actor"], obs["priv_info"], prefer_student=False
        )
        self.assertTrue(torch.allclose(mean, mean_tensors))
        value_tensors = shared.value_from_tensors(
            obs["actor"], obs["priv_info"], prefer_student=False
        )
        self.assertTrue(torch.allclose(value, value_tensors))

    def test_student_vs_teacher_privileged_latent(self) -> None:
        """HORA 可区分行为: 学生路径用 proprio 历史替代特权信息。"""
        shared = self._make_shared(student=True)
        obs = {
            "actor": torch.randn(8, OBS_DIM),
            "priv_info": torch.randn(8, PRIV_DIM),
            "proprio_hist": torch.randn(8, 30, OBS_DIM),
        }
        _, core_teacher = shared.policy_mean(obs, prefer_student=False)
        _, core_student = shared.policy_mean(obs, prefer_student=True)
        # 教师路径 latent 来自特权编码器；学生路径来自时序卷积 —— 数值应不同
        self.assertFalse(
            torch.allclose(core_teacher.privileged_latent, core_student.privileged_latent)
        )
        # 学生 latent 落在 tanh 空间
        self.assertLessEqual(float(core_student.privileged_latent.abs().max()), 1.0 + 1e-6)
        # 关掉 prefer_student 后又回到教师 latent
        _, core_back = shared.policy_mean(obs, prefer_student=False)
        self.assertTrue(
            torch.allclose(core_teacher.privileged_latent, core_back.privileged_latent)
        )

    def test_ppo_update_runs_with_shared_backbone(self) -> None:
        """build_hora_ppo 装配 -> rollout -> update; actor/critic 共享同一主干对象。"""
        ppo = build_hora_ppo(
            obs_dim=OBS_DIM,
            action_dim=ACTION_DIM,
            priv_info_dim=PRIV_DIM,
            num_envs=4,
            num_steps_per_env=8,
            actor_cfg={
                "hidden_dims": (64, 32),
                "priv_mlp_hidden_dims": (32, 8),
                "priv_info_embed_dim": 8,
            },
            algorithm_cfg={
                "num_learning_epochs": 1,
                "num_mini_batches": 2,
                "schedule": "fixed",
                "desired_kl": None,
            },
        )
        # 共享主干: actor 与 critic 指向同一个 HoraSharedActorCritic
        self.assertIs(ppo.actor.shared, ppo.critic.shared)
        for _ in range(8):
            obs = {
                "actor": torch.randn(4, OBS_DIM),
                "priv_info": torch.randn(4, PRIV_DIM),
            }
            ppo.act(obs)
            ppo.process_env_step(obs, torch.randn(4), torch.zeros(4), {})
        ppo.compute_returns(
            {"actor": torch.randn(4, OBS_DIM), "priv_info": torch.randn(4, PRIV_DIM)}
        )
        metrics = ppo.update()
        self.assertEqual(set(metrics), {"value", "surrogate", "entropy"})
        for value in metrics.values():
            self.assertTrue(math.isfinite(value))

    def test_latent_distiller_alignment(self) -> None:
        shared = self._make_shared(student=True)
        distiller = HoraLatentDistiller(shared, HoraDistillConfig(learning_rate=1e-3))
        priv = torch.randn(16, PRIV_DIM)
        hist = torch.randn(16, 30, OBS_DIM)
        loss_first = distiller.update(priv, hist)
        loss_second = distiller.update(priv, hist)
        self.assertTrue(math.isfinite(loss_first))
        # 同一批数据上重复对齐，损失应下降
        self.assertLess(loss_second, loss_first)

    def test_unimplemented_extensions_raise(self) -> None:
        """RND / symmetry / multi-GPU 明确报未实现（诚实标注）。"""
        from adapters.mjlab.algorithms.hora import HoraPPO, HoraActorModel, HoraCriticModel
        from adapters.mjlab.algorithms.hora import HoraRolloutStorage

        shared = self._make_shared()
        dummy_obs = {"actor": torch.zeros(1, OBS_DIM), "priv_info": torch.zeros(1, PRIV_DIM)}
        actor = HoraActorModel(dummy_obs, shared_model=shared)
        critic = HoraCriticModel(dummy_obs, shared_model=shared)
        storage = HoraRolloutStorage(2, 4, {"actor": (OBS_DIM,), "priv_info": (PRIV_DIM,)}, ACTION_DIM)
        for kwargs in (
            {"rnd_cfg": {"learning_rate": 1e-3}},
            {"symmetry_cfg": {"use_data_augmentation": True}},
            {"multi_gpu_cfg": {"global_rank": 0, "world_size": 2}},
        ):
            with self.assertRaises(NotImplementedError):
                HoraPPO(actor, critic, storage, **kwargs)


class AppoImportTest(unittest.TestCase):
    def test_import_and_asymmetric_dims(self) -> None:
        """APPO 可区分行为: actor/critic 观测维度不同（非对称 actor-critic）。"""
        torch.manual_seed(6)
        actor = APPOActor(obs_dim=OBS_DIM, action_dim=ACTION_DIM, hidden_dims=(64, 32))
        critic = APPOCritic(obs_dim=OBS_DIM + PRIV_DIM, hidden_dims=(64, 32))
        self.assertEqual(actor.mlp[0].in_features, OBS_DIM)
        self.assertEqual(critic.mlp[0].in_features, OBS_DIM + PRIV_DIM)
        action = actor(torch.randn(8, OBS_DIM), stochastic_output=True)
        self.assertEqual(action.shape, (8, ACTION_DIM))
        value = critic(torch.randn(8, OBS_DIM + PRIV_DIM))
        self.assertEqual(value.shape, (8,))

    def test_deepcopy_actor_after_forward(self) -> None:
        """target 网络构造依赖 deepcopy —— 前向之后也必须可拷贝。"""
        import copy

        actor = APPOActor(obs_dim=OBS_DIM, action_dim=ACTION_DIM, hidden_dims=(64, 32))
        actor(torch.randn(4, OBS_DIM), stochastic_output=True)
        clone = copy.deepcopy(actor)
        out = clone(torch.randn(4, OBS_DIM))
        self.assertEqual(out.shape, (4, ACTION_DIM))


class AppoVtraceTest(unittest.TestCase):
    def test_on_policy_vtrace_equals_discounted_returns(self) -> None:
        """behavior == target（rho=1）时 V-trace 退化为带 bootstrap 的折扣回报。"""
        torch.manual_seed(7)
        T, N, gamma = 5, 3, 0.9
        log_probs = torch.randn(T, N)
        rewards = torch.randn(T, N)
        values = torch.randn(T, N)
        bootstrap = torch.randn(N)
        dones = torch.zeros(T, N)

        vs, advantages = vtrace_advantages(
            behavior_log_probs=log_probs,
            target_log_probs=log_probs,  # on-policy: rho = 1
            rewards=rewards,
            values=values,
            bootstrap_values=bootstrap,
            dones=dones,
            gamma=gamma,
            clip_rho=1.0,
            clip_c=1.0,
        )
        # 手工计算折扣回报（无 done，bootstrap V(s_T)）
        expected = torch.zeros(T, N)
        acc = bootstrap.clone()
        for t in range(T - 1, -1, -1):
            acc = rewards[t] + gamma * acc
            expected[t] = acc
        self.assertTrue(torch.allclose(vs, expected, atol=1e-5))
        # on-policy 时 advantage = r + gamma*vs_{t+1} - v_t（TD 误差）
        next_vs = torch.cat([vs[1:], bootstrap.unsqueeze(0)], dim=0)
        expected_adv = rewards + gamma * next_vs - values
        self.assertTrue(torch.allclose(advantages, expected_adv, atol=1e-5))

    def test_offpolicy_correction_changes_targets(self) -> None:
        """target != behavior 时 rho 裁剪应改变 V-trace 目标（off-policy 修正）。"""
        torch.manual_seed(8)
        T, N = 4, 3
        shared = dict(
            rewards=torch.randn(T, N),
            values=torch.randn(T, N),
            bootstrap_values=torch.randn(N),
            dones=torch.zeros(T, N),
            gamma=0.99,
        )
        behavior = torch.randn(T, N)
        vs_on, adv_on = vtrace_advantages(
            behavior, behavior.clone(), clip_rho=1.0, clip_c=1.0, **shared
        )
        # rho > 1 会被 clip_rho=1 截平（与 on-policy 等价）；rho < 1 保留修正。
        # 用 target < behavior 得到 rho = exp(-2) < 1，V-trace 目标应实际改变。
        vs_off, adv_off = vtrace_advantages(
            behavior, behavior - 2.0, clip_rho=1.0, clip_c=1.0, **shared
        )
        self.assertFalse(torch.allclose(vs_on, vs_off))
        self.assertFalse(torch.allclose(adv_on, adv_off))


class AppoLearnerTest(unittest.TestCase):
    def _make_learner(self) -> APPOLearner:
        torch.manual_seed(9)
        actor = APPOActor(obs_dim=OBS_DIM, action_dim=ACTION_DIM, hidden_dims=(64, 32))
        critic = APPOCritic(obs_dim=OBS_DIM + PRIV_DIM, hidden_dims=(64, 32))
        return APPOLearner(
            actor,
            critic,
            num_learning_epochs=1,
            num_mini_batches=2,
            schedule="adaptive",
            desired_kl=0.01,
            device="cpu",
        )

    @staticmethod
    def _make_batch(T: int = 6, N: int = 4) -> dict:
        torch.manual_seed(10)
        return {
            "observations": torch.randn(T, N, OBS_DIM),
            "critic": torch.randn(T, N, OBS_DIM + PRIV_DIM),
            "rewards": torch.randn(T, N),
            "dones": torch.zeros(T, N),
            "last_obs": torch.randn(N, OBS_DIM),
            "last_critic": torch.randn(N, OBS_DIM + PRIV_DIM),
            "actions_log_prob": torch.randn(T, N) * 0.1,
            "actions": torch.randn(T, N, ACTION_DIM) * 0.3,
        }

    def test_process_batch_privileged_routing(self) -> None:
        """APPO 可区分行为: 特权观测只进 critic，本体观测只进 actor/target。"""
        learner = self._make_learner()
        T, N = 6, 4
        batch = self._make_batch(T, N)
        batch = learner.process_batch(batch)
        # critic 吃的是 57 维特权观测
        self.assertEqual(batch["_critic_obs_flat"].shape, (T * N, OBS_DIM + PRIV_DIM))
        # value/advantage/returns 是 [T, N]
        for key in ("values", "advantages", "returns", "target_log_probs"):
            self.assertEqual(batch[key].shape, (T, N))
        # target actor 的 mu/sigma 来自 45 维本体观测路径
        self.assertEqual(batch["_old_mu"].shape, (T * N, ACTION_DIM))
        self.assertEqual(batch["_old_sigma"].shape, (T * N, ACTION_DIM))
        # vtrace 诊断指标存在
        self.assertIn("vtrace/rho_clip_fraction", batch["_appo_process_metrics"])

    def test_update_runs_and_metrics(self) -> None:
        learner = self._make_learner()
        batch = learner.process_batch(self._make_batch())
        metrics = learner.update(batch)
        for key in (
            "surrogate_loss",
            "value_loss",
            "entropy",
            "optim/learning_rate",
            "ppo/clip_fraction",
            "appo/updates_executed",
        ):
            self.assertIn(key, metrics)
            self.assertTrue(math.isfinite(metrics[key]))
        self.assertEqual(metrics["appo/updates_executed"], 2.0)

    def test_target_network_soft_update(self) -> None:
        """target = tau * current + (1 - tau) * old_target 的精确软更新。"""
        learner = self._make_learner()
        learner.tau = 0.5
        param = next(learner.actor.parameters())
        target_param = next(learner.target_actor.parameters())
        old_actor = param.detach().clone()
        old_target = target_param.detach().clone()
        learner.update_target_network()
        expected = 0.5 * old_actor + 0.5 * old_target
        self.assertTrue(torch.allclose(target_param.detach(), expected, atol=1e-6))


if __name__ == "__main__":
    unittest.main()
