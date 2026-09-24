"""族级角色解析 —— 技能层与机型名的**唯一**接触面。

## 为什么需要它

技能层要"同族任何机型都能训同一技能"，就必须让**每个机型差异都从声明里取**，
一个都不许写在 Kit 内。四足族有两份声明可用，本模块把它们解析成技能层要的形状：

| 声明 | 真值 | 技能层拿它做什么 |
|---|---|---|
| `assets/robots/<机型>/contract.json` | 该机型自己的事实（关节名与序、默认姿、执行器谱、腿标记） | 关节序/默认姿/PD/足端几何名的**派生输入**（见 `binding.py`，不在本模块） |
| `registry/families/<族>.json` | 族级约定（角色骨架 + `role_aliases`） | 把某机型的角色名映射到族角色（`hip_abduction` / `hip_pitch` / `knee`），供"选髋关节""惩罚腿杆接触"这类**按角色**的项使用 |

## 命名约定（族级，不是机型级）

* **腿**：契约 `morphology.leg_ids`（四足族 = FL/FR/RL/RR，顺序即足端张量顺序）；
* **关节**：契约 `action.joint_order`（顺序即策略布局，**不是** MJCF 里的顺序 ——
  go2 两者一致，go1 的 MJCF 是 FR/FL/RL/RR 而契约是 FL/FR/RL/RR，这个区别正是
  "不许从 MJCF 推关节序"的理由）；
* **足端几何**：名里带 token ``foot`` —— 这条约定早于本模块就存在（
  `quadruped_kit.quadruped_foot_collision` 一直用 ``.*foot.*`` 给 b2/lite3 配足端碰撞）；
* **足端帧**：优先取与足端几何**同腿前缀**的 site（go2 有 FL/FR/RL/RR 四个 site），
  没有 site 的机型（go1）回退到足端几何自身的世界位姿（见 `mdp/contacts.py`）。

本模块**只读**声明文件，不复制任何数值；读不到就抛错，不静默回落。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

FAMILY_DIR_NAME = ("registry", "families")
DEFAULT_FAMILY_ID = "quadruped"
FOOT_TOKEN = "foot"


@lru_cache(maxsize=1)
def _repo_root() -> Path:
    """沿目录向上找族声明所在处（`registry/families/index.json` 是族注册的锚）。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / FAMILY_DIR_NAME[0] / FAMILY_DIR_NAME[1] / "index.json").is_file():
            return parent
    raise RuntimeError(
        "找不到 registry/families/index.json —— 族级技能层要求仓库根在场"
        "（包侧 stub 会先自举仓库根再导入本 Kit）"
    )


@lru_cache(maxsize=8)
def load_family(family_id: str = DEFAULT_FAMILY_ID) -> dict:
    """读族声明（唯一真值）。`lru_cache` 只在进程内缓存文件内容。"""
    path = _repo_root() / FAMILY_DIR_NAME[0] / FAMILY_DIR_NAME[1] / f"{family_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"族声明不存在：{path}")
    # 编码口径跟仓库守卫 `backend/test_jsonio_single_source.py` 一致：读 JSON 必须吃 BOM。
    return json.loads(path.read_text(encoding="utf-8-sig"))


def role_aliases(family_id: str = DEFAULT_FAMILY_ID) -> dict[str, tuple[str, ...]]:
    """族角色的别名表（小写）：`{"hip_abduction": ("hip","hipx"), ...}`。"""
    aliases = load_family(family_id).get("role_aliases") or {}
    return {str(role): tuple(str(x).lower() for x in names) for role, names in aliases.items()}


def family_roles(family_id: str = DEFAULT_FAMILY_ID) -> tuple[str, ...]:
    """族角色骨架（顺序即角色语义）：关节序里"每条腿的角色段"按它排列。"""
    roles = load_family(family_id).get("joint_roles") or []
    if not roles:
        raise ValueError(f"族 {family_id} 未声明 joint_roles")
    return tuple(str(role) for role in roles)


def joint_tokens(joint_name: str) -> tuple[str, ...]:
    """把关节名切成小写 token（`FL_hip_joint` → `fl/hip/joint`）。"""
    return tuple(part.lower() for part in str(joint_name).replace("-", "_").split("_") if part)


def role_of_joint(joint_name: str, family_id: str = DEFAULT_FAMILY_ID) -> str | None:
    """按族别名把关节名映射回族角色；映射不到返回 None（调用方决定是否判红）。"""
    tokens = set(joint_tokens(joint_name))
    for role, names in role_aliases(family_id).items():
        # 完全相等的别名（`knee` ↔ "knee"）与 token 相交（`hip` ∈ FL_hip_joint）都算命中。
        if any(name in tokens for name in names):
            return role
    return None


def joint_indices_by_role(
    joint_order: tuple[str, ...] | list[str],
    role: str,
    family_id: str = DEFAULT_FAMILY_ID,
) -> tuple[int, ...]:
    """在给定关节序里挑出某个族角色的位置。

    与"每 3 个取 1 个"这种位置假设不同：**位置假设会随腿/角色数变化而错位**，
    而按名字 + 族别名选是声明驱动的 —— 换机型、换角色数都不用改技能层。
    """
    names = role_aliases(family_id).get(role)
    if names is None:
        raise KeyError(f"族 {family_id} 未声明角色 {role}")
    picked = []
    for index, joint in enumerate(joint_order):
        tokens = set(joint_tokens(joint))
        if any(name in tokens for name in names):
            picked.append(index)
    return tuple(picked)


def foot_geoms_for_legs(
    geom_names: Sequence[str],
    leg_ids: tuple[str, ...],
    foot_token: str = FOOT_TOKEN,
) -> tuple[str, ...]:
    """在给定几何名集合里挑出**按腿序**排列的足端几何名。

    匹配规则：名里同时含该腿标记与足端 token（`FL_foot_collision`）。
    Kit 内不写任何机型的几何名 —— 名字从几何名集合里挑：
    配置期从 `spec_fn()` 编译出的 MjModel 取（静态、无需先建环境），
    运行期从 `robot.geom_names` 取（同一份 MJCF 真值）。
    """
    available = [str(name) for name in geom_names if name]
    picked: list[str] = []
    for leg in leg_ids:
        hits = [
            name
            for name in available
            if name.split("_")[0].lower() == leg.lower() and foot_token in name.lower()
        ]
        if not hits:
            raise RuntimeError(
                f"几何里找不到腿 {leg} 的足端几何（族约定：名含 {foot_token!r}）—— "
                f"可用几何：{sorted(available)[:12]}"
            )
        picked.append(sorted(hits)[0])
    return tuple(picked)
