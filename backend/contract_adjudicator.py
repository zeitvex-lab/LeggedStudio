"""契约一致性裁决器（K3）——**一次实现，两条链路复用**。

两条链路本来各有一套判据：

* **导出链路（训练 → 部署）**：``backend/export_gate.py`` 的 DENYLIST/WARNING 字段比较；
* **sim2sim 链路（训练 → 另一个引擎）**：此前只有性能数值对比（
  ``tools/sim2sim_validator.py``），**没有字段一致性判据**——换了引擎却没人比对
  「关节序 / action_scale / 观测组 / 控制频率 / 执行器指纹」是否还是同一份契约。

两者要回答的其实是同一个问题：「**源侧那份契约与目标侧这份契约，是不是一回事**」，
所以合并成一个裁决器，只换 ``context`` 标签：

三档处置（每条字段一个）：

* ``deny``  —— 不一致且属于硬约束（DENYLIST）→ 拒绝；
* ``warn``  —— 不一致但可接受（WARNING_LIST）→ 放行 + 提示；
* ``allow`` —— 一致。

**不对称出现 fail-closed**（K3 的关键新增）：一侧有值、另一侧没有，说明**无法验证**
而非「没问题」。旧实现把这种情况降级成 warning 后继续放行——那等于把最危险的
情况（换了引擎/换了契约导致字段对不上）当成安全。现在只要 DENYLIST 字段不对称
即 deny；两边都缺才算「该字段与本契约无关」，记 warning 不阻断。

报告每条目固定五要素：**字段 / 源值 / 目标值 / 处置 / 依据**（依据 = 规则 id，
形如 ``DENYLIST#action.action_scale`` 或 ``ASYMMETRY_FAIL_CLOSED#control.control_hz``），
来源可追溯到 ``00_resources/unilab_new/UniLab/utils/sim2sim.py`` 的 DENYLIST 语义。
"""

from __future__ import annotations

from typing import Any

#: 硬约束字段：不一致即 deny
DENY_FIELDS: tuple[str, ...] = (
    "action.joint_order",
    "action.action_scale",
    "action.reindex_from_model",
    "observation.components",
    "observation.dimension",
    "control.control_hz",
    "actuator_profile",
)
#: 软约束字段：不一致仅 warn
WARN_FIELDS: tuple[str, ...] = (
    "reward_scales",
    "control.decimation",
    "control.physics_hz",
)

#: v3 才引入的字段：v2（robot-contract-2.0）快照**从未记录过**它们。
#: v2 侧缺这些字段 = 格式边界（当时的 schema 装不下这个声明），不是漂移证据
#: ——按 SCHEMA_BOUNDARY 降 warn；v3 侧缺 = 契约漂移，照旧 deny。
V3_ONLY_FIELDS: tuple[str, ...] = (
    "actuator_profile",
    "action.reindex_from_model",
)
LEGACY_SCHEMA_VERSIONS: frozenset[str] = frozenset({"robot-contract-2.0"})

DENY = "deny"
WARN = "warn"
ALLOW = "allow"

#: 处置严重度（用于汇总整体结论）
_SEVERITY = {ALLOW: 0, WARN: 1, DENY: 2}

#: 链路标签（只影响报告可读性，不影响判据——这正是"合并"的意义）
CONTEXT_LABELS = {
    "export": "训练 → 部署（导出闸门）",
    "sim2sim": "训练 → 另一引擎（跨引擎守卫）",
}


class _MissingType:
    """「字段未声明」的哨兵。

    必须与 ``None`` 区分开：``action.reindex_from_model = null`` 是**显式取值**
    （表示恒等映射），而"键不存在"才是未声明。二者混为一谈会让「两侧都是 null」
    被误报成"无法强校验"，也检测不出「一侧 null、一侧真是映射表」这种不对称。
    """

    _instance: "_MissingType | None" = None

    def __new__(cls) -> "_MissingType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<缺失>"

    def __bool__(self) -> bool:  # pragma: no cover - 防止被当普通值误用
        return False


