"""Standalone Unitree Go2 PIE stair-locomotion task.

族级化（2026-09-25）后，本包**只剩薄委托**：

* `binding.py` —— 机型绑定（契约 + 本机型训练 MJCF）与配方身份 / 相机档位；
* `config/go2/` —— 入口模块（模块路径与符号名不变：profile 的 `entrypoints` 指向它们）；
* `rl/` —— 专用 runner 的包内再导出（profile 的 `runner_class` 指向它）。

实现（装配骨架、MDP 项、PIE 模型、PPO 扩展、地形、专用 runner）在族级
`adapters.mjlab.kits.quadruped_kit.skills.parkour/`。仓库根自举放在本包里做一次，
后续所有子模块都能 `import adapters.mjlab...`。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（与 go2_skills / go1 侧同一约定）：worker 只把包根与 training/source 放进
# sys.path，不保证仓库根在场；沿目录向上找 `adapters/mjlab` 对 assets 源树与 workspace
# 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
