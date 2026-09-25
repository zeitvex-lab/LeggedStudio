"""速度跟踪技能的族级 runner（含算法变体的训练循环与 runner 配置工厂）。

来源：`assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2/training/
runner.py`（417 行）与 `training/config.py` 的 `unitree_go2_custom_runner_cfg`。
去机型化改动：

* **策略侧元数据**（ONNX 附带信息）改成可注入件：`policy_metadata_fn`（机型侧给，
  语义是"本机型的部署契约"）；族级类默认不附任何机型元数据；
* **环境变量名**（跳过导出 / 教师 checkpoint）改成类属性；默认值与算法插件的
  `DistillAlgorithmConfig` 声明的一致（`skip_onnx_export_env_var=None` = 不跳）；
* 教师编码器宽度（地形扫描 / 特权块）从 `DEFAULT_DISTILL_CONFIG` 的 `terrain_dim` /
  `privileged_dim` 取（插件自己声明的输入契约），不再写数字；
* runner 配置的**算法侧符号串**（algorithm / actor / critic / distribution 的
  `class_name`）与全部超参走 `VariantRunnerProfile` 数据；
* 关节点数不再写死（checkpoint 归一化宽度检查读 actor 自己的 `actor_dim`）。

源实现的蒸馏循环、checkpoint 兼容处理与 ONNX/recurrent 导出逐项保留。
"""

from __future__ import annotations

import copy
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import torch
import wandb
from mjlab.rl import RslRlOnPolicyRunnerCfg, RslRlVecEnvWrapper
from mjlab.rl.exporter_utils import attach_metadata_to_onnx, get_base_metadata
from mjlab.rl.runner import MjlabOnPolicyRunner
from rsl_rl.modules import EmpiricalNormalization
from torch import nn

from adapters.mjlab.algorithms.common.modules import (
    Go2ClampedGaussianDistribution,
    _mlp,
)
from adapters.mjlab.algorithms.distill.config import DEFAULT_DISTILL_CONFIG
from adapters.mjlab.algorithms.distill.models import StudentActorModel

from .profile import VariantRunnerProfile

#: 策略侧 ONNX 元数据的注入签名：`(actor, *, recurrent=False) -> dict`。
PolicyMetadataFn = Callable[..., dict]


