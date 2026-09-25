"""族级角色解析 —— 技能层与机型名的**唯一**接触面（轮足族）。

## 为什么需要它

技能层要"同族任何机型都能训同一技能"，就必须让**每个机型差异都从声明里取**，
一个都不许写在 Kit 内。轮足族有这两份声明可用，本模块把它们解析成技能层要的形状：

| 声明 | 真值 | 技能层拿它做什么 |
|---|---|---|
| `assets/robots/<机型>/contract.json` | 该机型自己的事实（关节名与序、默认姿、执行器谱、腿标记） | 关节序/默认姿/PD/动作缩放的**派生输入**（见 `binding.py`，不在本模块） |
| `registry/families/wheel_leg.json` | 族级约定（角色骨架 + `role_aliases`） | 把某机型的角色名映射到族角色（`hip_abduction` / `hip_pitch` / `knee` / `wheel`），供"选髋关节""轮-地接触""按角色取关节"这类**按角色**的项使用 |

本模块与四足族的 `quadruped_kit/skills/family.py` 同口径、**同实现思路**，但两族
Kit 刻意互不依赖（形态不同、角色词表不同）——故这里是一份独立的小实现，不做跨 Kit 共享。

## 命名约定（族级，不是机型级）

* **腿**：契约 `morphology.leg_ids`（顺序即该机型声明的腿标记序）；
* **关节**：契约 `action.joint_order`（顺序即策略布局，**不是** MJCF 里的顺序 ——
  go2w 两者不同：MJCF 按腿混排、契约腿先轮后，这个区别正是"不许从 MJCF 推关节序"的理由）；
* **轮-地接触**：主匹配按"腿标记 + 轮角色别名"派生（机身可能是 `<LEG>_wheel_link`），
  另收通用足端 token `foot`（轮足族里"轮 = 足"，历史配方用 `(wheel|foot)` 两写法都收）。

本模块**只读**声明文件，不复制任何数值；读不到就抛错，不静默回落。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FAMILY_DIR_NAME = ("registry", "families")
DEFAULT_FAMILY_ID = "wheel_leg"
#: 族声明的轮角色名（轮足族 `joint_roles` 的末位语义；见 `family_roles()`）。
WHEEL_ROLE = "wheel"
#: 轮-地接触的通用足端 token（除族声明的轮角色别名之外的补充写法）。
WHEEL_CONTACT_TOKENS: tuple[str, ...] = ("foot",)
#: 关节名到腿标记的分隔符（族约定 `{LR}_{role}_joint`）。
LEG_PREFIX_SEPARATOR = "_"


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


def repo_root() -> Path:
    """仓库根（族声明与 `registry/*.json` 声明的所在处）。"""
    return _repo_root()


@lru_cache(maxsize=8)
def load_family(family_id: str = DEFAULT_FAMILY_ID) -> dict:
    """读族声明（唯一真值）。`lru_cache` 只在进程内缓存文件内容。"""
    path = _repo_root() / FAMILY_DIR_NAME[0] / FAMILY_DIR_NAME[1] / f"{family_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"族声明不存在：{path}")
    # 编码口径跟仓库守卫 backend/test_jsonio_single_source.py 一致：读 JSON 必须吃 BOM。
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


def _alias_hits_joint(alias: str, joint_name: str) -> bool:
    """别名是否命中关节名：按**token 段**对齐，不是任意子串。

    * 单 token 别名（`hip`）＝ 该 token 出现在关节名里；
    * 多 token 别名（`hip_pitch` / `hip_abduction`）＝ 这些 token 在关节名里**连续**出现
      （`fl_hip_pitch_joint` 命中；`fl_hip_pitch_link_joint` 不命中）。

    族声明里 `hip_abduction` / `hip_pitch` 这类"角色全名"别名只有在按 token 段对齐时
    才有意义 —— 关节名是按 `_` 分词的，全名永远不是单个 token（2026-09-25 zex-w 上移
    实况：zex-w 的关节就叫 `fl_hip_pitch_joint`，旧口径只能看见 `hip`，把髋俯仰关节
    判成了髋外展）。该口径对 go2w / b2w / m20 的命名（hip / thigh / calf / hipx / hipy）
    与旧口径逐名同解。
    """
    alias_tokens = joint_tokens(alias)
    if not alias_tokens:
        return False
    tokens = joint_tokens(joint_name)
    width = len(alias_tokens)
    return any(
        tuple(tokens[index : index + width]) == alias_tokens
        for index in range(len(tokens) - width + 1)
    )


def role_of_joint(joint_name: str, family_id: str = DEFAULT_FAMILY_ID) -> str | None:
    """按族别名把关节名映射回族角色；映射不到返回 None（调用方决定是否判红）。

    命中口径见 `_alias_hits_joint`；多个角色都命中时**最长的别名优先**：
    `fl_hip_pitch_joint` 同时含 `hip`（髋外展的别名）与 `hip_pitch`（髋俯仰的别名），
    按最长优先判给髋俯仰 —— 按短别名先到先得会把髋俯仰关节判成髋外展（族内"关节名含
    角色全名"的机型会中招，而别名表里本来就登记了这两个全名）。
    """
    best_role: str | None = None
    best_width = 0
    for role, names in role_aliases(family_id).items():
        for name in names:
            width = len(joint_tokens(name))
            if width < best_width or width == 0:
                continue
            if _alias_hits_joint(name, joint_name) and width > best_width:
                best_role, best_width = role, width
    return best_role


def joint_indices_by_role(
    joint_order: tuple[str, ...] | list[str],
    role: str,
    family_id: str = DEFAULT_FAMILY_ID,
) -> tuple[int, ...]:
    """在给定关节序里挑出某个族角色的位置。

    与"每 4 个取 1 个"这种位置假设不同：**位置假设会随腿/角色数变化而错位**，
    而按名字 + 族别名选是声明驱动的 —— 换机型、换角色词表都不用改技能层。

    判据是**解析出来的角色**等于请求的角色（`role_of_joint` 的同一份口径，含"最长别名
    优先"消歧）—— 只看"某别名命中"会把同时含短别名的关节重复挑进两个角色
    （`fl_hip_pitch_joint` 含 `hip`，会同时落进髋外展与髋俯仰）。
    """
    if role not in role_aliases(family_id):
        raise KeyError(f"族 {family_id} 未声明角色 {role}")
    return tuple(
        index
        for index, joint in enumerate(joint_order)
        if role_of_joint(joint, family_id) == role
    )


def leg_of_joint(joint_name: str, leg_ids: tuple[str, ...] | list[str]) -> str | None:
    """关节名 → 腿标记（按契约 `leg_ids` 的前缀匹配）；无前缀返回 None。"""
    text = str(joint_name)
    for leg in leg_ids:
        if text.lower().startswith(f"{str(leg).lower()}{LEG_PREFIX_SEPARATOR}"):
            return str(leg)
    return None


def role_suffix(joint_name: str, leg_ids: tuple[str, ...] | list[str]) -> str:
    """关节名去掉腿前缀后的尾段（`FL_hip_joint` → `hip_joint`）；无前缀则原样。"""
    leg = leg_of_joint(joint_name, leg_ids)
    if leg is None:
        return str(joint_name)
    return str(joint_name)[len(leg) + len(LEG_PREFIX_SEPARATOR) :]


def wheel_role_aliases(family_id: str = DEFAULT_FAMILY_ID) -> tuple[str, ...]:
    """轮角色的族别名（声明驱动；族没声明轮角色就抛错，不静默回落）。"""
    names = role_aliases(family_id).get(WHEEL_ROLE)
    if not names:
        raise ValueError(f"族 {family_id} 未在 role_aliases 里声明 {WHEEL_ROLE!r} 角色")
    return tuple(names)


def wheel_contact_pattern(
    leg_order: tuple[str, ...] | list[str], family_id: str = DEFAULT_FAMILY_ID
) -> str:
    """轮-地接触的主匹配正则：`.*(<腿组>)_(<轮别名|foot>).*`。

    腿组顺序取调用方给的**动作序腿序**（正则候选顺序不影响匹配集合，取动作序是为了
    可复现）；token 组 = 族声明的轮角色别名 + 通用足端 token。
    """
    legs = [str(leg) for leg in leg_order]
    if not legs:
        raise ValueError("轮-地接触匹配需要至少一条腿（leg_order 为空）")
    tokens = list(dict.fromkeys((*wheel_role_aliases(family_id), *WHEEL_CONTACT_TOKENS)))
    return ".*(" + "|".join(legs) + ")_(" + "|".join(tokens) + ").*"