MISSING = _MissingType()


def _jsonable(value: Any) -> Any:
    """报告里把哨兵渲染成可读文本（其余值原样保留，便于机器消费）。"""
    return "<缺失>" if value is MISSING else value


# ---------------------------------------------------------------------------
# 字段提取
# ---------------------------------------------------------------------------
def _obs_components(contract: dict[str, Any]) -> Any:
    """obs_groups 有序表：v3 用 components[name,width]；v2 退化为段名字符串表。

    v2 格式**有声明**（只是没宽度）——返回段名表而非 MISSING；把"格式旧"当
    "未声明"曾让全部 v2 快照在 components 上误判不对称（2026-10-03 部署门禁
    9 包全 deny 的根因）。
    """
    observation = contract.get("observation")
    if not isinstance(observation, dict):
        return MISSING
    components = observation.get("components")
    if isinstance(components, list) and components:
        names: list[str] = []
        pairs: list[tuple[str, int]] = []
        for component in components:
            if isinstance(component, str):
                names.append(component)
                continue
            if not isinstance(component, dict) or "name" not in component or "width" not in component:
                return MISSING
            pairs.append((str(component["name"]), int(component["width"])))
        if pairs and not names:
            return pairs
        if names and not pairs:
            return names
        return MISSING  # 混合形态 = 契约自身不合法，不猜
    dimension = observation.get("dimension")
    if isinstance(dimension, int) and dimension > 0:
        return [("(dimension)", dimension)]
    return MISSING


def _actuator_fingerprint(contract: dict[str, Any]) -> Any:
    """执行器指纹（关注物理量：mode/effort/armature/stiffness/damping/action_scale）。

    契约带 ``joints.actuated`` 时按角色展开到逐关节；快照缺关节表（早期训练快照）
    时退化为角色表指纹，仍能发现漂移。
    """
    profile = contract.get("actuator_profile")
    if not isinstance(profile, dict) or not profile:
        return MISSING

    def pick(params: dict[str, Any]) -> dict[str, Any]:
        return {
            key: params.get(key)
            # B5：action_scale 并入指纹——否则"改了角色级档位"会绕过闸门
            for key in ("mode", "effort", "armature", "stiffness", "damping", "action_scale")
            if params.get(key) is not None
        }

    joints = (contract.get("joints") or {}).get("actuated") or []
    if joints:
        try:
            from contracts.role_resolver import RoleResolver

            expanded = RoleResolver(contract).expand_actuator_profile()
        except Exception:
            return MISSING
        return {joint: pick(params) for joint, params in expanded.items()}
    return {"(by_role)": {role: pick(params) for role, params in (profile.get("by_role") or {}).items()}}


def extract_field(contract: dict[str, Any], field: str) -> Any:
    """按字段名取可比较的值；键不存在时返回 :data:`MISSING`（显式 ``null`` 仍是 ``None``）。"""
    if field == "observation.components":
        return _obs_components(contract)
    if field == "actuator_profile":
        return _actuator_fingerprint(contract)
    node: Any = contract
    for part in field.split("."):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    if node is None:
        return None
    if field == "action.joint_order" and isinstance(node, list):
        return [str(item) for item in node]
    return node


# ---------------------------------------------------------------------------
# 裁决
# ---------------------------------------------------------------------------
def _entry(
    field: str,
    source_value: Any,
    target_value: Any,
    disposition: str,
    reason: str,
    basis: str,
) -> dict[str, Any]:
    return {
        "field": field,
        "source_value": _jsonable(source_value),
        "target_value": _jsonable(target_value),
        "disposition": disposition,
        "reason": reason,
        "basis": basis,
    }