class VelocityOnPolicyRunner(MjlabOnPolicyRunner):
    """速度跟踪族的 on-policy runner（ONNX 导出 + 检查点兼容 + 推理路径）。"""

    env: RslRlVecEnvWrapper

    #: 机型侧注入件：给 ONNX 附上**本机型的部署契约**元数据（无则不加）。
    policy_metadata_fn: PolicyMetadataFn | None = None
    #: 跳过 ONNX 导出的环境变量名（`None` = 不跳；机型侧给老名以保持兼容）。
    skip_onnx_export_env_var: str | None = None

    @staticmethod
    def _checkpoint_actor_state(path: Path) -> dict[str, torch.Tensor]:
        loaded = torch.load(path, map_location="cpu", weights_only=False)
        state = loaded.get("actor_state_dict", loaded.get("model_state_dict", loaded))
        if not isinstance(state, dict):
            raise ValueError(f"Checkpoint has no actor state dictionary: {path}")
        normalized: dict[str, torch.Tensor] = {}
        for key, value in state.items():
            name = key
            if name.startswith("actor_obs_normalizer."):
                name = name.replace("actor_obs_normalizer.", "obs_normalizer.", 1)
            for prefix in ("actor.", "model."):
                if name.startswith(prefix):
                    name = name[len(prefix) :]
            normalized[name] = value
        return normalized

    def _prepare_checkpoint_for_load(self, loaded_dict: dict, path: Path) -> None:
        """在严格加载之前重建 checkpoint 自带的 running 归一化器。

        源并列档位关掉了 actor 归一化，但部分有效 checkpoint（含从旧教师蒸馏出的学生）
        带 rsl_rl 的 running 归一化器。重建它才能严格加载，并且**把该输入变换保留在
        导出的 ONNX 里**。
        """
        super()._prepare_checkpoint_for_load(loaded_dict, path)
        state = loaded_dict.get("actor_state_dict", {})
        if not isinstance(state, dict):
            raise ValueError(f"Checkpoint has no actor state dictionary: {path}")
        normalizer_state = {
            key.removeprefix("obs_normalizer."): value
            for key, value in state.items()
            if key.startswith("obs_normalizer.")
        }
        actor = self.alg.get_policy()
        current_actor_state = actor.state_dict()
        if normalizer_state and not actor.obs_normalizer.state_dict():
            mean = normalizer_state.get("_mean")
            if mean is None or mean.ndim != 2 or mean.shape[0] != 1:
                raise ValueError(f"Checkpoint has an invalid actor normalizer: {path}")
            # 策略宽度：算法层声明的是 `actor_dim`（历史命名保留为回退）。
            actor_dim = getattr(actor, "actor_dim", None)
            if actor_dim is None:
                actor_dim = getattr(actor, "_go2_actor_dim", None)
            if actor_dim is not None and mean.shape[1] != actor_dim:
                raise ValueError(
                    f"Checkpoint actor normalizer width {mean.shape[1]} does not match "
                    f"policy width {actor_dim}: {path}"
                )
            actor.obs_normalizer = EmpiricalNormalization(int(mean.shape[1])).to(self.device)
        # ``min_std`` 是固定的训练档常量而非学习参数。旧 checkpoint 合理地不含它：
        # 只从当前解析出的档位拷这一个已知值，其余张量与缓冲仍走严格加载。
        min_std_key = "distribution.min_std"
        if min_std_key not in state and min_std_key in current_actor_state:
            state[min_std_key] = current_actor_state[min_std_key]

    def get_inference_policy(self, device: str | None = None) -> Any:
        """返回源推理路径（条件策略：播放一律走学生分支）。"""
        self.alg.eval_mode()
        actor = self.alg.get_policy().to(device)
        if getattr(actor, "latent_kind", None) == "cts":
            # 源 CTS 同时训练特权教师与 history-only 学生两份，但播放总是调
            # ``act_inference``，因此每个环境都用蒸馏后的学生。
            setattr(actor, "use_student", True)  # noqa: B010
        return actor

    def save(self, path: str, infos=None):
        super().save(path, infos)
        # 大规模并行环境在迭代 0 导出 ONNX 可能耗尽 CUDA graph 工作区。验证脚本可以
        # 关掉导出而保留常规 .pt；独立的 ONNX 冒烟/导出仍可用（不设该变量）。
        env_var = self.skip_onnx_export_env_var
        if env_var and os.environ.get(env_var, "").lower() in {"1", "true", "yes"}:
            return
        policy_dir, filename, onnx_path = self._get_export_paths(path)
        try:
            self.export_policy_to_onnx(str(policy_dir), filename)
            run_name = (
                wandb.run.name or "local"
                if self.logger.logger_type in ("wandb", "WandbLogWriter") and wandb.run
                else "local"
            )  # type: ignore[assignment]
            metadata = get_base_metadata(self.env.unwrapped, run_name)
            if self.policy_metadata_fn is not None:
                metadata.update(self.policy_metadata_fn(self.alg.get_policy()))
            attach_metadata_to_onnx(str(onnx_path), metadata)
            # 学生档还有一份源兼容的循环实现。对 mjlab 调用方保留上面的双输入
            # ONNX，另在它旁边生成可选的 ``obs,h,c`` 伴生文件。
            try:
                recurrent_filename = f"{onnx_path.stem}_recurrent.onnx"
                recurrent_path = policy_dir / recurrent_filename
                if self.export_recurrent_policy_to_onnx(str(policy_dir), recurrent_filename):
                    recurrent_metadata = dict(metadata)
                    if self.policy_metadata_fn is not None:
                        recurrent_metadata.update(
                            self.policy_metadata_fn(self.alg.get_policy(), recurrent=True)
                        )
                    attach_metadata_to_onnx(str(recurrent_path), recurrent_metadata)
            except Exception as recurrent_error:
                print(
                    f"[WARN] recurrent ONNX export failed (training continues): {recurrent_error}"
                )
            if (
                self.logger.logger_type in ("wandb", "WandbLogWriter")
                and self.cfg["upload_model"]
            ):
                wandb.save(str(onnx_path), base_path=str(policy_dir))
        except Exception as e:
            print(f"[WARN] ONNX export failed (training continues): {e}")


