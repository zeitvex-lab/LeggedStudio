"""**形态 Kit 的家**（2026-09-19 拍板落点）。

一个形态一份框架层真值，包内只留任务特有部分 + 入口 stub：

| Kit | 形态 | 归属包 | 提供什么 |
|---|---|---|---|
| :mod:`quadruped_kit` | 四足 | `unitree_b2` · `deeprobotics_lite3`（+ 待迁 `unitree_go1` · `unitree_go2`） | 装配骨架 / `XmlActuatorCfg` 包装 / env 装配 / 高度扫描重指 / viewer 与收尾 / `ppo_runner_cfg` |
| :mod:`wheel_leg_kit` | 轮足 | `deeprobotics_m20` · `unitree_b2w` · `unitree_go2w`（+ 待迁 `zex-w`） | `mdp/` 框架族 + `velocity_env_cfg.py` + `ppo_runner_cfg_ex` |

**为什么不放仓库顶层 `kits/`**：包侧 stub 靠"沿目录向上找 `adapters/mjlab`"自举仓库根
（worker / schema-dump / 冒烟三处只把 `training/source` 放进 `sys.path`），位置一变，
全部 stub 与自举逻辑都要改；且既有裁决已把 Kit 划在 `adapters/mjlab/` 边界内。
决策依据与否决理由见 `00_know/90_归档/07_形态Kit设计草案.md`。

**不做什么**：不建人形 Kit（`g1` 只登记不迁）；冻结包（`limx_tron1_pf/sf/wf` /
`microduck` / `wuji_hand`）不参与任何 Kit 动作；Kit 里不放任何物理数值。
"""

__all__: list[str] = []
