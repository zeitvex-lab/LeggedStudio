"""冒烟前置门（E8）：**未过冒烟不能长训**。

## 为什么需要这道门

长训是 GPU 分钟到小时级；而配置错误（观测维度不符、历史布局不对、依赖缺失、资产缺件）
在**冒烟档**（64 envs × 5 iters）几十秒内就会暴露。不设门就会出现"跑了 40 分钟才发现
`obs_dim` 错"——本仓反复踩过的正是这一类：**错在配置，却被读成"策略不行"**。

## 证据从哪来（**不另造记录**）

冒烟"通过"的证据＝**已有事实的组合**：

* ``task_dir/resolved-config.json``（B9 落的 Run 档案）里的 ``inputs.digest`` —— 输入指纹；
  同指纹 = 同机器人 + 同契约 + 同 recipe + 同 profile + 同 seed + **同整份 config**；
* ``resolved.inputs.params.smoke_preset`` 为真 —— 那次是冒烟档；
* 该任务状态为 ``completed``（词表取自 `TrainingManager`）。

于是证据可审计、可复算；而且**配置改一个字就会派生新指纹** → "沿用上次的冒烟结论"
在结构上不可能发生（这正是把门挂在 B9 指纹上的价值）。

## 门开在哪一层

挂在 **HTTP 请求层**（`backend/training/create.py`）而不是 `TrainingManager.create_task`：
``smoke_preset`` 这个语义只在请求层存在；且直接调 manager 的调用方（测试/脚本）
不该被门拦住——门不该挡住"合成配置的单元测试"。

绕过：环境变量 ``LEGGED_STUDIO_SMOKE_GATE=0``（**仅限 CI / 合成配置**），
绕过会在返回里**如实标注** ``bypassed: true``，不静默。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

#: 冒烟档规模。与 `backend/training/create.py` 的钳制**共用同一常量**，避免两处各自漂移。
SMOKE_MAX_ENVS = 64
SMOKE_MAX_ITERS = 5

#: 只有"真的跑完"的任务才算证据。`TrainingManager` 的成功态是 ``completed``；
#: 其余拼写一并接受，是为了不因词表措辞变化而**误判成"没跑过冒烟"**。
SUCCESS_STATES = ("completed", "success", "finished", "done")

#: 绕过开关（仅限 CI/合成配置）。
BYPASS_ENV = "LEGGED_STUDIO_SMOKE_GATE"


def is_smoke_scale(config: Mapping[str, Any]) -> bool:
    """这份配置是否在**冒烟档规模**内（≤64 envs 且 ≤5 iters）。"""
    envs = int(config.get("num_envs") or 0)
    iters = int(config.get("max_iterations") or 0)
    return envs <= SMOKE_MAX_ENVS and iters <= SMOKE_MAX_ITERS


def _status_and_dir(candidate: Any) -> tuple[str, Path | None]:
    """把候选证据统一成 ``(status, task_dir)``。接受 ``(status, dir)`` 元组或带属性的对象。"""
    if isinstance(candidate, (tuple, list)) and len(candidate) == 2:
        status, task_dir = candidate
    else:
        status = getattr(candidate, "status", None)
        task_dir = getattr(candidate, "task_dir", None)
    return str(status or "").lower(), (Path(task_dir) if task_dir else None)


def smoke_evidence(digest: str, candidates: Iterable[Any]) -> dict[str, Any] | None:
    """找一条**同输入指纹 · 已完成 · 冒烟档**的 Run —— 这就是"冒烟通过"的证据。

    读的是磁盘上的既有事实（`resolved-config.json` + 任务状态），不依赖任何内存状态，
    所以它在"重启后"、"别的进程刚跑完"这些场景下同样成立。
    """
    for candidate in candidates:
        status, task_dir = _status_and_dir(candidate)
        if status not in SUCCESS_STATES or task_dir is None:
            continue
        try:
            resolved = json.loads(
                (task_dir / "resolved-config.json").read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError):
            continue
        inputs = resolved.get("inputs") or {}
        if str(inputs.get("digest") or "") != digest:
            continue
        params = inputs.get("params") or {}
        if not params.get("smoke_preset"):
            continue          # 长训自己不能给自己当冒烟证据
        return {
            "run_id": task_dir.name,
            "iterations": params.get("max_iterations"),
            "num_envs": params.get("num_envs"),
            "seed": inputs.get("seed"),
        }
    return None


def check(
    *,
    digest: str,
    config: Mapping[str, Any],
    candidates: Iterable[Any] = (),
    bypass: bool | None = None,
) -> dict[str, Any]:
    """长训前的前置检查。返回结论字典（**不抛异常**，由调用方决定怎么处理）。

    ``required=False`` 只表示"这次不是长训"，不表示"没问题" —— 冒烟档自身的成败由
    运行结果说话，门不管。
    """
    env_value = str(os.environ.get(BYPASS_ENV) or "").strip().lower()
    bypassed = bool(bypass) or env_value in ("0", "false", "no", "off")

    if is_smoke_scale(config):
        return {
            "required": False, "ok": True, "bypassed": False, "digest": digest, "evidence": None,
            "reason": (f"冒烟档规模内（≤{SMOKE_MAX_ENVS} envs × ≤{SMOKE_MAX_ITERS} iters），"
                       "无需前置——它自己就是冒烟"),
        }

    evidence = smoke_evidence(digest, candidates)
    if evidence is not None:
        return {
            "required": True, "ok": True, "bypassed": False, "digest": digest, "evidence": evidence,
            "reason": f"已找到同输入指纹的冒烟通过记录：{evidence['run_id']}",
        }
    if bypassed:
        return {
            "required": True, "ok": True, "bypassed": True, "digest": digest, "evidence": None,
            "reason": f"冒烟前置被 {BYPASS_ENV} 绕过（**仅限 CI / 合成配置**）",
        }
    return {
        "required": True, "ok": False, "bypassed": False, "digest": digest, "evidence": None,
        "reason": (
            "长训前必须先在**冒烟档**跑通同一配置（64 envs × 5 iters）："
            "冒烟几十秒就能暴露维度/布局/依赖/缺件错误，而长训要占 GPU 到小时级。"
            f"当前输入指纹 {digest[:12]}… 没有任何「已完成且成功」的冒烟 Run；"
            "冒烟通过后配置**改一个字**都会派生新指纹，需重跑冒烟"
            "（刻意设计，防止「改了配置却沿用旧结论」）"
        ),
    }