class _RecurrentStudentPolicy:
    """普通 mjlab play 循环用的带状态学生策略。"""

    def __init__(self, actor, env) -> None:
        self.actor = actor
        self.env = env
        self.hidden: tuple[torch.Tensor, torch.Tensor] | None = None

    @torch.no_grad()
    def __call__(self, obs) -> torch.Tensor:
        actor_obs = self.actor.obs_normalizer(obs["actor"])
        batch_size = actor_obs.shape[0]
        if self.hidden is None or self.hidden[0].shape[1] != batch_size:
            shape = (
                self.actor.student_lstm.num_layers,
                batch_size,
                self.actor.student_lstm.hidden_size,
            )
            self.hidden = (actor_obs.new_zeros(shape), actor_obs.new_zeros(shape))
        # mjlab 在暴露新 episode 的首个观测之前已经复位 episode_length_buf，
        # 于是这里能拿到这个 callable 原本看不到的 done 掩码。
        reset = self.env.unwrapped.episode_length_buf == 0
        if torch.any(reset):
            keep = (~reset).view(1, -1, 1)
            self.hidden = tuple(state * keep for state in self.hidden)  # type: ignore[assignment]
        encoded, self.hidden = self.actor.student_lstm(actor_obs[:, None, :], self.hidden)
        features = self.actor.student_head(encoded[:, -1])
        return self.actor.mlp(torch.cat((features, actor_obs), dim=-1))


