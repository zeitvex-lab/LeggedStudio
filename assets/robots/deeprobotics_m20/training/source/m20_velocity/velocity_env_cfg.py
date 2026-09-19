# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：本文件与 b2w_velocity / go2w_velocity 的同名文件
# 逐字全同（sha256 一致），正文已上移为 adapters/mjlab/kits/wheel_leg_kit/
# velocity_env_cfg.py（唯一真值）。m20 包内留一个语义绑定 stub：上移前本文件
# `from .mdp import UniformVelocityCommandCfg` 解析到的是 **mjlab.tasks.velocity.
# mdp 版本**（m20 包 mdp/__init__ 尾部 m20_rewards 星导入的覆盖结果，m20 的
# UniformThresholdVelocityCommandM20 正子类化它）——与 b2w/go2w 的包内框架族
# 类不同，故这里显式把本包 mdp 命名空间解析到的类传给 kit 工厂，逐字段保持
# 上移前语义（语义等价实证见 .tmp_b8_batch2 dump 比对 / 汇报）。
# ------------------------------------------------------------------------------

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.wheel_leg_kit.velocity_env_cfg import (  # noqa: E402
    make_velocity_env_cfg as _kit_make_velocity_env_cfg,
)

from . import mdp  # noqa: E402


def make_velocity_env_cfg():
    """velocity 基座 cfg（m20 语义绑定，见文件头说明）。"""
    return _kit_make_velocity_env_cfg(
        uniform_velocity_command_cfg=mdp.UniformVelocityCommandCfg
    )
