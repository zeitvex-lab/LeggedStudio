"""导出双 gate（T0.4）——DENYLIST fail-closed 语义，照抄 UniLab sim2sim 契约思想。

参考：unilab_new/UniLab ``utils/sim2sim.py`` 的 DENYLIST/WARNING_LIST
（00_Survey 报告 7 §3/§5——"sim2sim 需要哪些字段一致"从口头约定变成机器可校验
manifest，不一致即拒绝，不用发明）；go2w_sim2sim 启动时 dummy 前向维度检查
（报告 2 §5）；microduck publish 形状冒烟门（报告 4 §3）。

两个 gate：
  gate ① 形状：dummy forward 维度检查（导出器结果 input/output shape vs 契约维度）
  gate ② 数值：固定输入数值回放（导出器 max_numerical_diff < 1e-5）

DENYLIST（不一致 = 拒绝导出）：
    action.joint_order / action.action_scale / action.reindex_from_model /
    observation.components（obs_groups：名称+宽度有序表）/ observation.dimension /
    control.control_hz / actuator_profile（角色展开后的逐关节 armature/effort/mode）
WARNING（不一致 = 仅警告）：
    reward_scales / control.decimation·physics_hz（ctrl_dt）

快照缺字段时降级为 warning（"无法强校验"）——T0.5 起 run_config 写入
contract_snapshot 后自动收紧为强校验。
"""

from __future__ import annotations

from typing import Any

REPLAY_DIFF_THRESHOLD = 1e-5

# DENYLIST 字段 → 比较键提取器（None = 两边都无法提取，跳过并记 warning）
DENYLIST_FIELDS = (
    "action.joint_order",
    "action.action_scale",
    "action.reindex_from_model",
    "observation.components",
    "observation.dimension",
    "control.control_hz",
    "actuator_profile",
)
WARNING_FIELDS = (
    "reward_scales",
    "control.decimation",
    "control.physics_hz",
)


def _nested(data: dict[str, Any], path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _obs_components(contract: dict[str, Any]) -> list[tuple[str, int]] | None:
    """obs_groups 有序表：v3 components[name,width]；v2 退化为 [dimension]。"""

    observation = contract.get("observation") or {}
    components = observation.get("components")
    if isinstance(components, list) and components:
        pairs: list[tuple[str, int]] = []
        for component in components:
            if not isinstance(component, dict) or "name" not in component or "width" not in component:
                return None
            pairs.append((str(component["name"]), int(component["width"])))
        return pairs
    dimension = observation.get("dimension")
    if isinstance(dimension, int) and dimension > 0:
        return [("(dimension)", dimension)]
    return None


def _actuator_fingerprint(contract: dict[str, Any]) -> dict[str, Any] | None:
    """执行器指纹（armature/effort/mode 优先——DENYLIST 关注物理）。

    契约带 joints.actuated 时按角色展开到逐关节；快照缺关节表（早期训练快照）
    时退化为角色表指纹，仍可发现漂移。
    """

    profile = contract.get("actuator_profile")
    if not isinstance(profile, dict) or not profile:
        return None

    def pick(params: dict[str, Any]) -> dict[str, Any]:
        return {
            key: params.get(key)
            for key in ("mode", "effort", "armature", "stiffness", "damping")
            if params.get(key) is not None
        }

    joints = (contract.get("joints") or {}).get("actuated") or []
    if joints:
        try:
            from contracts.role_resolver import RoleResolver

            expanded = RoleResolver(contract).expand_actuator_profile()
        except Exception:
            return None
        fingerprint: dict[str, Any] = {joint: pick(params) for joint, params in expanded.items()}
    else:
        fingerprint = {
            "(by_role)": {role: pick(params) for role, params in (profile.get("by_role") or {}).items()}
        }
    return fingerprint


def _extract(contract: dict[str, Any], field: str) -> Any:
    if field == "observation.components":
        return _obs_components(contract)
    if field == "actuator_profile":
        return _actuator_fingerprint(contract)
    value = _nested(contract, field)
    if value is None:
        return None
    if field == "action.joint_order" and isinstance(value, list):
        return [str(item) for item in value]
    return value


def _diff(training: Any, current: Any) -> str | None:
    """返回不一致的可读描述；一致返回 None。"""

    if training is None or current is None:
        return None
    if training != current:
        return f"训练 {training!r} vs 当前 {current!r}"
    return None


def compare_contracts(
    training_snapshot: dict[str, Any], current_contract: dict[str, Any]
) -> dict[str, Any]:
    """DENYLIST/WARNING 比较。返回 {ok, blockers, warnings}。

    blocker 条目为中文三段式原因：发生什么 → 为什么 → 下一步。
    """

    blockers: list[str] = []
    warnings: list[str] = []
    unverifiable: list[str] = []

    for field in DENYLIST_FIELDS:
        training = _extract(training_snapshot, field)
        current = _extract(current_contract, field)
        if training is None or current is None:
            unverifiable.append(field)
            continue
        difference = _diff(training, current)
        if difference:
            blockers.append(
                f"{field} 不一致（{difference}）——策略与当前机器人契约已漂移，"
                f"按 DENYLIST 语义拒绝导出；请回训练区用当前契约重训，或恢复契约后重试"
            )
    for field in WARNING_FIELDS:
        training = _extract(training_snapshot, field)
        current = _extract(current_contract, field)
        if training is None or current is None:
            continue
        difference = _diff(training, current)
        if difference:
            warnings.append(f"{field} 不一致（{difference}）——不影响导出，但请注意 sim2real 表现")
    for field in unverifiable:
        warnings.append(
            f"{field} 无法强校验（训练快照或当前契约缺少该字段）——"
            f"T0.5 起 run_config 将固化 contract_snapshot"
        )
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings}


def check_export_result(
    result: Any, obs_dim: int, act_dim: int, threshold: float = REPLAY_DIFF_THRESHOLD
) -> dict[str, Any]:
    """gate ①+②：导出器结果（dummy 前向形状 + 数值一致性）对照契约维度。"""

    blockers: list[str] = []
    input_shape = list(getattr(result, "input_shape", None) or [])
    output_shape = list(getattr(result, "output_shape", None) or [])
    if input_shape and int(input_shape[-1]) != int(obs_dim):
        blockers.append(
            f"dummy forward 输入维度 {input_shape[-1]} != 契约 obs_dim {obs_dim}"
            "——观测组漂移，请检查 observation.components 后重新导出"
        )
    if output_shape and int(output_shape[-1]) != int(act_dim):
        blockers.append(
            f"dummy forward 输出维度 {output_shape[-1]} != 契约 action_dim {act_dim}"
            "——动作槽漂移，请检查 action.joint_order 后重新导出"
        )
    max_diff = getattr(result, "max_numerical_diff", None)
    if max_diff is not None and float(max_diff) >= threshold:
        blockers.append(
            f"数值回放 max|Δ|={max_diff:.3e} >= 阈值 {threshold:.0e}"
            "——'验收通过但回放不通过 = 没学会'，请检查导出图与 normalizer bake-in"
        )
    return {"ok": not blockers, "blockers": blockers}
