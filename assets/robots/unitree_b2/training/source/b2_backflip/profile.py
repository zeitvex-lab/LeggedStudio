"""Unitree B2 的后空翻配方数据（族级 `BackflipProfile` 的 b2 实例）。

## 这份数据从哪来

本仓**没有 b2 专属的后空翻上游**（后空翻的上游是 `00_resources` 里 Gym 包的
`go2_backflip`）。所以本表是**同一份配方**：族级 `BackflipProfile` 的默认值就是
go2 的源配方数值（飞行 0.6 / 站姿 0.35 / 站姿下限 0.2 / 关节速度上限 30 /
落地判定 0.1 / 接触阈值 1.0 与 150.0 / 命令重采样 5 s / 起跳帧 50~60），
b2 侧**只换机型身份**，与 `b2-wtw` 同一纪律（"只填机型身份，其余沿用源配方默认值"）。

唯一的结构性差异是**镜像腿对**：不在此声明 —— 由绑定从腿标记派生
（go2 腿序 `FL,FR,RL,RR` ⇒ `(1,3)`；b2 腿序 `FR,FL,RR,RL` ⇒ `(0,2)`），
照搬一台的常量会把左右镜像做反。

## 别把"能训"当成"训得好"

站姿/飞行高度目标是 go2 的机身几何下的数（go2 站姿 0.42 m，b2 站姿 0.54 m），
接触力阈值也是 go2 的质量量级；b2 上**没有标定过**。本档案的产品意义是
**复用证明**：族级实现 + 只换数据，第二台四足就能训同一个特技。要当正式技能用，
需按 b2 标定一轮（登记在 `registry/porting_references.json` 的 `b2-backflip` 条目里）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.backflip.profile import BackflipProfile

BACKFLIP = BackflipProfile(
    task_id="Unitree-B2-Backflip-Flat",
    experiment_name="b2_backflip",
)
