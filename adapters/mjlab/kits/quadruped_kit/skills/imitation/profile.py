"""Imitation（AMP）技能的族级常量与算法配置。

**技能级常量**（判别器容量、专家预载量、奖励系数、动作加载时间步、地形传感器名）
保留为默认值 —— 同族机型共享同一套配方；**机型身份**（`task_id` / `experiment_name`）
与**身材相关量**（判别器状态维由关节数派生）由调用方传入：

* go2：`Unitree-Go2-AMP-DreamWaQ-Rough` / `go2_amp_dreamwaq`；
* go1：`Unitree-Go1-AMP-Rough` / `go1_amp`。

`AmpPpoAlgorithmCfg` 是**族级** AMP-PPO runner 的算法配置（宿主为普通 PPO 时用；
go2 的 DreamWaQ 宿主仍用它自己的 `AmpDreamWaQAlgorithmCfg`，字段同名）。
额外字段会被 rsl_rl 原样透传给算法构造函数（`construct_algorithm` 用 ``**cfg``），
因此运动目录/关节序这类"机型侧输入"可以走 runner 配置而不是模块常量。
"""

from dataclasses import dataclass

from mjlab.rl import RslRlPpoAlgorithmCfg


@dataclass(frozen=True)
class AmpProfile:
    """一台机型在这个族级 AMP 技能里的身份 + 技能级常量。"""

    task_id: str
    experiment_name: str
    #: 判别器状态相对地形的高度传感器名（族约定：mjlab 基座的 `terrain_scan`）。
    terrain_sensor: str = "terrain_scan"
    #: 专家转移的策略时间步（源配方 50 Hz）。
    motion_dt: float = 0.02
    #: 判别器/回放/归一化的 AMP 超参（源配方默认）。
    replay_buffer_size: int = 1_000_000
    num_preload_transitions: int = 2_000_000
    reward_coef: float = 0.5
    discr_hidden_dims: tuple[int, ...] = (1024, 512)
    min_normalized_std: float = 0.05
    #: 后腿髋限位奖励（`mdp.rear_hip_limit`）的权重与阈值。
    rear_hip_limit_weight: float = -1.0
    rear_hip_limit_bound: float = 0.4
    max_iterations: int = 20_000


@dataclass
class AmpPpoAlgorithmCfg(RslRlPpoAlgorithmCfg):
    """族级 AMP-PPO（`rl.AmpPPO`）的配置：PPO 字段 + AMP 侧输入。"""

    #: 专家动作目录（`motion_root`）；空表示本任务不加载专家数据。
    amp_motion_root: str | None = None
    #: 判别器状态的关节序（与专家帧同序；机型侧按契约传入）。
    amp_joint_order: tuple[str, ...] = ()
    #: 专家转移的策略时间步（源配方 50 Hz）。
    amp_motion_dt: float = 0.02
    amp_replay_buffer_size: int = 1_000_000
    amp_num_preload_transitions: int = 2_000_000
    amp_reward_coef: float = 0.5
    amp_discr_hidden_dims: tuple[int, ...] = (1024, 512)
    min_normalized_std: float = 0.05
    symmetry_cfg: dict | None = None


__all__ = ["AmpPpoAlgorithmCfg", "AmpProfile"]
