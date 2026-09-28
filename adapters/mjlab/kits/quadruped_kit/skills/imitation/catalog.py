"""族级 AMP 技能的**装配表入口**（catalog-facing，2026-09-28 新增）。

`go1_amp`（2026-09-24 第二台试点）验证的组合模式在此上移为族级默认，装配表
`skill_catalog["imitation"]` 指向本模块 —— **新机型 + 标准 MJCF 即可装配 AMP**：

* **宿主** = 族级 velocity 技能的 rough 档环境（AMP 是叠在速度跟踪上的风格先验，
  宿主决定机器人 / 物理 / 速度奖励 —— 与 go1_amp 同一口径）；
* **专家动作** = 族内共享库（go2 包内的 LLoco 数据，motion 注册表已登记）。
  「契约关节序同构 ⇒ 数据可复用」是 go1 试点实证的最省成本路径；**不同构的机型
  在这里 fail-closed**（明确报"需要本机型自己的专家动作"），不静默置换帧序 ——
  判别器按契约序采样专家帧，序不同等于喂错数据。
"""

from __future__ import annotations

from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg

from ..binding import QuadrupedSkillBinding
from ..velocity import config as velocity_config
from ..velocity.profile import VelocityProfile
from . import config as amp_config
from .profile import AmpProfile

#: 共享专家动作库（相对仓库根）：go2 包内 LLoco 数据（13 条 .txt，注册表
#: `registry/motions/index.json` 可查）。沿目录向上找仓库根的解析方式与
#: `go1_amp.shared_amp_motion_root` 相同 —— 对 assets 源树与 workspace 镜像副本一致。
_SHARED_MOTION_RELATIVE = Path(
    "assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2"
    "/assets/motions/go2_amp"
)

#: 该数据集自带的关节序（= go2 契约 `action.joint_order`；与注册表 `dof_layout`
#: 的登记同源）。这是**数据的布局事实**，不是机型知识 —— 换数据集时改这里。
_GO2_MOTION_JOINT_ORDER = (
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
)


def shared_motion_root() -> Path:
    """解析族内共享 AMP 动作目录（沿目录向上找仓库根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _SHARED_MOTION_RELATIVE
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"找不到族内共享 AMP 动作数据（相对仓库根）：{_SHARED_MOTION_RELATIVE}"
    )


def _check_joint_order(binding: QuadrupedSkillBinding) -> None:
    """共享动作库的**同构闸**：契约关节序 ≠ 数据布局 ⇒ 拒绝装配（不静默置换）。"""
    if tuple(binding.joint_order) != _GO2_MOTION_JOINT_ORDER:
        raise ValueError(
            f"{binding.robot_id}: 共享 AMP 专家动作按 go2 关节序布局"
            f"（{_GO2_MOTION_JOINT_ORDER[0]} … {_GO2_MOTION_JOINT_ORDER[-1]}），"
            "与本机契约 action.joint_order 不同构 —— 判别器按契约序采样专家帧，"
            "静默置换帧序等于喂错数据。需要本机型自己的专家动作"
            "（登记进 motion 注册表后扩展本入口），或确认关节序后再复用。"
        )


def make_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: AmpProfile,
    *,
    terrain_profile: str = "rough",
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """velocity(rough) 宿主 + 族级 AMP 增量（入口签名与装配表其它技能一致）。"""
    _check_joint_order(binding)

    def _host_env_fn(*, play: bool = False) -> ManagerBasedRlEnvCfg:
        host_profile = VelocityProfile(
            task_id=f"{profile.task_id}_host" if profile.task_id else "family_amp_host",
            experiment_name=profile.experiment_name or "family_amp",
        )
        return velocity_config.make_env_cfg(
            binding, host_profile, terrain_profile=terrain_profile, play=play
        )

    return amp_config.make_env_cfg(
        binding, profile, host_env_fn=_host_env_fn, play=play
    )


def make_runner_cfg(
    binding: QuadrupedSkillBinding, profile: AmpProfile
):
    """族级 AMP runner：专家动作目录由本入口解析（装配表只声明数据，不写机器路径）。"""
    _check_joint_order(binding)
    return amp_config.make_runner_cfg(
        binding, profile, motion_root=str(shared_motion_root())
    )