class VelocityDistillationRunner(VelocityOnPolicyRunner):
    """源兼容的循环学生蒸馏 runner。

    源学生 job **不是** PPO job：冻结已训完的教师、把它的 actor 克隆给学生，然后对
    三层 LSTM 编码器 + 克隆的 actor 优化（对齐教师的隐变量与动作）。复用普通的
    on-policy 采集循环会静默引入 PPO 梯度，并在每个动作处把 LSTM 复位成五帧窗口，
    因此两个学生任务走这条专用学习循环。
    """

    student_actor: StudentActorModel

    #: 教师 checkpoint 的 opt-in 环境变量（默认 = 算法插件声明的名字）。
    teacher_checkpoint_env_var: str = DEFAULT_DISTILL_CONFIG.teacher_checkpoint_env_var

    def __init__(self, env, train_cfg, log_dir=None, device="cpu") -> None:
        super().__init__(env, train_cfg, log_dir, device)
        student_actor = self.alg.get_policy()
        if not isinstance(student_actor, StudentActorModel):
            raise TypeError(
                "VelocityDistillationRunner requires StudentActorModel, got "
                f"{type(student_actor).__name__}"
            )
        self.student_actor = student_actor

        self.teacher_terrain_encoder = _mlp(
            DEFAULT_DISTILL_CONFIG.terrain_dim, 16, (256, 128)
        ).to(self.device)
        self.teacher_privileged_encoder = _mlp(
            DEFAULT_DISTILL_CONFIG.privileged_dim, 16, (128, 64)
        ).to(self.device)
        self.teacher_actor = copy.deepcopy(self.student_actor.mlp).to(self.device)
        self.teacher_obs_normalizer = copy.deepcopy(self.student_actor.obs_normalizer).to(
            self.device
        )
        self._load_teacher_checkpoint()
        # 源 DistillPolicyRunner 从教师 actor 的精确拷贝起步，循环编码器保持随机初始化。
        self.student_actor.mlp.load_state_dict(self.teacher_actor.state_dict())
        self.student_actor.obs_normalizer = copy.deepcopy(self.teacher_obs_normalizer).to(
            self.device
        )
        for module in (
            self.teacher_terrain_encoder,
            self.teacher_privileged_encoder,
            self.teacher_actor,
            self.teacher_obs_normalizer,
        ):
            module.eval()
            for parameter in module.parameters():
                parameter.requires_grad_(False)

        self.distill_optimizer = torch.optim.Adam(
            [
                *self.student_actor.student_lstm.parameters(),
                *self.student_actor.student_head.parameters(),
                *self.student_actor.mlp.parameters(),
            ],
            lr=1e-3,
        )
        # 教师 PPO 算法把这个优化器随普通 actor 状态一起持久化。
        setattr(  # noqa: B010
            self.alg, "student_distill_optimizer", self.distill_optimizer
        )
        self._student_hidden: tuple[torch.Tensor, torch.Tensor] | None = None

    def _load_teacher_checkpoint(self) -> None:
        env_var = self.teacher_checkpoint_env_var
        checkpoint = os.environ.get(env_var) if env_var else None
        if not checkpoint:
            print(
                f"[WARN] TS-Student has no teacher checkpoint; set "
                f"{env_var} for source-compatible distillation."
            )
            return
        path = Path(checkpoint)
        if not path.is_file():
            raise FileNotFoundError(f"{env_var} does not exist: {path}")
        state = self._checkpoint_actor_state(path)

        def select(prefix: str) -> dict[str, torch.Tensor]:
            return {
                key[len(prefix) :]: value
                for key, value in state.items()
                if key.startswith(prefix)
            }

        required = {
            "terrain_encoder.": self.teacher_terrain_encoder,
            "privileged_encoder.": self.teacher_privileged_encoder,
            "mlp.": self.teacher_actor,
        }
        for prefix, module in required.items():
            selected = select(prefix)
            if not selected:
                raise ValueError(f"Teacher checkpoint {path} lacks {prefix[:-1]} weights")
            module.load_state_dict(selected, strict=True)
        normalizer = select("obs_normalizer.")
        if normalizer:
            # 源归一化并列之前生成的 checkpoint 用 rsl_rl 的 running 归一化器。
            # 保留教师那份精确的输入变换，这些 checkpoint 才能继续当蒸馏源；
            # 新的并列档教师用 Identity、没有归一化器状态。
            try:
                self.teacher_obs_normalizer.load_state_dict(normalizer, strict=True)
            except RuntimeError:
                self.teacher_obs_normalizer = EmpiricalNormalization(
                    DEFAULT_DISTILL_CONFIG.actor_dim
                ).to(self.device)
                self.teacher_obs_normalizer.load_state_dict(normalizer, strict=True)

    def _teacher_step(
        self, obs: dict[str, torch.Tensor]
    ) -> tuple[torch.Tensor, torch.Tensor]:
        with torch.no_grad():
            features = torch.cat(
                (
                    self.teacher_terrain_encoder(obs["terrain"]),
                    self.teacher_privileged_encoder(obs["privileged"]),
                ),
                dim=-1,
            )
            actor_obs = self.teacher_obs_normalizer(obs["actor"])
            actions = self.teacher_actor(torch.cat((features, actor_obs), dim=-1))
        return actions, features

    def _student_step(
        self, obs: dict[str, torch.Tensor]
    ) -> tuple[torch.Tensor, torch.Tensor]:
        actor_obs = self.student_actor.obs_normalizer(obs["actor"])
        batch_size = actor_obs.shape[0]
        if self._student_hidden is None:
            shape = (
                self.student_actor.student_lstm.num_layers,
                batch_size,
                self.student_actor.student_lstm.hidden_size,
            )
            self._student_hidden = (
                actor_obs.new_zeros(shape),
                actor_obs.new_zeros(shape),
            )
        encoded, self._student_hidden = self.student_actor.student_lstm(
            actor_obs[:, None, :], self._student_hidden
        )
        features = self.student_actor.student_head(encoded[:, -1])
        actions = self.student_actor.mlp(torch.cat((features, actor_obs), dim=-1))
        return actions, features

    def _reset_student_hidden(self, dones: torch.Tensor) -> None:
        if self._student_hidden is None:
            return
        keep = (~dones.to(torch.bool)).view(1, -1, 1)
        hidden, cell = self._student_hidden
        self._student_hidden = (hidden * keep, cell * keep)

    def learn(
        self, num_learning_iterations: int, init_at_random_ep_len: bool = False
    ) -> None:
        if init_at_random_ep_len:
            self.env.episode_length_buf = torch.randint_like(
                self.env.episode_length_buf, high=int(self.env.max_episode_length)
            )
        obs = self.env.get_observations().to(self.device)
        self.student_actor.train()
        self.logger.init_logging_writer()
        start_it = self.current_learning_iteration
        total_it = start_it + num_learning_iterations
        for it in range(start_it, total_it):
            collect_start = time.time()
            teacher_features: list[torch.Tensor] = []
            student_features: list[torch.Tensor] = []
            teacher_actions: list[torch.Tensor] = []
            student_actions: list[torch.Tensor] = []
            for _ in range(self.cfg["num_steps_per_env"]):
                target_actions, target_features = self._teacher_step(obs)
                actions, features = self._student_step(obs)
                teacher_actions.append(target_actions)
                teacher_features.append(target_features)
                student_actions.append(actions)
                student_features.append(features)
                # 与源的热身一致：第 0 次迭代由教师驱动，之后由学出来的循环学生驱动。
                env_actions = target_actions if it == 0 else actions.detach()
                obs, rewards, dones, extras = self.env.step(env_actions.to(self.env.device))
                obs, rewards, dones = (
                    obs.to(self.device),
                    rewards.to(self.device),
                    dones.to(self.device),
                )
                self._reset_student_hidden(dones)
                self.logger.process_env_step(rewards, dones, extras, None)
            collect_time = time.time() - collect_start

            learn_start = time.time()
            latent_loss = torch.linalg.vector_norm(
                torch.cat(teacher_features).detach() - torch.cat(student_features), dim=-1
            ).mean()
            action_loss = torch.linalg.vector_norm(
                torch.cat(teacher_actions).detach() - torch.cat(student_actions), dim=-1
            ).mean()
            loss = latent_loss + action_loss
            self.distill_optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(
                [
                    *self.student_actor.student_lstm.parameters(),
                    *self.student_actor.student_head.parameters(),
                ],
                1.0,
            )
            nn.utils.clip_grad_norm_(self.student_actor.mlp.parameters(), 1.0)
            self.distill_optimizer.step()
            if self._student_hidden is not None:
                hidden, cell = self._student_hidden
                self._student_hidden = (hidden.detach(), cell.detach())
            learn_time = time.time() - learn_start
            self.current_learning_iteration = it
            self.logger.log(
                it=it,
                start_it=start_it,
                total_it=total_it,
                collect_time=collect_time,
                learn_time=learn_time,
                loss_dict={
                    "ts_latent_distillation": float(latent_loss.detach()),
                    "ts_action_distillation": float(action_loss.detach()),
                },
                learning_rate=self.distill_optimizer.param_groups[0]["lr"],
                action_std=self._action_std(),
                rnd_weight=None,
            )
            if self.logger.writer is not None and it % self.cfg["save_interval"] == 0:
                self.save(os.path.join(self._log_dir(), f"model_{it}.pt"))
        if self.logger.writer is not None:
            self.save(
                os.path.join(self._log_dir(), f"model_{self.current_learning_iteration}.pt")
            )
            self.logger.stop_logging_writer()

    def _action_std(self) -> torch.Tensor:
        distribution = self.student_actor.distribution
        if not isinstance(distribution, Go2ClampedGaussianDistribution):
            raise TypeError("Student actor requires Go2ClampedGaussianDistribution")
        return distribution.std_param.clamp(*distribution.std_range)

    def _log_dir(self) -> str:
        log_dir = self.logger.log_dir
        if log_dir is None:
            raise RuntimeError("Distillation logger has no log directory")
        return str(log_dir)

    def get_inference_policy(self, device: str | None = None) -> Any:
        """返回源学生播放所用的循环路径。"""
        self.alg.eval_mode()
        actor = self.alg.get_policy().to(device)
        return _RecurrentStudentPolicy(actor, self.env)


