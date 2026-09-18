# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：mdp 框架族十文件（curriculums / feet_rewards /
# observations / posture_rewards / randomization / rewards / terminations /
# tracking_rewards / velocity_command / wheel_rewards）在 m20/b2w/go2w 三包
# 逐字全同（velocity_command 仅 m20 一个局部变量名之差），已整体上移为
# adapters/mjlab/velocity_task_kit/mdp/（组合真值亦在 kit/mdp/__init__）。
# 本包 __init__ 只剩一行星导入：最终命名空间与上移前逐名一致
# （kit/mdp/__init__ 的组合次序 = 上移前 b2w/go2w mdp/__init__ 的次序）。
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
