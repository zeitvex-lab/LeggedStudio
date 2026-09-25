"""族级技能的奖励原语。

来源：`assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2/mdp/rewards.py`
的 `go2_dof_power_penalty`（逐字上移，只去掉机型名与机型侧的标定文案）。**不含机型常量**：
`asset_cfg` 由调用方传入（默认场景实体 `robot`），核函数与量纲是族级机制。

为什么是族级机制而不是机型配方：功率 `|tau*v|` 的量纲与"执行器 1:1 驱动关节"的索引约定
是 mjlab 实体层的通用口径（`asset.data.actuator_force * asset.data.joint_vel`），
与评测侧 `adapters/mjlab/quality_metrics.py::dof_power` 同一量纲；**权重**才是任务数值
（由各技能 profile 携带）。
"""

from __future__ import annotations

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def dof_power_penalty(
    env,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    kernel: str = "mean_abs",
) -> torch.Tensor:
    """Per-joint mechanical power |tau*v| penalty, aligned with the quality metric.

    口径与评测侧一致：功率 = ``|actuator_force * joint_vel|``（执行器与关节 1:1 同序）。
    kernel：
    * ``mean_abs``（逐关节 |tau*v| 均值，权重可读性好，默认）；
    * ``mean_square`` / ``rms`` 备查。
    """
    asset: Entity = env.scene[asset_cfg.name]
    force = asset.data.actuator_force[:, asset_cfg.joint_ids]
    velocity = asset.data.joint_vel[:, asset_cfg.joint_ids]
    power = (force * velocity).abs()
    if kernel == "mean_square":
        return torch.mean(torch.square(power), dim=-1)
    if kernel == "rms":
        return torch.sqrt(torch.mean(torch.square(power), dim=-1) + 1e-6)
    return torch.mean(power, dim=-1)
