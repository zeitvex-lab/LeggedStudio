"""Go2 源兼容任务工厂的共享助手（薄 shim）。

族级实现：`adapters/mjlab/kits/quadruped_kit/skills/velocity/config.py` 的三个源配方
收尾（观测裁剪 / 共享摩擦采样 / 帧噪声向量）。本模块按**原函数名**再导出，
包内未上移的任务（trot / 特技与站姿）与既有调用方一律不动。

只留在包内的一样：`_go2_source_47_noise_cfg` —— 47 维相位帧的逐段噪声幅度是
**特技/站姿任务的帧布局**（相位 5 + 角速度 3 + 欧拉 3 + 关节 3×12），
不属速度跟踪族的时间口径，未上移。
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.utils.noise.noise_cfg import UniformNoiseCfg

from adapters.mjlab.kits.quadruped_kit.skills.velocity.config import (
  apply_source_geom_friction as _go2_source_geom_friction,
)
from adapters.mjlab.kits.quadruped_kit.skills.velocity.config import (
  apply_source_observation_clipping as _go2_source_observation_clipping,
)
from adapters.mjlab.kits.quadruped_kit.skills.velocity.config import (
  source_frame_noise,
)

#: 47 维相位帧的关节数（特技/站姿任务的帧布局常量）。
_SOURCE_47_JOINT_COUNT = 12


def _go2_source_noise_cfg(
  *, command_first: bool, dof_pos_noise: float = 0.01, ang_vel_noise: float = 0.2
) -> UniformNoiseCfg:
  """返回 45 维帧的源噪声向量（族级实现；本机型关节数 = 12）。"""
  return source_frame_noise(
    joint_count=_SOURCE_47_JOINT_COUNT,
    command_first=command_first,
    dof_pos_noise=dof_pos_noise,
    ang_vel_noise=ang_vel_noise,
  )


def _go2_source_47_noise_cfg() -> UniformNoiseCfg:
  """返回相位式 47 维帧的源噪声向量。"""
  values = (
    [0.0] * 5
    + [0.2 * 0.25] * 3
    + [0.1] * 3
    + [0.01] * 12
    + [1.5 * 0.05] * 12
    + [0.0] * 12
  )
  return UniformNoiseCfg(n_min=tuple(-value for value in values), n_max=tuple(values))


__all__ = [
  "_go2_source_47_noise_cfg",
  "_go2_source_geom_friction",
  "_go2_source_noise_cfg",
  "_go2_source_observation_clipping",
  "ManagerBasedRlEnvCfg",
]
