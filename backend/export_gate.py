"""导出闸门（T0.4 / K3）——DENYLIST fail-closed 语义。

参考：``00_resources/unilab_new/UniLab/utils/sim2sim.py`` 的 DENYLIST/WARNING_LIST
（"sim2sim 需要哪些字段一致"从口头约定变成机器可校验的 manifest，不一致即拒绝）；
go2w_sim2sim 启动时 dummy 前向维度检查；microduck publish 形状冒烟门。

两个 gate：

* **gate ① 形状**：dummy forward 维度检查（导出器结果 input/output shape vs 契约维度）
* **gate ② 数值**：固定输入数值回放（导出器 ``max_numerical_diff < 1e-5``）
* （gate ③ 字段）**契约一致性**：由 :mod:`backend.contract_adjudicator` 统一裁决

**K3 起本模块不再自己实现字段比较**：导出闸门与跨引擎 sim2sim 守卫共用
``backend/contract_adjudicator.adjudicate`` 一处实现，差异只有 ``context`` 标签
（``export`` / ``sim2sim``）。这样"改了导出判据忘了改 sim2sim 判据"这类漂移在结构上
就不可能发生。此处 ``compare_contracts`` 保留原有返回形状（``ok`` / ``blockers`` /
``warnings``）以免打断既有调用方，另附 ``disposition`` / ``entries`` 明细。
"""

from __future__ import annotations

from typing import Any

from backend.contract_adjudicator import (  # noqa: F401  (re-export，兼容既有引用)
    ALLOW,
    DENY,
    DENY_FIELDS,
    WARN,
    WARN_FIELDS,
    adjudicate,
    adjudicate_sim2sim,
    extract_field,
    format_report,
)

#: 旧名保留：调用方/测试曾直接引用这两个常量名
DENYLIST_FIELDS = DENY_FIELDS
WARNING_FIELDS = WARN_FIELDS

REPLAY_DIFF_THRESHOLD = 1e-5


def compare_contracts(
    training_snapshot: dict[str, Any],
    current_contract: dict[str, Any],
) -> dict[str, Any]:
    """训练契约快照 vs 当前契约的字段裁决（导出链路 context=``export``）。

    返回 ``{ok, blockers, warnings, disposition, entries, context}``。
    ``blockers`` 条目为中文三段式原因：发生什么 → 为什么 → 下一步。
    """
    report = adjudicate(training_snapshot, current_contract, context="export")
    return {
        "ok": report["ok"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "disposition": report["disposition"],
        "entries": report["entries"],
        "context": report["context"],
    }


def sim2sim_contract_guard(
    training_snapshot: dict[str, Any],
    target_engine_contract: dict[str, Any],
) -> dict[str, Any]:
    """跨引擎守卫（训练 → 另一引擎）：与导出闸门同一实现，仅 context 不同。"""
    return adjudicate_sim2sim(training_snapshot, target_engine_contract)


def check_export_result(
    result: Any, obs_dim: int, act_dim: int, threshold: float = REPLAY_DIFF_THRESHOLD,
    *, quality: dict[str, Any] | None = None, quality_min: float | None = None,
) -> dict[str, Any]:
    """gate ①+②：导出器结果（dummy 前向形状 + 数值一致性）对照契约维度。

    **gate ③ 质量（B11）**：给了 ``quality``（`backend.quality_matrix` 的报告）就按
    ``quality_min`` 判"达标才放行打包"；判据实现在 `quality_matrix.gate`（一处），
    本函数只是把它的 blockers 并进来 —— 免得"导出闸门"和"质量门"各有一套阈值口径。
    """

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
    quality_verdict = None
    if quality is not None or quality_min is not None:
        from backend.quality_matrix import DEFAULT_MIN_SCORE, gate

        quality_verdict = gate(quality, min_score=quality_min if quality_min is not None else DEFAULT_MIN_SCORE)
        blockers.extend(quality_verdict["blockers"])
    return {"ok": not blockers, "blockers": blockers, "quality": quality_verdict}
