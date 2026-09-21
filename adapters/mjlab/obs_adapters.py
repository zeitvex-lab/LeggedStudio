"""本体观测适配器（proprio 45D 帧）。

段序与缩放与浏览器 ``observation_builders.js::fillRlSdkActorFrame`` / 桌面
``policy_acceptance.py::ObsBuilder`` **同源**（三端口径一致是本项目硬约束）：

    [ang_vel×ang_scale(3), projected_gravity(3), cmd×cmd_scale(3),
     (qpos−default)×pos_scale(12), qvel×vel_scale(12), last_action(12)]

关节槽按契约 ``joint_order`` 的**名字**解析到模型 ``jnt_qposadr/jnt_dofadr``——
模型物理序与策略序可能不同（SDK 序 FR,FL,RR,RL vs mjlab 序），按名字对齐才不错排。
``projected_gravity = R^T·[0,0,-1]``（直立为 [0,0,-1]，与采样同号，勿取负）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

__all__ = ["ProprioFrameBuilder"]


def _quat_rotate_inverse(q: Sequence[float], v: Sequence[float]) -> np.ndarray:
    """``R^T · v``（q 为 wxyz）。"""

    w, x, y, z = (float(c) for c in q)
    vx, vy, vz = (float(c) for c in v)
    t = 2.0 * np.array([y * vz - z * vy, z * vx - x * vz, x * vy - y * vx])
    return np.array([vx, vy, vz]) - w * t + np.cross([x, y, z], t)


class ProprioFrameBuilder:
    """把 MuJoCo 状态装配成策略本体观测帧（不感知传感器/深度/历史——那些走各自适配器）。"""

    def __init__(
        self,
        *,
        joint_order: Sequence[str],
        default_angles: Mapping[str, float],
        ang_vel_scale: float = 0.25,
        dof_pos_scale: float = 1.0,
        dof_vel_scale: float = 0.05,
        command_scale: Sequence[float] = (1.0, 1.0, 1.0),
        action_dim: int = 12,
    ) -> None:
        self._joint_order = [str(name) for name in joint_order]
        self._defaults = np.array(
            [float(default_angles.get(name, 0.0)) for name in self._joint_order], dtype=np.float64
        )
        self._ang_scale = float(ang_vel_scale)
        self._pos_scale = float(dof_pos_scale)
        self._vel_scale = float(dof_vel_scale)
        self._cmd_scale = np.array([float(c) for c in command_scale], dtype=np.float64)
        self._action_dim = int(action_dim)
        self._qadr: list[int] = []
        self._vadr: list[int] = []

    def bind(self, model: Any) -> None:
        """编译后解析关节地址；查不到即抛（fail-closed，不静默错排）。"""

        import mujoco

        qadr: list[int] = []
        vadr: list[int] = []
        for name in self._joint_order:
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise ValueError(f"模型缺少关节 {name!r}，无法按契约关节序装配观测")
            qadr.append(int(model.jnt_qposadr[jid]))
            vadr.append(int(model.jnt_dofadr[jid]))
        self._qadr = qadr
        self._vadr = vadr

    @property
    def obs_dim(self) -> int:
        return 9 + 2 * len(self._joint_order) + self._action_dim

    def build(self, data: Any, last_action: Any, command: Any = None) -> np.ndarray:
        if not self._qadr:
            raise ValueError("ProprioFrameBuilder 未 bind（先 bind(model) 再 build）")
        gravity = _quat_rotate_inverse(data.qpos[3:7], (0.0, 0.0, -1.0))
        ang_vel = np.asarray(data.qvel[3:6], dtype=np.float64) * self._ang_scale
        cmd_raw = np.zeros(3, dtype=np.float64) if command is None else np.asarray(command, dtype=np.float64)[:3]
        cmd = cmd_raw * self._cmd_scale
        pos_rel = (np.asarray([data.qpos[a] for a in self._qadr], dtype=np.float64) - self._defaults) * self._pos_scale
        vel = np.asarray([data.qvel[a] for a in self._vadr], dtype=np.float64) * self._vel_scale
        act = (
            np.zeros(self._action_dim, dtype=np.float64)
            if last_action is None
            else np.asarray(last_action, dtype=np.float64)[: self._action_dim]
        )
        frame = np.concatenate([ang_vel, gravity, cmd, pos_rel, vel, act])
        return frame.astype(np.float32)
