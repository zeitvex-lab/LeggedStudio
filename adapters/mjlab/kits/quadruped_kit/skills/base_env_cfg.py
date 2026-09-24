"""族级技能的平地基座。

## 它对应源实现的哪一段

源实现（go2）的技能 cfg 是**从该机型的 velocity 平地环境**长出来的：

```python
cfg = make_flat_env_cfg(<该机型的 velocity profile>, play=False)   # 源：upstream/velocity.py
cfg.scene.entities = {...}; cfg.observations = {...}; ...           # 技能层逐项覆盖
```

技能层几乎把所有段都覆盖掉了（观测/动作/命令/事件/奖励/终止/课程/传感器/实体），
**真正留下来的只有**：sim 上限（njmax / ccd_iterations / contact_sensor_maxmatch / nconmax）、
平地形（`terrain_type="plane"`，无 generator，保留 `max_init_terrain_level`）、
viewer 三元组、以及 `scene.extent` 这类基座默认值。
本模块就是把这"留下来的那部分"写成一个**与机型无关**的构造器 ——
它等价于"该机型 velocity 平地环境被逐项覆盖后的余项"，因此不需要知道任何机型。

设计上刻意**不**沿用机型的 velocity profile：那会把 velocity 任务的奖励/传感器/姿态参数
带进技能层（随后被覆盖），既掩盖真实依赖，也让"技能层复用"变成"velocity 层复用"的寄生。
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

from .. import apply_flat_postlude, set_viewer
from .binding import QuadrupedSkillBinding


def flat_base_env_cfg(binding: QuadrupedSkillBinding) -> ManagerBasedRlEnvCfg:
    """mjlab velocity 基座 + 平地收尾 + 基座显示（技能层覆盖前的起点）。"""
    cfg = make_velocity_env_cfg()
    apply_flat_postlude(cfg, drop_terrain_scan_sensor=True, drop_height_scan_obs=True)
    set_viewer(cfg, body_name=binding.root_body, distance=1.5, elevation=-10.0)
    return cfg
