# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：mdp 框架族十文件已上移 adapters/mjlab/velocity_task_kit/
# mdp/（见 kit/mdp/__init__ 头注释）。本包 __init__ = kit 组合真值一行星导入 +
# **本包特有的尾部两行**（原样保留，次序必须最后）：
# `from .m20_rewards import *` 会把命名空间里的 UniformVelocityCommandCfg /
# UniformVelocityCommand 覆盖成 mjlab.tasks.velocity.mdp 版本（m20_rewards 为
# 子类化 UniformThresholdVelocityCommandM20 而显式导入再泄出），并把 m20 专属
# 奖励项挂进命名空间——velocity_env_cfg 的 twist 基类与 env_cfgs 的 mdp.* 解析
# 都依赖这一覆盖语义，等价实证按此对账。
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

from adapters.mjlab.velocity_task_kit.mdp import *  # noqa: F401, F403, E402

from .m20_rewards import *  # noqa: F401, F403, E402
from .m20_rewards import joint_pos_rel_zero_wheel  # noqa: F401, E402
