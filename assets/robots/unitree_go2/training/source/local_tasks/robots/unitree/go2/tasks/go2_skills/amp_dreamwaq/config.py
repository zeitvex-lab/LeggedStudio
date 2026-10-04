"""Go2 侧薄委托：AMP-DreamWaQ 环境/运行器（族级实现在 `quadruped_kit/skills/imitation/`）。

## 这个文件为什么这么短

族级 imitation 技能层承接了 AMP 的全部实现：判别器状态观测、后腿髋限位、
终止态记录器、判别器/回放/归一化、AMP 奖励整形与更新次序、专家动作加载器。
本文件只留三样**机型/宿主事实**：

1. **入口符号**（`make_amp_dreamwaq_env_cfg` / `make_amp_dreamwaq_runner_cfg`）——
   profile 的 `entrypoints` 指向的就是它们，迁移没有动路径；
2. **宿主**：`host_env_fn=make_dreamwaq_env_cfg`（DreamWaQ 环境，仍是 go2 的包内实现）；
3. **宿主的源配方差异**（`_host_delta`）：命令采样器换成 AMP 版、奖励权重/目标高、
   base_mass 范围、0.01 关节位置观测噪声、`alive`/`termination` 两项 MuJoCo 后端适配 ——
   这些是**源配方数字**（`AmpDreamWaQAlgorithmCfg` 同源），不是族级 AMP 定义，
   故留在机型侧并逐条取证。

AMP 算法类仍解析到本包的 `rl:AmpDreamWaQPPO`（族级混入 + DreamWaQ 宿主）。
"""

from __future__ import annotations

from dataclasses import dataclass

from mjlab.envs import mdp as env_mdp
from mjlab.managers import RewardTermCfg
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

from adapters.mjlab.kits.quadruped_kit.skills.imitation import config as kit_amp

from ..binding import GO2
from ..dreamwaq.config import make_dreamwaq_env_cfg, make_dreamwaq_runner_cfg
from ..shared import rl as shared_rl
from ..upstream.rl import RslRlPpoWithSymmetryAlgorithmCfg
from . import commands
from .profile import GO2_AMP_DREAMWAQ


@dataclass
class AmpDreamWaQAlgorithmCfg(RslRlPpoWithSymmetryAlgorithmCfg):
  amp_replay_buffer_size: int = 1_000_000
  amp_num_preload_transitions: int = 2_000_000
  amp_reward_coef: float = .5
  amp_discr_hidden_dims: tuple[int, ...] = (1024, 512)
  min_normalized_std: float = .05


def _host_delta(cfg, binding, profile) -> None:
  """Go2 AMP-DreamWaQ 的宿主级源配方差异（逐条对照源 Gym 任务）。"""
  del binding, profile
  # Source AMP differs from DreamWaQ in lateral command range, task rewards,
  # base-mass range and 0.01 joint-position observation noise.
  cfg.commands["twist"] = commands.AmpDreamWaQVelocityCommandCfg(
    entity_name="robot", resampling_time_range=(10., 10.),
    rel_standing_envs=0., rel_heading_envs=1., heading_command=True,
    heading_control_stiffness=.5, debug_vis=True,
    ranges=UniformVelocityCommandCfg.Ranges(
      lin_vel_x=(-1., 1.), lin_vel_y=(-.6, .6), ang_vel_z=(-1., 1.),
      heading=(-3.14, 3.14),
    ),
  )
  cfg.events["base_mass"].params["ranges"] = (-1., 3.)
  cfg.rewards["tracking_lin_vel"].weight = 1.
  cfg.rewards["tracking_ang_vel"].weight = .5
  cfg.rewards["lin_vel_z"].weight = -2.
  cfg.rewards["torques"].weight = -1.e-5
  cfg.rewards["base_height"].params["target_height"] = .35
  # In MuJoCo the random AMP policy can terminate after ~15 steps and avoid
  # the source task's net-negative shaping return.  The Gym task assigns zero
  # terminal cost and happens not to fall into this basin under PhysX.  These
  # two backend-adaptation terms remove that early-termination optimum; they
  # do not alter the target pose, commands, observations, or AMP objective.
  # Keep a small backend survival bridge: the terminal cost prevents the
  # early-fall loophole, while a large per-step alive bonus creates a static
  # policy that ignores velocity commands in MuJoCo.
  cfg.rewards["alive"] = RewardTermCfg(func=env_mdp.is_alive, weight=.1)
  cfg.rewards["termination"] = RewardTermCfg(
    func=shared_rl.terminal_cost, weight=-5.
  )
  cfg.observations["actor"].terms["frame"].params["joint_position_noise"] = .01


def make_amp_dreamwaq_env_cfg(*, play: bool = False):
  """族级 imitation 技能 + go2/DreamWaQ 宿主（入口签名与族级工厂一致）。"""
  return kit_amp.make_env_cfg(
    GO2,
    GO2_AMP_DREAMWAQ,
    host_env_fn=make_dreamwaq_env_cfg,
    host_delta=_host_delta,
    play=play,
  )


def make_amp_dreamwaq_runner_cfg():
  # The dedicated AMP PPO class is installed by this task, not the source fork.
  cfg = make_dreamwaq_runner_cfg()
  cfg.experiment_name = GO2_AMP_DREAMWAQ.experiment_name
  cfg.max_iterations = 20_000
  cfg.save_interval = 500
  cfg.algorithm = AmpDreamWaQAlgorithmCfg(**vars(cfg.algorithm))
  # 本地 AmpDreamWaQPPO（AmpPpoMixin 源口径）仍为唯一可用实现——插件的 amp 变体
  # 尚未上移该数据流（2026-10-04 冒烟实证接口不兼容），接管前本处 class_name 保留
  # 并列入 runner_classname_rule 的显式豁免清单（具名债务，非静默例外）。
  cfg.algorithm.class_name = "local_tasks.robots.unitree.go2.tasks.go2_skills.amp_dreamwaq.rl:AmpDreamWaQPPO"
  return cfg