def make_variant_runner_cfg(
    spec: VariantRunnerProfile,
    *,
    base_runner_cfg: Callable[[], RslRlOnPolicyRunnerCfg],
) -> RslRlOnPolicyRunnerCfg:
    """在机型侧 source-PPO 基座之上装配算法变体的 runner 配置。

    参数化（数据）的是：实验名、PPO 超参（学习率/迭代/保存间隔/种子）、观测归一化
    开关、动作裁剪上限、以及算法/actor/critic/分布四个 `class_name`；
    机制（源并列档"关归一化 + 不裁剪动作 + 换分布 std 下限 + 学生更长 rollout"）在这里。
    """
    cfg = base_runner_cfg()
    cfg.actor.obs_normalization = bool(spec.obs_normalization)
    cfg.critic.obs_normalization = bool(spec.obs_normalization)
    if spec.clip_actions is not None:
        cfg.clip_actions = float(spec.clip_actions)
    cfg.algorithm.learning_rate = float(spec.learning_rate)
    cfg.max_iterations = int(spec.max_iterations)
    cfg.save_interval = int(spec.save_interval)
    cfg.seed = int(spec.seed)
    cfg.algorithm.class_name = spec.algorithm_class
    cfg.actor.class_name = spec.actor_class
    if spec.critic_class is not None:
        cfg.critic.class_name = spec.critic_class
    if spec.num_steps_per_env is not None:
        cfg.num_steps_per_env = int(spec.num_steps_per_env)
    if spec.distribution_class is not None:
        assert cfg.actor.distribution_cfg is not None
        cfg.actor.distribution_cfg["class_name"] = spec.distribution_class
        if spec.min_std is not None:
            cfg.actor.distribution_cfg["min_std"] = tuple(spec.min_std)
    cfg.experiment_name = spec.experiment_name
    return cfg


