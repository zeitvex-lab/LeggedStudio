"""Unitree Go1 的后空翻配方数据（族级 `BackflipProfile` 的 go1 实例）。

## 这份数据从哪来

本仓**没有 go1 专属的后空翻上游**（后空翻的上游是 `00_resources` 里 Gym 包的
`go2_backflip`）。所以本表是**同一份配方**：族级 `BackflipProfile` 的默认值就是
go2 的源配方数值，go1 侧**只换机型身份**，与 `go1-jump`（只填 `task_id` /
`experiment_name`）同一纪律。

镜像腿对不在此声明：由绑定从腿标记派生（go1 契约腿序 `FL,FR,RL,RR` ⇒ `(1,3)`，
与 go2 同值）。

## 站姿高正好对得上，其余仍未标定

go1 的出生站姿高是 **0.42 m**（`go1_velocity.robot_constants.INIT_STATE.pos[2]`），
与 go2 特技源配方的 0.42 **同值** ⇒ 几何目标高（飞行 0.6 / 站姿 0.35 / 落地判定 0.1）
这一组在本档不需要按机身缩放（这是"同族同构"的巧合，不是标定）。

仍**未按 go1 标定**的是与质量/电机量级相关的那几项：接触力阈值（1.0 / 150.0）、
关节速度上限（30 rad/s）、启动 DR 区间（摩擦 0.2~1.25 / 质量 ±1 kg）—— 与 `b2-backflip`
同样的口径：**能训 ≠ 训得好**，登记在 `registry/porting_references.json` 的
`go1-backflip` 条目里。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.backflip.profile import BackflipProfile

BACKFLIP = BackflipProfile(
    task_id="Unitree-Go1-Backflip-Flat",
    experiment_name="go1_backflip",
)
