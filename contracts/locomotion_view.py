"""B2 契约单轨：把 v2 的粗粒度 ``locomotion_type`` 收敛为 v3 morphology 的**派生视图**。

背景
----
v2 契约用四值枚举 ``locomotion_type`` 描述运动形态：

===================  ==========================================
``P``                四足点足（quadruped, point foot）
``B``                双足（biped）
``W``                轮足（wheel-leg）
``H``                手（hand，非移动构型）
===================  ==========================================

v3 则把它拆成更细的 ``morphology``：``id`` / ``legs`` / ``leg_pattern`` / ``foot_type``
/ ``actuator_type``。两者长期并存并**互相漂移**——实测 ``microduck`` 是 ``legs=2`` 的
双足（``id=biped``、``foot_type=sole``、带踝关节），v2/v3 却都写着 ``P``（=四足点足），
与本机型的真实构型矛盾；而与之同构的 ``limx_tron1_sf`` 正确写着 ``B``。

收敛规则（"保留表达能力更强的一方"）
------------------------------------
* **v3 morphology 是唯一真值**——它能表达"双足 + 足底 + 踝"这种 v2 枚举无法区分的组合
  （``P`` 既表示四足点足，也曾在代码注释里被当作双足的 umbrella）；
* ``locomotion_type`` 退化为**派生视图**，由 :func:`locomotion_type_from_contract` 计算，
  不再单独维护，于是不可能再漂移。

派生优先级
----------
1. ``morphology.id == "hand"``（或没有足端、``legs <= 1``）→ ``H``
2. ``foot_type == "wheel"`` 或 ``leg_pattern`` 含 ``wheel`` → ``W``
3. ``legs == 2`` → ``B``
4. 其余 → ``P``

注意 ``legs=2`` 与 ``foot_type`` 的组合：``sole`` 不改变双足判定（``tron1_sf`` 即为
``B`` + ``sole``），因为该枚举描述的是**运动形态**而非足端材质。

退化行为
--------
未迁移的旧契约（无 ``morphology``）不猜：直接沿用其存量 ``locomotion_type``，缺失才取
``P``。这样既有消费方在迁移完成前后看到同一个值。
"""

from __future__ import annotations

from typing import Any

__all__ = ["LOCOMOTION_ENUM", "locomotion_type_from_contract"]

# v2 兼容枚举（顺序即声明优先级，便于阅读）。
LOCOMOTION_ENUM = ("P", "B", "W", "H")

_DEFAULT = "P"


def locomotion_type_from_contract(contract: dict[str, Any]) -> str:
    """由 v3 ``morphology`` 派生 v2 兼容的 ``locomotion_type``。

    非 dict（含 None）或缺少 ``morphology`` 时，退化为该契约自身的存量值。
    """

    if not isinstance(contract, dict):
        return _DEFAULT
    morphology = contract.get("morphology")
    if not isinstance(morphology, dict) or not morphology:
        stored = contract.get("locomotion_type")
        return stored if stored in LOCOMOTION_ENUM else _DEFAULT

    morphology_id = str(morphology.get("id") or "")
    pattern = [str(role) for role in (morphology.get("leg_pattern") or [])]
    foot_type = morphology.get("foot_type")
    try:
        legs = int(morphology.get("legs") or 0)
    except (TypeError, ValueError):
        legs = 0

    if morphology_id == "hand" or foot_type is None and legs <= 1:
        return "H"
    if foot_type == "wheel" or "wheel" in pattern:
        return "W"
    if legs == 2:
        return "B"
    if legs > 2:
        return "P"
    stored = contract.get("locomotion_type")
    return stored if stored in LOCOMOTION_ENUM else _DEFAULT
