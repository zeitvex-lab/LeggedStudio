"""Go2 侧薄委托：族级奖励原语 + 族级 PPO runner 构造。

族级实现在 `.../quadruped_kit/skills/mdp/rl.py`。本模块把 go2 的绑定绑到需要
关节序的原语上，并原样转出与机型无关的那些 —— 包内未上移的技能
（backflip / hand_stand / rear_stand / dreamwaq / amp_dreamwaq）继续按老签名调用。

`make_ppo_runner_cfg` 是**族级唯一真值**（含 `symmetry_cfg` 扩展的算法配置类），
原先住在 `go2_skills/upstream/rl.py`。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp import rl as _kit_rl

from ..binding import GO2

#: 与机型无关的原语：直接转出（族级实现即唯一真值）。
RslRlPpoWithSymmetryAlgorithmCfg = _kit_rl.RslRlPpoWithSymmetryAlgorithmCfg
make_ppo_runner_cfg = _kit_rl.make_ppo_runner_cfg
command = _kit_rl.command
moving = _kit_rl.moving
lin_vel_z_squared = _kit_rl.lin_vel_z_squared
ang_vel_xy_squared = _kit_rl.ang_vel_xy_squared
orientation_squared = _kit_rl.orientation_squared
collision = _kit_rl.collision
action_rate = _kit_rl.action_rate
contact_without_command = _kit_rl.contact_without_command
terminal_cost = _kit_rl.terminal_cost


#: 需要关节序的项：族级实现从动作项（`joint_pos`，go2 的序 = 契约序）取 id，
#: 故这里也只是转出 —— 包内未上移的技能用的动作项名与顺序都与之一致。
DofAcceleration = _kit_rl.DofAcceleration
torques_squared = _kit_rl.torques_squared
absolute_torques = _kit_rl.absolute_torques
stand_still = _kit_rl.stand_still
default_pos = _kit_rl.default_pos
