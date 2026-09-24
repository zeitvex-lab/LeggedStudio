"""AMP 的 Manager-MDP 项（族级）：判别器状态、后腿髋限位、终止态记录器。

来源：`go2_skills/amp_dreamwaq/mdp.py`（逐字上移）。去机型化改动：

* `amp_state` 的关节序从模块常量 `JOINT_NAMES` 改为**参数** `joint_order`
  （调用方传契约 `action.joint_order`）；顺序断言保留（错位必须当场炸）；
* `rear_hip_limit` 从写死的 `RL/RR_hip_joint` 改为参数 `joint_names`
  （由绑定按族角色派生：后腿 × `hip_abduction`），阈值 `bound` 参数化；
* `AmpTerminalStateRecorder` 的关节序/传感器名从 `cfg.params` 读（族级唯一实现）。
"""

from __future__ import annotations

from collections.abc import Sequence

import torch
from mjlab.entity import Entity
from mjlab.managers import RecorderTerm


def amp_state(
    env, *, joint_order: Sequence[str], sensor_name: str = "terrain_scan"
) -> torch.Tensor:
    """源判别器状态：q、体线/角速度、dq、地形相对根高（2×关节数+7 维）。"""
    robot: Entity = env.scene["robot"]
    order = tuple(str(name) for name in joint_order)
    ids, names = robot.find_joints(order, preserve_order=True)
    if tuple(names) != order:
        raise RuntimeError(f"关节序与契约不一致：{names} ≠ {order}")
    scan = env.scene[sensor_name].data
    terrain_z = scan.hit_pos_w[..., 2].mean(1, keepdim=True)
    return torch.cat(
        (
            robot.data.joint_pos[:, ids],
            robot.data.root_link_lin_vel_b,
            robot.data.root_link_ang_vel_b,
            robot.data.joint_vel[:, ids],
            robot.data.root_link_pos_w[:, 2:3] - terrain_z,
        ),
        dim=1,
    )


def rear_hip_limit(
    env, *, joint_names: Sequence[str], bound: float = 0.4
) -> torch.Tensor:
    """后腿髋关节越限惩罚（源：`((q > .4) | (q < -.4)).any(dim=1)`）。"""
    robot: Entity = env.scene["robot"]
    wanted = tuple(str(name) for name in joint_names)
    ids, names = robot.find_joints(wanted, preserve_order=True)
    if tuple(names) != wanted:
        raise RuntimeError(f"髋关节名与契约不一致：{names} ≠ {wanted}")
    q = robot.data.joint_pos[:, ids]
    return ((q > bound) | (q < -bound)).any(dim=1).float()


class AmpTerminalStateRecorder(RecorderTerm):
    """把 reset 前的 AMP 状态交给 on-policy 算法（源 `terminal_amp_states` 口径）。

    mjlab 自动 reset 后的观测是**下一段** episode 的初始态；本记录器在 reset 前
    跑，保留动作真正到达的终止态 —— 与 Gym AMP runner 的路径一致。
    关节序/传感器名从 `cfg.params` 读（族级唯一实现；机型侧只给参数）。
    """

    def _state(self, env) -> torch.Tensor:
        params = self.cfg.params or {}
        return amp_state(
            env,
            joint_order=params.get("joint_order") or (),
            sensor_name=params.get("sensor_name", "terrain_scan"),
        )

    def record_pre_reset(self, env_ids: torch.Tensor) -> None:
        self._env.extras["amp_terminal_env_ids"] = env_ids.clone()
        self._env.extras["amp_terminal_states"] = self._state(self._env)[env_ids].clone()

    def record_post_step(self) -> None:
        if not torch.any(self._env.reset_buf):
            self._env.extras.pop("amp_terminal_env_ids", None)
            self._env.extras.pop("amp_terminal_states", None)
