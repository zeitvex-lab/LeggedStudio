"""冒烟前置门（E8）：**未过冒烟不能长训**。

## 为什么需要这道门

长训是 GPU 分钟到小时级；而配置错误（观测维度不符、历史布局不对、依赖缺失、资产缺件）
在**冒烟档**（64 envs × 5 iters）几十秒内就会暴露。不设门就会出现"跑了 40 分钟才发现
`obs_dim` 错"——本仓反复踩过的正是这一类：**错在配置，却被读成"策略不行"**。

## 证据从哪来（**不另造记录**）

冒烟"通过"的证据＝**已有事实的组合**：

* ``task_dir/resolved-config.json``（B9 落的 Run 档案）里的 ``inputs`` —— 输入四元组
  （契约哈希 + recipe + profile + seed + 全部 config 参数）；
* ``resolved.inputs.params.smoke_preset`` 为真 —— 那次是冒烟档；
* 该任务状态为 ``completed`` 族（worker 的完成词表含 ``train_completed``）。

"同一配置"按**规范化摘要**比对（`_match_digest`）：剔除规模三元组
``num_envs`` / ``max_iterations`` / ``smoke_preset``（``params`` 与 recipe 里的
派生落点一并剔除）后**逐键一致**。E8 的意图是
"先在冒烟档跑通同一配置再长训"，而冒烟档必然把规模钳到 64×5（create.py）——若按
逐字节指纹比对，真长训（规模更大）永远匹配不上任何冒烟 Run，门就从"先冒烟"
劣化成"永远 409"。除规模与落盘频率之外的任何一键差异（seed / recipe / overrides / …）
仍会改变规范化摘要 → "沿用上次的冒烟结论"在结构上不可能发生
（这正是把门挂在 B9 指纹上的价值）。

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

from backend.training.runs import canonical_digest

#: 冒烟档规模。与 `backend/training/create.py` 的钳制**共用同一常量**，避免两处各自漂移。
SMOKE_MAX_ENVS = 64
SMOKE_MAX_ITERS = 5

#: 规范化比对时从 ``params`` 剔除的**规模三元组**：冒烟钳制（create.py）只动这三个键，
#: 长训与冒烟在这三键上必然不同；其余任何一键都保留在比对里，改一个字就换摘要。
#: 加 ``save_interval``（2026-09-30 checkpoint 磁盘纪律）：落盘频率**不影响训练行为**
#: （只改 checkpoint 写盘节奏），且它按预算自适应（l7 驱动 ``max(250, iters // 10)``）
#: ——不豁免的话"改间隔必重跑冒烟"就是假门禁。权重行为面照旧逐键比对。
SCALE_KEYS = ("num_envs", "max_iterations", "smoke_preset", "save_interval")

#: 只有"真的跑完"的任务才算证据。`TrainingManager` 的成功态是 ``completed``，
#: worker（adapters/mjlab/native_worker.py）的实际完成词表是 ``train_completed``；
#: 其余拼写一并接受，是为了不因词表措辞变化而**误判成"没跑过冒烟"**。
SUCCESS_STATES = ("completed", "train_completed", "success", "finished", "done")

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


def _strip_scale(container: Any) -> Any:
    """从一层 Mapping 里剔掉 ``SCALE_KEYS``（规模 + save_interval；非 Mapping 原样返回）。"""
    if not isinstance(container, Mapping):
        return container
    return {key: value for key, value in container.items() if key not in SCALE_KEYS}


def _match_digest(inputs: Mapping[str, Any]) -> str:
    """**规范化比对摘要**：剔除规模三元组后重算的输入指纹。

    与 `backend.training.runs.build_inputs` 用**同一个** `canonical_digest`
    （同算法、同规范化规则：sort_keys + 紧凑分隔符 + 保留非 ASCII），只是先把
    **规模三元组**剔掉 —— **不发明第二种摘要**，"同输入必同摘要"仍由 runs.py
    的同一处实现背书。``inputs["digest"]``（build_inputs 算的整档指纹）不参与
    重算，与 build_inputs「先算 payload 再挂 digest」的次序一致。

    规模三元组有**两处落点**，都要剔（`resolve_recipe` 会把 config 原样带进
    recipe，见 adapters/mjlab/recipe_registry.py）：

    * ``params``：``num_envs`` / ``max_iterations`` / ``smoke_preset``；
    * ``recipe``：``environment.num_envs`` 与
      ``algorithm_config.{num_envs, max_iterations, smoke_preset}``。

    它们是**同一组规模参数**的派生视图，不是新的语义键；只剔 ``params`` 会让
    "同配置（规模除外）"仍然永远比对失败。剔除严格限于这三个键名 —— recipe 的
    其余键（reward_scales / terrain / command_ranges / seed / …）与 inputs 的
    其余部分（contract_hash / seed / profile / …）仍逐键参与比对。
    """
    body = {key: value for key, value in dict(inputs).items() if key != "digest"}
    if isinstance(body.get("params"), Mapping):
        body["params"] = _strip_scale(body["params"])
    recipe = body.get("recipe")
    if isinstance(recipe, Mapping):
        recipe = dict(recipe)
        if isinstance(recipe.get("environment"), Mapping):
            recipe["environment"] = _strip_scale(recipe["environment"])
        if isinstance(recipe.get("algorithm_config"), Mapping):
            recipe["algorithm_config"] = _strip_scale(recipe["algorithm_config"])
        body["recipe"] = recipe
    return canonical_digest(body)


def smoke_evidence(inputs: Mapping[str, Any], candidates: Iterable[Any]) -> dict[str, Any] | None:
    """找一条**同配置（规模除外）· 已完成 · 冒烟档**的 Run —— 这就是"冒烟通过"的证据。

    「同配置」的判据是 `_match_digest(候选 inputs) == _match_digest(本次长训 inputs)`：
    剔除规模三键与 ``save_interval`` 后逐键一致。
    读的是磁盘上的既有事实（`resolved-config.json` + 任务状态），不依赖任何内存状态，
    所以它在"重启后"、"别的进程刚跑完"这些场景下同样成立。
    """
    target = _match_digest(inputs)
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
        candidate_inputs = resolved.get("inputs") or {}
        if _match_digest(candidate_inputs) != target:
            continue
        params = candidate_inputs.get("params") or {}
        if not params.get("smoke_preset"):
            continue          # 长训自己不能给自己当冒烟证据
        return {
            "run_id": task_dir.name,
            "iterations": params.get("max_iterations"),
            "num_envs": params.get("num_envs"),
            "seed": candidate_inputs.get("seed"),
        }
    return None


def check(
    *,
    inputs: Mapping[str, Any],
    config: Mapping[str, Any],
    candidates: Iterable[Any] = (),
    bypass: bool | None = None,
) -> dict[str, Any]:
    """长训前的前置检查。返回结论字典（**不抛异常**，由调用方决定怎么处理）。

    ``inputs`` 是本次长训的完整输入四元组（`runs.build_inputs` 的产出，含整档
    ``digest``）——比对按 `_match_digest` 的规范化摘要，报告用的指纹取
    ``inputs["digest"]`` 原值。``required=False`` 只表示"这次不是长训"，
    不表示"没问题" —— 冒烟档自身的成败由运行结果说话，门不管。
    """
    digest = str(inputs.get("digest") or "")
    env_value = str(os.environ.get(BYPASS_ENV) or "").strip().lower()
    bypassed = bool(bypass) or env_value in ("0", "false", "no", "off")

    if is_smoke_scale(config):
        return {
            "required": False, "ok": True, "bypassed": False, "digest": digest, "evidence": None,
            "reason": (f"冒烟档规模内（≤{SMOKE_MAX_ENVS} envs × ≤{SMOKE_MAX_ITERS} iters），"
                       "无需前置——它自己就是冒烟"),
        }

    evidence = smoke_evidence(inputs, candidates)
    if evidence is not None:
        return {
            "required": True, "ok": True, "bypassed": False, "digest": digest, "evidence": evidence,
            "reason": (
                "已找到同配置（除规模与 save_interval 外逐键一致）"
                f"的冒烟通过记录：{evidence['run_id']}"
            ),
        }
    if bypassed:
        return {
            "required": True, "ok": True, "bypassed": True, "digest": digest, "evidence": None,
            "reason": f"冒烟前置被 {BYPASS_ENV} 绕过（**仅限 CI / 合成配置**）",
        }
    return {
        "required": True, "ok": False, "bypassed": False, "digest": digest, "evidence": None,
        "reason": (
            "长训前必须先在**冒烟档**跑通同一配置（64 envs × 5 iters；与长训配置除规模 "
            "规模与 save_interval 外需逐键一致）："
            "冒烟几十秒就能暴露维度/布局/依赖/缺件错误，而长训要占 GPU 到小时级。"
            f"当前输入指纹 {digest[:12]}… 没有任何「已完成且成功」的同配置冒烟 Run；"
            "配置（规模除外）**改一个字**都会改变规范化比对，需重跑冒烟"
            "（刻意设计，防止「改了配置却沿用旧结论」）"
        ),
    }
