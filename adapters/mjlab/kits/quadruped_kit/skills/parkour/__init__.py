"""越障（parkour / PIE）技能的族级实现。

## 这一层解决什么

PIE 深度越障此前整份住在 `unitree_go2` 包里（入口硬编码
`local_tasks.robots.unitree.go2.tasks.parkour.*`，相机位姿/分辨率/视场是字面量），
同族其它机型**没得复用**。本层把这套装配上移为族级技能：机型包只保留薄委托（入口名不动）
+ 一份**机型绑定** + profile（机型身份 + 相机档位 id）。

## 目录

* `profile.py` —— 配方常量（足端槽位序、大腿限位上界、相机档位 id 的容器）与机型身份；
* `camera.py` —— **深度相机声明**的读取与换算（`registry/cameras.json`，缺项 fail-closed）；
* `binding.py` —— 绑定 + 配方 → 装配要的形状（足端槽位校验、足端几何/帧、配方级限位）；
* `config.py` —— 环境/运行器工厂（装配骨架）；
* `mdp/` —— 本技能自有的 MDP 项（观测/奖励/终止/课程/命令）；
* `rl/` —— PIE 模型、PPO 扩展与专用 runner；
* `terrains.py` —— PIE 地形集（配方常量）。

## 关节序怎么来（同族统一设计）

动作项 `joint_pos` 的 `actuator_names=(".*",)`：关节布局由 MJCF 决定，观测里的
`joint_pos_joint_vel` 用同一模式取序 —— 与 `trot/jump` 的"按契约关节序 `preserve_order`"
不同，那是**源配方**的写法（PIE 移植自 IsaacGym，从不导出关节序），迁移以等价为先，
故原样保留；族级可复用的部分（相机/根 body/足端/角色关节）已全部声明驱动。
"""

from __future__ import annotations

from .camera import DepthCameraDeclaration, resolve_depth_declaration
from .config import make_env_cfg, make_runner_cfg
from .profile import ParkourProfile
from .rl import PIEActorModel, PIEPPO, PIEOnPolicyRunner, PIEPpoAlgorithmCfg

__all__ = [
    "DepthCameraDeclaration",
    "PIEActorModel",
    "PIEPPO",
    "PIEPpoAlgorithmCfg",
    "PIEOnPolicyRunner",
    "ParkourProfile",
    "make_env_cfg",
    "make_runner_cfg",
    "resolve_depth_declaration",
]
