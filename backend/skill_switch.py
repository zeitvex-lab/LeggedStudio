"""感知触发后的**切换动作层**：限速 / 切策略 / 停机（纯函数，可测）。

provider 只负责"看清了什么"（`terrain_class` 等），**不负责"因此做什么"**——把它交给本模块，
好处是切换口径只有一处、且能在没有仿真时单测：

* ``kind: limits``      —— 只改指令上限，无感（策略不用动）；
* ``kind: policy_hint`` —— 建议切到某个策略（如感知跑酷策略）；**该策略不可用时降级为限速并注明**
  （绝不静默当成功——"打算切策略但没切成"是最典型的假象）；
* ``kind: stop``        —— 判定不可通行，安全停机（上限全零）。

浏览器侧真正执行策略切换的是 `web/sim2sim/app.js` 的 `switchPolicy()`（离散切换、会 reset 策略状态）
——代价必须写在结论里，不能假装无缝。
"""

from __future__ import annotations

from typing import Any

#: 指令上限的键（与 `SimulationStepRequest.command` / 场景 `command_limits` 同口径）
LIMIT_KEYS = ("vx", "vy", "wz")


def scale_limits(base_limits: dict[str, float], action: dict[str, Any]) -> dict[str, float]:
    """按动作里的 ``vx_scale`` 缩放上限：**只降不升**（切动作不该放大权限）。"""
    scale = float(action.get("vx_scale", 1.0))
    if scale < 0.0:
        raise ValueError("vx_scale 不能为负")
    scale = min(1.0, scale)
    return {key: round(float(base_limits.get(key, 0.0)) * scale, 6) for key in LIMIT_KEYS}


def plan_switch(
    action: dict[str, Any] | None,
    *,
    base_limits: dict[str, float],
    available_policies: list[str] | None = None,
) -> dict[str, Any]:
    """把 provider 给出的动作描述翻译成可执行的切换决定。

    返回：``{kind, new_limits, policy_id, changed, note}``；``kind`` ∈
    ``none | limits | policy | stop``。
    """
    available = list(available_policies or [])
    limits = {key: float(base_limits.get(key, 0.0)) for key in LIMIT_KEYS}
    if not action:
        return {"kind": "none", "new_limits": limits, "policy_id": None,
                "changed": False, "note": "provider 未给出动作"}

    kind = str(action.get("kind") or "limits")
    if kind == "stop":
        return {"kind": "stop", "new_limits": {key: 0.0 for key in LIMIT_KEYS}, "policy_id": None,
                "changed": True, "note": str(action.get("note") or "判定不可通行，安全停机")}

    new_limits = scale_limits(limits, action)
    changed = new_limits != {key: round(limits[key], 6) for key in LIMIT_KEYS}
    if kind == "policy_hint":
        hint = str(action.get("policy_hint") or "")
        if hint and hint in available:
            return {"kind": "policy", "new_limits": new_limits, "policy_id": hint, "changed": True,
                    "note": f"切换到策略 {hint}（离散切换，策略状态会重置）"}
        return {
            "kind": "limits",
            "new_limits": new_limits,
            "policy_id": None,
            "changed": changed,
            "note": (
                f"建议策略 {hint or '<未声明>'} 不在可用列表 {available}，**降级为限速**"
                "（不静默当作已完成切换）"
            ),
            "degraded_from": "policy_hint",
        }
    return {"kind": "limits", "new_limits": new_limits, "policy_id": None, "changed": changed,
            "note": str(action.get("note") or "按感知结果调整指令上限")}


def evaluate_terrain(
    height_scan,
    *,
    base_limits: dict[str, float],
    available_policies: list[str] | None = None,
    provider=None,
) -> dict[str, Any]:
    """一步到位：高度扫描 → 地形判定 → 切换决定（服务端/工具用；浏览器将来接同一份输出）。"""
    if provider is None:
        from backend.perception_providers import resolve_provider

        provider = resolve_provider("terrain_classifier")
    reading = provider.update(height_scan, 0.0)
    switch = plan_switch(reading.get("action"), base_limits=base_limits, available_policies=available_policies)
    return {"reading": reading, "switch": switch}


def switch_selftest() -> dict[str, Any]:
    """自检：三种动作（限速 / 切策略 / 停机）与"策略不可用时降级"各走一遍。"""
    base = {"vx": 1.0, "vy": 0.5, "wz": 0.8}
    cases = {
        "limits": plan_switch({"kind": "limits", "vx_scale": 0.5}, base_limits=base),
        "policy_available": plan_switch(
            {"kind": "policy_hint", "policy_hint": "perceptive", "vx_scale": 0.5},
            base_limits=base, available_policies=["perceptive", "velocity"],
        ),
        "policy_missing": plan_switch(
            {"kind": "policy_hint", "policy_hint": "perceptive", "vx_scale": 0.5},
            base_limits=base, available_policies=["velocity"],
        ),
        "stop": plan_switch({"kind": "stop"}, base_limits=base),
    }
    ok = (
        cases["limits"]["new_limits"] == {"vx": 0.5, "vy": 0.25, "wz": 0.4}
        and cases["policy_available"]["kind"] == "policy"
        and cases["policy_missing"]["kind"] == "limits"
        and cases["policy_missing"].get("degraded_from") == "policy_hint"
        and cases["stop"]["new_limits"] == {"vx": 0.0, "vy": 0.0, "wz": 0.0}
    )
    return {"success": True, "verdict": "pass" if ok else "fail", "cases": cases}
