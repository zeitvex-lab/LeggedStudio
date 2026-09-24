"""Go2 侧薄委托：族级观测帧与历史缓冲（老路径兼容）。

族级实现在 `.../quadruped_kit/skills/mdp/observations.py`（trot / jump 共用一份）。
保留本模块是因为包内**未上移**的技能按老路径复用这里的符号：

* `backflip/mdp/observations.py`：`_SourceHistory`、`joint_ids`；
* `spring_jump/mdp/observations.py`：`_SourceHistory`、`contact_observation`、
  `root_euler`、`joint_ids`。

`joint_ids` 两处口径不同，别混：族级实现收**环境**（关节序取自动作项），
包内未上移的技能沿用"收实体 + 契约关节序"的老签名，故这里转出的是
`shared.contacts.joint_ids`。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    JumpActorHistory,
    JumpCriticHistory,
    TrotActorHistory,
    TrotCriticHistory,
    _SourceHistory,
    actor_frame,
    contact_observation,
    critic_frame,
    jump_actor_frame,
    jump_critic_frame,
    jump_phase,
    jump_phase_command,
    jump_stance_mask,
    phase,
    phase_command,
    root_euler,
    single_frame_noise_bounds,
    stance_mask,
)

from ...shared.contacts import joint_ids

__all__ = [
    "JumpActorHistory",
    "JumpCriticHistory",
    "TrotActorHistory",
    "TrotCriticHistory",
    "_SourceHistory",
    "actor_frame",
    "contact_observation",
    "critic_frame",
    "joint_ids",
    "jump_actor_frame",
    "jump_critic_frame",
    "jump_phase",
    "jump_phase_command",
    "jump_stance_mask",
    "phase",
    "phase_command",
    "root_euler",
    "single_frame_noise_bounds",
    "stance_mask",
]