def _brief(value: Any, limit: int = 160) -> str:
    """把值渲染成短摘要（进 ``blockers`` 文本用，完整值在 ``entries`` 里）。"""
    text = repr(_jsonable(value))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _diff_paths(source: Any, target: Any, prefix: str = "") -> list[str]:
    """递归收集不一致的叶子路径，形如 ``calf.armature: 0.01 → 0.03``。

    执行器指纹这类嵌套 dict 直接 repr 会既冗长又读不出"差在哪"，所以按路径下钻；
    文本必须能点出具体关节名，否则报告等于没说。
    """
    if isinstance(source, dict) and isinstance(target, dict):
        paths: list[str] = []
        for key in sorted(set(source) | set(target)):
            paths.extend(_diff_paths(source.get(key, MISSING), target.get(key, MISSING), f"{prefix}{key}."))
        return paths
    if isinstance(source, (list, tuple)) and isinstance(target, (list, tuple)):
        if len(source) != len(target):
            return [f"{prefix.rstrip('.')}: 长度 {len(source)} → {len(target)}"]
        paths = []
        for index, (left, right) in enumerate(zip(source, target)):
            paths.extend(_diff_paths(left, right, f"{prefix}{index}."))
        return paths
    label = prefix.rstrip(".") or "值"
    return [f"{label}: {_brief(source, 40)} → {_brief(target, 40)}"]


def _difference_summary(source: Any, target: Any, limit: int = 6) -> str:
    """不一致的可读摘要（最多列 ``limit`` 条路径，超出即注明）。"""
    paths = _diff_paths(source, target)
    if not paths:
        return f"{_brief(source, 60)} → {_brief(target, 60)}"
    shown = "；".join(paths[:limit])
    if len(paths) > limit:
        shown += f"；…（共 {len(paths)} 处）"
    return shown


def _next_step(field: str, context: str) -> str:
    if context == "sim2sim":
        return "请在目标引擎下用同一份契约重建场景，或回到训练区按该契约重训后再跨引擎验证"
    return "请回训练区用当前契约重训，或恢复契约后重试"


def _is_names_only(value: Any) -> bool:
    """components 值是否 v2 段名表（纯字符串列表）——决定比较是否退化为按名。"""
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) for item in value)


def _obs_names(value: Any) -> Any:
    """components 比较的归一投影：段名序列（一侧为 v2 无宽度格式时按名比对）。

    两侧都是 (name,width) 对 = 严格比对（宽度漂移照样抓）；任一侧只有段名
    （v2 字符串表）= 退化成段名序比对——宽度在旧快照里**没记录过**，能验证的
    最强声明就是"段与序一致"。
    """
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, list) and value and all(isinstance(item, (list, tuple)) for item in value):
        return [item[0] for item in value]
    return value


def _is_legacy_snapshot(doc: dict[str, Any]) -> bool:
    """文档是否 v2 格式快照（v3-only 字段在其 schema 里从未存在过）。"""
    return isinstance(doc, dict) and doc.get("schema_version") in LEGACY_SCHEMA_VERSIONS


