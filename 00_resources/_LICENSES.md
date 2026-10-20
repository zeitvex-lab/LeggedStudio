# 参考资源许可边界（2026-10-18）

> 本文件是**使用边界索引**，不替代各项目 `_SOURCE.md` 与上游 LICENSE 原文。
> 原则：许可不明 = reference-only；非商用 = 只读参考；代码移植必须保留版权/许可/NOTICE 并标注修改。

| 项目 | 许可 | 使用边界 |
|---|---|---|
| `legbot_lab_PPO` / `legbot_lab_PPO-CTS-MOE` / `legbot_lab_WF-CTS-MOE` | Apache-2.0 | 可移植（保留版权/许可/NOTICE；README badge 与 LICENSE 冲突时以 LICENSE 为准） |
| `GO2_backflip` | MIT | 可移植（保留版权/许可） |
| `deepseek-harness` | MIT | 可移植（保留版权/许可/NOTICE）；插件架构/内容清单参考；不并入运行时 |
| `awesome-rl-for-legged-locomotion` | CC0-1.0 | 可复制/修改/商用（无版权保留要求）；仅文献索引，论文正文/代码/权重另核 |
| `amp_go2` / `smp` / `locowiki-open-source` | unknown | **reference-only**：无 LICENSE 或未声明 |
| `HIMLoco-for-Go2W` / `champ` | BSD-3-Clause | 可移植（保留版权/许可） |
| `RC_WheelLeg` / `TWIST` / `TWIST2` / `GMR` / `rl-mpc-locomotion` / `umi-on-legs` / `Cheetah-Software` / `26RC_Field` | MIT | 可移植（保留版权/许可） |
| `blender-mujoco-hfield` / `quadruped_robot_lab` | Apache-2.0 | 可移植（保留版权/许可/NOTICE） |
| `TienKung-Lab` / `uw-himloco` | BSD-3-Clause | 可移植（保留版权/许可） |
| `go2_flip_TO` | BSD-2-Clause | 可移植（保留版权/许可） |
| `A1-QP-MPC-Controller` | AGPL-3.0 | reference-only / 独立参考；不并入闭源分发 |
| `IsaacLab` | BSD-3-Clause（`isaaclab_mimic` 为 Apache-2.0） | reference-only；Isaac Sim 组件/资产另按 NVIDIA 许可，不随产品分发 |
| `UniLab` | Apache-2.0 | 可移植（保留版权/许可/NOTICE）；reference-only 使用，不并入运行时 |
| `ComfyUI` | GPL-3.0 | **reference-only / 独立 sidecar**：不把代码并入产品可执行/安装包；分发修改版需按 GPLv3 提供源码；模型权重/自定义节点另核 |
| `dfki-quad` | BSD-3-Clause | 可移植（保留版权/许可；外部依赖另核） |
| `legged_mpc_amp` | BSD-3-Clause + THIRD_PARTY_NOTICES | 可移植（保留 notices；qpOASES 为 LGPL-2.1，发布前替换或隔离） |
| `extreme-parkour` | CC BY-NC 4.0 | **reference-only**：不得把代码/资产/权重复制进产品 |
| `legged_robot_competition` | unknown（无 LICENSE） | **reference-only** |
| `beyondAMP` | unknown（无 LICENSE） | **reference-only** |
| `quadruped-robotics-stack` | unknown（无顶层 LICENSE） | **reference-only**（本地参考，未纳入版本） |
| `robocraftai.cn` / `1000framesai.com` / `sim.stackforce.cc` | unknown | **reference-only**：竞品站点快照，不随产品分发 |

新增参考先写 `00_resources/<project>/_SOURCE.md`（URL / 分支 / commit / 许可 / 边界），再登记到 `tools/sync_resources.py` 与本表。
