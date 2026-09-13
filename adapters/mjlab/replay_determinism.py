"""确定性回放判据（L1 / G2）——「两次逐帧一致」的**唯一判定实现**。

**为什么需要它**：`deterministic_replay` 能力目前只能记 `partial`，因为"两次跑同一策略
是否逐帧一致"这件事**没有判据**——只有 `adapters/mjlab/replay_diff.py` 那种人肉比对的
诊断脚本（浏览器 vs 桌面，阈值 0.05 硬编码）。没有判据，"回放不通过 = 没学会"就写不进页面。

**判据口径（两条，别混）**：

1. **同执行器重跑**（同一浏览器 / 同一无头引擎，同 seed 同指令）⇒ 默认容差 **0**
   —— MuJoCo 给定相同输入是确定性的，不一致就是真不一致（浮点也不该差）。
   参考实现：`00_resources/newton/newton/tests/determinism/test_solver_determinism.py`
   （同 solver 跑两遍比对 / 子进程隔离跑，判据是"轨迹逐点相同"）。
2. **跨执行器比对**（浏览器 WASM vs 桌面原生；`replay_diff.py` 的用法）⇒ 显式传容差
   （例如 0.05），因为两条实现路径的浮点行为本就不同，此时判的是"链路一致"而非"确定性"。

帧格式（与 `web/sim2sim/app.js` 的 `frameLog` 对齐，也接受无头引擎产出的同形日志）：

    [{"t": 0.02, "stepIndex": 1, "obs": [...], "action": [...], "ctrlBefore": [...]}, ...]

`stepIndex` 存在时按它对齐（不同执行器的墙钟不同，只能靠控制步序号对齐）。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

#: 同执行器重跑的默认容差：**必须逐位一致**
DEFAULT_TOLERANCE = 0.0
#: 跨执行器（WASM vs 原生）诊断用容差，与 replay_diff.py 既有口径一致
CROSS_EXECUTOR_TOLERANCE = 0.05


def _frames(log: Any) -> list[dict[str, Any]]:
    """接受三种输入：裸列表 / ``{"frames": [...]}`` / ``{"frame_log": [...]}``。"""
    if isinstance(log, dict):
        for key in ("frames", "frame_log", "frameLog"):
            value = log.get(key)
            if isinstance(value, list):
                return [f for f in value if isinstance(f, dict)]
        raise ValueError("frame log 里找不到 frames/frame_log 数组")
    if isinstance(log, list):
        return [f for f in log if isinstance(f, dict)]
    raise ValueError(f"无法解析 frame log（类型 {type(log).__name__}）")


def _obs(frame: dict[str, Any], key: str) -> list[float]:
    value = frame.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"帧缺少数值数组字段 {key!r}")
    return [float(x) for x in value]


def compare_frame_logs(
    log_a: Any,
    log_b: Any,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    obs_key: str = "obs",
    step_key: str = "stepIndex",
) -> dict[str, Any]:
    """逐帧逐维比对两份日志，返回结构化结论（不改动任何一侧）。

    返回：
        ``{verdict, reason, frames_compared, skipped, alignment, tolerance,
           max_delta, first_divergence, length_mismatch}``

    * ``verdict``：``"pass"`` / ``"fail"``；
    * ``reason``：失败原因（``"obs_divergence"`` / ``"length_mismatch"`` /
      ``"step_index_missing"`` / ``"empty"``）；
    * ``first_divergence``：最早不一致的帧与维度（含两侧取值与差值），便于直接定位。
    """
    frames_a, frames_b = _frames(log_a), _frames(log_b)
    if not frames_a or not frames_b:
        return {
            "verdict": "fail", "reason": "empty", "frames_compared": 0, "skipped": 0,
            "alignment": "none", "tolerance": float(tolerance), "max_delta": None,
            "first_divergence": None, "length_mismatch": None,
        }

    has_index = all(step_key in f for f in frames_a) and all(step_key in f for f in frames_b)
    alignment = "step_index" if has_index else "position"
    skipped: list[Any] = []
    if has_index:
        index_b = {int(f[step_key]): f for f in frames_b}
        pairs = []
        for frame in frames_a:
            idx = int(frame[step_key])
            if idx in index_b:
                pairs.append((frame, index_b[idx]))
            else:
                skipped.append(idx)
    else:
        pairs = list(zip(frames_a, frames_b))

    length_mismatch = None
    if len(frames_a) != len(frames_b):
        length_mismatch = {"a": len(frames_a), "b": len(frames_b)}

    max_delta = 0.0
    mismatched_frames = 0
    first_divergence = None
    for position, (frame_a, frame_b) in enumerate(pairs):
        obs_a, obs_b = _obs(frame_a, obs_key), _obs(frame_b, obs_key)
        if len(obs_a) != len(obs_b):
            first_divergence = first_divergence or {
                "position": position,
                "step_index": int(frame_a.get(step_key, position)) if has_index else position,
                "reason": "obs_dim_mismatch",
                "dim_a": len(obs_a),
                "dim_b": len(obs_b),
            }
            mismatched_frames += 1
            continue
        worst_dim, worst_delta = -1, 0.0
        for dim, (value_a, value_b) in enumerate(zip(obs_a, obs_b)):
            delta = abs(value_a - value_b)
            if delta > worst_delta:
                worst_dim, worst_delta = dim, delta
        if worst_delta > max_delta:
            max_delta = worst_delta
        if worst_delta > float(tolerance):
            mismatched_frames += 1
            if first_divergence is None:
                first_divergence = {
                    "position": position,
                    "step_index": int(frame_a.get(step_key, position)) if has_index else position,
                    "dim": worst_dim,
                    "a": obs_a[worst_dim],
                    "b": obs_b[worst_dim],
                    "delta": worst_delta,
                    "reason": "obs_divergence",
                }

    verdict = "pass"
    reason = "identical"
    if length_mismatch is not None:
        verdict, reason = "fail", "length_mismatch"
    elif first_divergence is not None:
        verdict, reason = "fail", first_divergence.get("reason", "obs_divergence")

    return {
        "verdict": verdict,
        "reason": reason,
        "frames_compared": len(pairs),
        "skipped": skipped,
        "alignment": alignment,
        "tolerance": float(tolerance),
        "max_delta": max_delta,
        "mismatched_frames": mismatched_frames,
        "first_divergence": first_divergence,
        "length_mismatch": length_mismatch,
    }


def determinism_verdict(
    log_a: Any,
    log_b: Any,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    min_frames: int = 1,
) -> dict[str, Any]:
    """同执行器重跑的判定（默认容差 0），并额外要求"至少比够 min_frames 帧"。

    **为什么要有 min_frames**：只比 1-2 帧的"一致"没有说服力（还没走出初始态）。
    默认 1 帧只为兼容手工快速验证；门禁应显式给一个有意义的下限（如 50 帧）。
    """
    result = compare_frame_logs(log_a, log_b, tolerance=tolerance)
    if result["verdict"] == "pass" and result["frames_compared"] < int(min_frames):
        result = {
            **result,
            "verdict": "fail",
            "reason": "too_few_frames",
            "required_frames": int(min_frames),
        }
    result["min_frames"] = int(min_frames)
    return result


def summarize(result: dict[str, Any]) -> str:
    """一行摘要（CLI 用）。"""
    if result.get("verdict") == "pass":
        return (
            f"PASS · 逐帧一致（{result['frames_compared']} 帧，对齐 {result['alignment']}，"
            f"容差 {result['tolerance']}，max_delta={result['max_delta']:.3g}）"
        )
    first = result.get("first_divergence") or {}
    detail = (
        f"stepIndex={first.get('step_index')} dim={first.get('dim')} "
        f"a={first.get('a')} b={first.get('b')} Δ={first.get('delta')}"
        if first.get("dim") is not None
        else f"{first or result.get('length_mismatch')}"
    )
    return (
        f"FAIL · {result.get('reason')}（比对 {result['frames_compared']} 帧，"
        f"首个发散：{detail}）"
    )


def iter_obs_rows(log: Iterable[dict[str, Any]], obs_key: str = "obs") -> list[list[float]]:
    """辅助：把帧日志摊平为 obs 行（外部工具复用，避免各自解析）。"""
    return [_obs(frame, obs_key) for frame in _frames(list(log))]