def adjudicate(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    context: str = "export",
    deny_fields: tuple[str, ...] = DENY_FIELDS,
    warn_fields: tuple[str, ...] = WARN_FIELDS,
) -> dict[str, Any]:
    """逐字段裁决源契约与目标契约，返回带五要素条目的报告。

    Args:
        source: 源侧契约快照（如训练时的 ``contract_snapshot``）。
        target: 目标侧契约（当前部署契约 / 另一引擎的契约）。
        context: ``"export"`` 或 ``"sim2sim"``——同一套判据，仅用于报告与措辞。
    """
    if context not in CONTEXT_LABELS:
        raise ValueError(f"未知 context {context!r}（可选 {sorted(CONTEXT_LABELS)}）")

    entries: list[dict[str, Any]] = []

    for field in deny_fields:
        source_value = extract_field(source, field)
        target_value = extract_field(target, field)
        if source_value is MISSING and target_value is MISSING:
            entries.append(
                _entry(field, source_value, target_value, WARN,
                       f"{field} 两侧均未声明——该字段与本契约无关，未能纳入强校验",
                       f"BOTH_MISSING#{field}")
            )
            continue
        if source_value is MISSING or target_value is MISSING:
            present, missing_side = ("源", "目标") if target_value is MISSING else ("目标", "源")
            missing_doc = target if target_value is MISSING else source
            if field in V3_ONLY_FIELDS and _is_legacy_snapshot(missing_doc):
                entries.append(
                    _entry(field, source_value, target_value, WARN,
                           f"{field} {missing_side}侧未声明，但该侧是 v2 格式快照"
                           f"（schema_version={missing_doc.get('schema_version')}）——"
                           f"v2 从未记录过此字段，无法验证属格式边界而非漂移证据；"
                           f"如需强校验请用 v3 契约重导出训练快照",
                           f"SCHEMA_BOUNDARY#{field}")
                )
                continue
            entries.append(
                _entry(field, source_value, target_value, DENY,
                       f"{field} 不对称：{present}侧有值而{missing_side}侧未声明——无法验证即视为不一致"
                       f"（fail-closed），{_next_step(field, context)}",
                       f"ASYMMETRY_FAIL_CLOSED#{field}")
            )
            continue
        if field == "observation.components" and (
            _is_names_only(source_value) or _is_names_only(target_value)
        ):
            # 一侧是 v2 段名表：按段名序比对（宽度在旧快照里没记录过）
            if _obs_names(source_value) != _obs_names(target_value):
                entries.append(
                    _entry(field, source_value, target_value, DENY,
                           f"{field} 不一致（{_difference_summary(_obs_names(source_value), _obs_names(target_value))}）"
                           f"——按段名序比对（一侧为 v2 无宽度格式）；{_next_step(field, context)}",
                           f"DENYLIST#{field}")
                )
            else:
                entries.append(
                    _entry(field, source_value, target_value, ALLOW,
                           f"{field} 段名序一致（一侧为 v2 无宽度格式，宽度不纳入比对）",
                           f"DENYLIST#{field}")
                )
            continue
        if source_value != target_value:
            entries.append(
                _entry(field, source_value, target_value, DENY,
                       f"{field} 不一致（{_difference_summary(source_value, target_value)}）"
                       f"——{CONTEXT_LABELS[context]}要求该字段严格一致，"
                       f"按 DENYLIST 语义拒绝；{_next_step(field, context)}",
                       f"DENYLIST#{field}")
            )
        else:
            entries.append(_entry(field, source_value, target_value, ALLOW, f"{field} 一致", f"DENYLIST#{field}"))

    for field in warn_fields:
        source_value = extract_field(source, field)
        target_value = extract_field(target, field)
        if source_value is MISSING and target_value is MISSING:
            entries.append(
                _entry(field, source_value, target_value, ALLOW,
                       f"{field} 两侧均未声明（{CONTEXT_LABELS[context]}不强制该字段）",
                       f"BOTH_MISSING#{field}")
            )
            continue
        if source_value is MISSING or target_value is MISSING:
            # 软约束字段不对称只提示：它们本就不该阻断放行
            entries.append(
                _entry(field, source_value, target_value, WARN,
                       f"{field} 不对称（一侧未声明）——无法比较，本次不阻断",
                       f"ASYMMETRY_WARN#{field}")
            )
            continue
        if source_value != target_value:
            entries.append(
                _entry(field, source_value, target_value, WARN,
                       f"{field} 不一致（{_difference_summary(source_value, target_value)}）"
                       f"——不影响本次放行，但请注意 sim2real 表现差异",
                       f"WARNING_LIST#{field}")
            )
        else:
            entries.append(_entry(field, source_value, target_value, ALLOW, f"{field} 一致", f"WARNING_LIST#{field}"))

    blockers = [item["reason"] for item in entries if item["disposition"] == DENY]
    warnings = [item["reason"] for item in entries if item["disposition"] == WARN]
    overall = max((item["disposition"] for item in entries), key=lambda d: _SEVERITY[d], default=ALLOW)
    return {
        "ok": not blockers,
        "disposition": overall,
        "context": context,
        "context_label": CONTEXT_LABELS[context],
        "entries": entries,
        "blockers": blockers,
        "warnings": warnings,
        "counts": {
            "deny": len(blockers),
            "warn": len(warnings),
            "allow": sum(1 for item in entries if item["disposition"] == ALLOW),
        },
    }


