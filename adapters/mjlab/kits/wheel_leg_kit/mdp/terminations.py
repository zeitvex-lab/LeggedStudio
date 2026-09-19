# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：本文件由 b2w_velocity/mdp/{name}.py **逐字上移**
# （== go2w_velocity 同名文件 sha256 一致；m20_velocity 同名文件亦逐字一致）。
# 包侧 mdp/__init__ 改为从本 kit 模块星导入，组合顺序与原 mdp/__init__ 相同。
# ------------------------------------------------------------------------------
from __future__ import annotations

from typing import TYPE_CHECKING

import torch

from mjlab.sensor import ContactSensor

if TYPE_CHECKING:
  from mjlab.envs import ManagerBasedRlEnv


def illegal_contact(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
  sensor: ContactSensor = env.scene[sensor_name]
  assert sensor.data.found is not None
  return torch.any(sensor.data.found, dim=-1)
