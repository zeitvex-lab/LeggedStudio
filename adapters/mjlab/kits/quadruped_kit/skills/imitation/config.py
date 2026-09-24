"""Imitation（AMP）技能的族级环境/运行器工厂。

来源：`go2_skills/amp_dreamwaq/config.py`。族级化后的口径：

* **宿主是参数**：AMP 是叠在速度跟踪任务上的风格先验。族级层只负责
  "AMP 项"（判别器状态观测 / 后腿髋限位 / 终止态记录器）与 AMP 算法接线；
  宿主环境（go2 = DreamWaQ，go1 = 它的 rough velocity）由机型侧传入
  `host_env_fn`，宿主的源配方差异（命令采样、奖励权重、事件范围）由机型侧以
  `host_delta` 传入 —— 技能层不认识任何机型；
* **AMP 项参数来自契约**：判别器状态的关节序 = `binding.joint_order`，
  后腿髋关节名 = `binding.joint_names("hip_abduction", legs=binding.rear_legs)`
  （两者都不写死机型名/数值）；
* **专家数据是族级资源**：`motion_root` 由调用方给（试点：go1 复用 go2 的
  LLoco 数据，见 go1 侧模块注释）。

go2 的薄委托（`go2_skills/amp_dreamwaq/config.py`）保持入口名不变；
普通 PPO 宿主（go1）用本模块的 `make_runner_cfg`（算法类 = `rl.AmpPPO`）。
"""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Callable

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.managers import (
    ObservationGroupCfg,
    ObservationTermCfg,
    RecorderTermCfg,
    RewardTermCfg,
)
from mjlab.rl import RslRlOnPolicyRunnerCfg

from ..binding import QuadrupedSkillBinding
from ..mdp import rl as shared_rl
from . import mdp as amp_mdp
from .profile import AmpPpoAlgorithmCfg, AmpProfile

#: 普通 PPO 宿主的族级 AMP 算法类（rsl_rl 按 `class_name` 解析）。
DEFAULT_ALGORITHM_CLASS_NAME = (
    "adapters.mjlab.kits.quadruped_kit.skills.imitation.rl:AmpPPO"
)


def apply_amp_terms(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding, profile: AmpProfile
) -> None:
    """把 AMP 项装进宿主 cfg（族级唯一实现；键名/权重与源配方一致）。"""
    joint_order = tuple(binding.joint_order)
    params = {"joint_order": joint_order, "sensor_name": profile.terrain_sensor}
    cfg.observations["amp"] = ObservationGroupCfg(
        terms={"state": ObservationTermCfg(func=amp_mdp.amp_state, params=params)},
        enable_corruption=False,
    )
    cfg.rewards["rear_hip_limit"] = RewardTermCfg(
        func=amp_mdp.rear_hip_limit,
        weight=profile.rear_hip_limit_weight,
        params={
            "joint_names": binding.joint_names(
                "hip_abduction", legs=binding.rear_legs
            ),
            "bound": profile.rear_hip_limit_bound,
        },
    )
    cfg.recorders["amp_terminal_state"] = RecorderTermCfg(
        func=amp_mdp.AmpTerminalStateRecorder, params=dict(params)
    )


def make_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: AmpProfile,
    *,
    host_env_fn: Callable[..., ManagerBasedRlEnvCfg],
    host_delta: Callable[[ManagerBasedRlEnvCfg, QuadrupedSkillBinding, AmpProfile], None]
    | None = None,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """宿主 cfg + 族级 AMP 增量（源口径：先深拷宿主，再逐项覆盖）。"""
    cfg = deepcopy(host_env_fn(play=play))
    apply_amp_terms(cfg, binding, profile)
    if host_delta is not None:
        host_delta(cfg, binding, profile)
    return cfg


def make_runner_cfg(
    binding: QuadrupedSkillBinding,
    profile: AmpProfile,
    *,
    motion_root: str,
    algorithm_class_name: str = DEFAULT_ALGORITHM_CLASS_NAME,
) -> RslRlOnPolicyRunnerCfg:
    """族级 AMP runner：源 PPO 超参 + AMP 侧输入（运动目录/关节序走配置）。"""
    cfg = shared_rl.make_ppo_runner_cfg(
        profile.experiment_name,
        max_iterations=profile.max_iterations,
        save_interval=500,
    )
    cfg.seed = 1
    cfg.clip_actions = 100.0
    base = dict(vars(cfg.algorithm))
    base.pop("class_name", None)
    cfg.algorithm = AmpPpoAlgorithmCfg(
        **base,
        amp_motion_root=str(motion_root),
        amp_joint_order=tuple(binding.joint_order),
        amp_motion_dt=profile.motion_dt,
        amp_replay_buffer_size=profile.replay_buffer_size,
        amp_num_preload_transitions=profile.num_preload_transitions,
        amp_reward_coef=profile.reward_coef,
        amp_discr_hidden_dims=profile.discr_hidden_dims,
        min_normalized_std=profile.min_normalized_std,
    )
    cfg.algorithm.class_name = algorithm_class_name
    return cfg