def adjudicate_sim2sim(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """跨引擎（sim2sim）守卫：与导出闸门**同一实现**，仅 context 不同。"""
    return adjudicate(source, target, context="sim2sim")


def format_report(report: dict[str, Any]) -> str:
    """把报告渲染成可读表格（工具/日志用；五要素齐全）。"""
    lines = [
        f"[契约裁决] {report['context_label']} → 处置 {report['disposition'].upper()}"
        f"（deny {report['counts']['deny']} / warn {report['counts']['warn']} / allow {report['counts']['allow']}）",
        "| 字段 | 源值 | 目标值 | 处置 | 依据 |",
        "|---|---|---|---|---|",
    ]
    for item in report["entries"]:
        lines.append(
            f"| `{item['field']}` | `{item['source_value']}` | `{item['target_value']}` | "
            f"{item['disposition']} | `{item['basis']}` |"
        )
    return "\n".join(lines)


def adjudicator_selftest() -> dict[str, Any]:
    """离线自检：一致/不一致/不对称/双侧缺失 四种情形的处置是否符合三档语义。"""
    base = {
        "action": {"joint_order": ["a", "b"], "action_scale": 0.25, "reindex_from_model": None},
        "observation": {"dimension": 6},
        "control": {"control_hz": 50, "decimation": 10},
        "actuator_profile": {"by_role": {"hip": {"armature": 0.01, "effort": 20.0}}},
        "reward_scales": {"track": 1.0},
    }
    cases: list[dict[str, Any]] = []

    def case(name: str, ok: bool, detail: dict[str, Any]) -> None:
        cases.append({"name": name, "ok": bool(ok), **detail})

    identical = adjudicate(base, dict(base))
    case("identical_contracts_allow", identical["disposition"] == ALLOW and identical["ok"], {"disposition": identical["disposition"]})

    drifted = {**base, "action": {**base["action"], "action_scale": 0.5}}
    drift = adjudicate(base, drifted)
    case(
        "denylist_drift_denies_with_five_elements",
        drift["disposition"] == DENY
        and set(drift["entries"][0]) >= {"field", "source_value", "target_value", "disposition", "basis", "reason"},
        {"first_entry": drift["entries"][0]},
    )

    # 源侧有 joint_order 但完全没有 action_scale → 该字段不对称，应 fail-closed
    asymmetric = adjudicate({"action": {"joint_order": ["a", "b"]}}, base)
    case(
        "asymmetric_denylist_is_fail_closed",
        asymmetric["disposition"] == DENY
        and any(item["basis"].startswith("ASYMMETRY_FAIL_CLOSED#action.action_scale") for item in asymmetric["entries"]),
        {"deny_bases": [item["basis"] for item in asymmetric["entries"] if item["disposition"] == DENY]},
    )

    warn_only = adjudicate(base, {**base, "reward_scales": {"track": 2.0}})
    case(
        "warning_field_only_warns",
        warn_only["ok"] and warn_only["disposition"] == WARN,
        {"blockers": warn_only["blockers"], "warnings": warn_only["warnings"]},
    )

    export = adjudicate(base, drifted, context="export")
    sim2sim = adjudicate_sim2sim(base, drifted)
    case(
        "one_implementation_two_contexts",
        [item["disposition"] for item in export["entries"]] == [item["disposition"] for item in sim2sim["entries"]]
        and export["context"] != sim2sim["context"],
        {"export_disposition": export["disposition"], "sim2sim_disposition": sim2sim["disposition"]},
    )

    unknown_context = False
    try:
        adjudicate(base, base, context="unknown")
    except ValueError:
        unknown_context = True
    case("unknown_context_rejected", unknown_context, {})

    failures = [item["name"] for item in cases if not item["ok"]]
    return {
        "success": True,
        "deny_fields": list(DENY_FIELDS),
        "warn_fields": list(WARN_FIELDS),
        "cases": cases,
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
    }