def make_source_ppo_runner_cfg(
    base: RslRlOnPolicyRunnerCfg,
    *,
    learning_rate: float,
    max_iterations: int,
    save_interval: int,
    seed: int,
    symmetry_func: str | None = None,
) -> RslRlOnPolicyRunnerCfg:
    """在机型基座 runner 之上套「源配方 PPO」档 —— CTS/TS/DreamWaQ/AMP 那一族的共同口径。

    **这是技能机制、不是机型差异**：源策略直接消费环境已 scaled/clipped 的观测，不做
    running 归一化，也不裁动作。原先只写在 `unitree_go2` 的 `training/config.py` 里，
    第二台机型要用就得抄一份 —— 上移后机型侧只交自己的基座与超参。
    """
    base.actor.obs_normalization = False
    base.critic.obs_normalization = False
    base.clip_actions = 100.0
    base.algorithm.learning_rate = float(learning_rate)
    base.max_iterations = int(max_iterations)
    base.save_interval = int(save_interval)
    base.seed = int(seed)
    if symmetry_func is not None:
        base.algorithm.symmetry_cfg = {
            "data_augmentation_func": symmetry_func,
            "use_data_augmentation": False,
            "use_mirror_loss": True,
            "mirror_loss_coeff": 1.0,
        }
    return base


__all__ = [
    "PolicyMetadataFn",
    "VelocityDistillationRunner",
    "VelocityOnPolicyRunner",
    "make_source_ppo_runner_cfg",
    "make_variant_runner_cfg",
]
