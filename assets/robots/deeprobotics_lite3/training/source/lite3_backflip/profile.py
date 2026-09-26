"""Deeprobotics Lite3 的后空翻配方数据（族级 `BackflipProfile` 的 lite3 实例）。

## 这份数据从哪来

本仓**没有 lite3 专属的后空翻上游**（后空翻的上游是 `00_resources` 里 Gym 包的
`go2_backflip`）。所以本表是**同一份配方**：族级 `BackflipProfile` 的默认值就是
go2 的源配方数值，lite3 侧**只换机型身份**，与 `lite3-jump` 同一纪律。

镜像腿对不在此声明：由绑定从腿标记派生（lite3 契约腿序 `FL,FR,HL,HR` ⇒ `(1,3)`）。

## 别把"能训"当成"训得好" —— 未按 lite3 标定

几何目标高（飞行 0.6 / 站姿 0.35 / 落地判定 0.1）与接触力阈值（1.0 / 150.0）是 go2
几何（站姿 0.42 m）与质量量级下的数，lite3 站姿 **0.3 m** ⇒ 目标高相对偏高，
**未标定**；能训 ≠ 训得好。登记在 `registry/porting_references.json` 的
`lite3-backflip` 条目里。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.backflip.profile import BackflipProfile

BACKFLIP = BackflipProfile(
    task_id="Unitree-Lite3-Backflip-Flat",
    experiment_name="lite3_backflip",
)
