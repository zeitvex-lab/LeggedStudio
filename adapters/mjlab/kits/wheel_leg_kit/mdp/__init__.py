# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：mdp 框架族命名空间的装配真值。
# 由 b2w_velocity/mdp/__init__.py 与 go2w_velocity/mdp/__init__.py 的逐字共同
# 部分上移（两包该文件 sha256 一致）；m20_velocity 的同名文件多出尾部两行
# m20_rewards 的再导出（那两行把 mdp 命名空间里的 UniformVelocityCommandCfg
# 覆盖成 mjlab.tasks.velocity.mdp 版本、并把 m20 专属奖励项挂进命名空间——
# 属任务特有 wiring，仍留在 m20 包内，且必须保持"最后星导入"的次序）。
#
# 星导入次序即命名空间覆盖次序：mjlab.envs.mdp 先进，包内框架族逐个覆盖，
# 与上移前三包的组合语义逐名一致。
# ------------------------------------------------------------------------------

from mjlab.envs.mdp import *  # noqa: F401, F403

from .curriculums import *  # noqa: F403
from .terrain_curriculums import *  # noqa: F403  越障技能族级化：地形级课程（含障碍释放课程）
from .feet_rewards import *  # noqa: F403
from .observations import *  # noqa: F403
from .posture_rewards import *  # noqa: F403
from .randomization import *  # noqa: F403
from .tracking_rewards import *  # noqa: F403
from .terminations import *  # noqa: F403
from .velocity_command import *  # noqa: F403
from .wheel_rewards import *  # noqa: F403

# Shared mjlab 1.6 keeps these in submodules rather than the mdp top level.
from mjlab.envs.mdp.rewards import (  # noqa: F401
    action_rate_l2,
    flat_orientation_l2,
    joint_acc_l2,
)
from mjlab.envs.mdp.dr.joint import encoder_bias as randomize_encoder_bias  # noqa: F401
from .only_positive_rewards import (  # noqa: F401
    disable_only_positive_rewards,
    enable_only_positive_rewards,
)
