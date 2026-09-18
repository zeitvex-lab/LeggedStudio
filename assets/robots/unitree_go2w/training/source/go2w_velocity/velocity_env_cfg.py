# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：本文件与 m20_velocity / go2w_velocity 的同名文件
# 逐字全同（sha256 一致），已上移为 adapters/mjlab/velocity_task_kit/
# velocity_env_cfg.py（唯一真值）。包内只留再导出 stub：默认（不传参）即
# kit 框架族 UniformVelocityCommandCfg —— 与上移前本包语义一致。
# ------------------------------------------------------------------------------

import sys
from pathlib import Path

# 仓库根自举（见 velocity_task_kit 模块注释）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.velocity_task_kit.velocity_env_cfg import (  # noqa: E402, F401
    make_velocity_env_cfg,
)
