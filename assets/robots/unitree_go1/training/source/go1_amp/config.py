"""Unitree Go1 的 AMP 环境/运行器入口（族级 imitation 技能 + go1 绑定）。

## 这个文件为什么这么短

族级 imitation 技能层（`quadruped_kit/skills/imitation/`）承接了 AMP 的全部实现：
判别器状态观测、后腿髋限位、终止态记录器、判别器/回放/归一化、AMP 奖励整形与更新
次序、专家动作加载器。本文件只做三件事：

1. 用 go1 的**契约 + 包内 MJCF** 建立绑定（`_build_binding()`）——关节序 / 后腿髋
   关节名 / 足端几何全部派生，没有一处手抄；
2. 把**宿主**交给族级工厂：go1 的 rough velocity 任务（`go1_velocity.env_cfg`）——
   AMP 是叠在速度跟踪上的风格先验，宿主决定机器人/物理/速度奖励；
3. 指出**族内共享的专家动作目录**（见 `shared_amp_motion_root()`）。

## 两处机型侧输入（都在此取证）

* `init_base_height=0.42` —— 出生高，契约里没有这一项（不是机型常量，是任务参数）；
* 专家数据 = **借用 go2 的 LLoco 动作**：go1 与 go2 的关节名与契约关节序完全相同
  （`FL/FR/RL/RR × hip/thigh/calf`），先用它验证"同序 ⇒ 数据可复用"这一最省成本的
  路径；go1 自己的专家动作与族级动作库登记是后续 gap（如实登记，不在本轮伪造）。

## 已知边界（如实登记）

* go1 的 MJCF 腿序是 FR/FL/RL/RR，契约是 FL/FR/RL/RR：判别器状态按**契约序**采样
  （与专家帧同序，语义对齐）；动作 std 下限按契约序送到策略侧 —— go1 各腿同角色的
  关节限位相同，故该置换在数值上无差别；
* go1 无足端 site：宿主（go1_velocity）已按既有裁决处理，本技能不碰。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根自举（与 go1_jump / go1_velocity / quadruped_kit 同一约定）。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import (  # noqa: E402
    QuadrupedSkillBinding,
    from_contract,
)
from adapters.mjlab.kits.quadruped_kit.skills.imitation import config as kit_amp  # noqa: E402

from go1_velocity.env_cfg import make_go1_rough_env_cfg  # noqa: E402
from go1_velocity.robot_constants import get_go1_robot_cfg  # noqa: E402

from .profile import GO1_AMP  # noqa: E402

#: 源配方的出生高（go1 站姿高；契约不声明该字段）。
INIT_BASE_HEIGHT = 0.42


def contract_path() -> Path:
    """沿目录向上找 v3 契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 unitree_go1 的 contract.json（沿目录向上查找）")


def _build_binding() -> QuadrupedSkillBinding:
    contract = json.loads(contract_path().read_text(encoding="utf-8-sig"))
    return from_contract(
        contract,
        spec_fn=get_go1_robot_cfg().spec_fn,
        base_entity_cfg=get_go1_robot_cfg,
        init_base_height=INIT_BASE_HEIGHT,
    )


GO1: QuadrupedSkillBinding = _build_binding()


def shared_amp_motion_root() -> Path:
    """族内共享的 AMP 专家动作目录（本轮试点：go2 包内的 LLoco 数据）。

    解析方式对 assets 源树与 workspace 镜像副本两种深度都成立：沿目录向上找
    含该相对路径的仓库根。
    """
    relative = Path(
        "assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2"
        "/assets/motions/go2_amp"
    )
    for parent in Path(__file__).resolve().parents:
        candidate = parent / relative
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"找不到族内共享 AMP 动作数据（相对仓库根）：{relative}")


def make_go1_amp_env_cfg(*, play: bool = False):
    """族级 imitation 技能 + go1 rough velocity 宿主（入口签名与族级工厂一致）。"""
    return kit_amp.make_env_cfg(
        GO1,
        GO1_AMP,
        host_env_fn=make_go1_rough_env_cfg,
        play=play,
    )


def make_go1_amp_runner_cfg():
    """族级 AMP runner（算法类 = 族级 `imitation.rl:AmpPPO`，宿主持有 PPO 基类）。"""
    return kit_amp.make_runner_cfg(
        GO1, GO1_AMP, motion_root=str(shared_amp_motion_root())
    )
