"""训练健康仪表盘 + 中文症状路由卡（T2.2，批次 2 / M3）。

五大仪表盘（Reward / KL / Entropy / Value Loss / Episode Length）来自知识库
Ch25（00_Survey 报告 1 §9）：每项 ✅⚠❌ + 当前值 + 一句话状态；⚠ 展开中文症状
诊断卡，按"先验接口 → 再查 reward → 最后调 PPO"铁律排序，每步带跳转（dot-path）。

输入是 metrics.jsonl 行 / TB 序列中常见的 rsl_rl 键；键缺失的仪表盘返回
"未采集"而不是伪造结论。
"""

from __future__ import annotations

from typing import Any

# rsl_rl 常见键别名（不同 runner 版本键名略有差异）
KEY_ALIASES = {
    "reward": ["train/mean_reward", "Episode/rew_total", "mean_reward", "reward"],
    "kl": ["Policy/mean_kl", "kl", "kl_divergence"],
    "entropy": ["Policy/mean_entropy", "entropy"],
    "value_loss": ["Loss/value_function", "value_loss", "value_function_loss"],
    "episode_length": ["Train/mean_episode_length", "Episode/episode_length", "episode_length"],
}

# 症状 → 排查路由（静态；顺序即"先验接口→再查 reward→最后调 PPO"铁律）
SYMPTOM_CARDS = {
    "kl_zero": {
        "symptom": "KL 长时间为 0 或极小",
        "why": "学习率过小或策略没有梯度——更新量不足，训练停滞",
        "steps": [
            {"check": "检查动作 scale / obs 归一化是否把策略输出压平", "jump": "训练区 · 执行器页 actuator_profile.action_scale"},
            {"check": "检查 reward 是否全为常数（接口断了 reward 没有信号）", "jump": "监控区 · 分项曲线 Tracking 层"},
            {"check": "learning_rate 相对 desired_kl 是否过小", "jump": "训练配置 · PPO learning_rate"},
        ],
    },
    "kl_spike": {
        "symptom": "KL 周期性尖峰",
        "why": "一次更新把策略推得太远——lr 自适应跟不上 reward 突变或课程跳变",
        "steps": [
            {"check": "分项曲线是否在尖峰处有 reward 突变（课程推进/DR 参数切换）", "jump": "监控区 · 分项曲线"},
            {"check": "降低 desired_kl（如 0.01 → 0.008）让 lr 自适应更保守", "jump": "训练配置 · PPO desired_kl"},
        ],
    },
    "entropy_collapse": {
        "symptom": "熵快速塌缩到接近 0",
        "why": "策略过早确定化——探索不足，后续 reward 平台期难以逃出",
        "steps": [
            {"check": "entropy coefficient 是否过大导致一次性压没", "jump": "训练配置 · PPO entropy_coef"},
            {"check": "检查观测里是否有捷径信号（prev_action 泄漏等）", "jump": "训练区 · 观测组件"},
        ],
    },
    "value_spike": {
        "symptom": "Value loss 尖峰伴随 reward 崩",
        "why": "critic 对新 value 目标追不上——常见于 timeout bootstrap 配置漂移或奖励突变",
        "steps": [
            {"check": "确认 wrapper 透传 time_outs（冒烟档已有不变量检查）", "jump": "tools/_smoke_one.py time_outs_wired"},
            {"check": "查看 reward_scales 是否中途被改（contract_snapshot diff）", "jump": "策略档案 · lineage"},
        ],
    },
    "episode_short": {
        "symptom": "回合长度短且不增长",
        "why": "机器人早期反复摔倒——可能是 reward 冲突或地形课程推进过快",
        "steps": [
            {"check": "检查 Contact 层惩罚是否过严（早期严罚 → 学会不动）", "jump": "训练区 · 奖励看板 Contact 层"},
            {"check": "检查地形/命令课程当前难度", "jump": "训练配置 · curriculum"},
        ],
    },
    "reward_up_perf_flat": {
        "symptom": "total reward 上涨但表现没有变好",
        "why": "reward hacking：上涨可能只是 Regularization 惩罚在降（策略变得更保守）",
        "steps": [
            {"check": "按层对比 Tracking 曲线是否真的在涨", "jump": "监控区 · 分项曲线四层着色"},
            {"check": "检查正则项权重是否相对 Tracking 过大", "jump": "训练区 · 奖励看板 Regularization 层"},
        ],
    },
}


def _series(rows: list[dict], aliases: list[str]) -> list[float]:
    for key in aliases:
        values = [float(row[key]) for row in rows if isinstance(row, dict) and isinstance(row.get(key), (int, float))]
        if values:
            return values
    return []


def _trend(values: list[float], window: int = 5) -> str:
    if len(values) < window * 2:
        return "flat"
    head = sum(values[:window]) / window
    tail = sum(values[-window:]) / window
    if tail > head * 1.05 + 1e-9:
        return "up"
    if tail < head * 0.95 - 1e-9:
        return "down"
    return "flat"


def _spiky(values: list[float]) -> bool:
    if len(values) < 10:
        return False
    tail = values[-10:]
    mean = sum(tail) / len(tail) or 1e-9
    spread = (max(tail) - min(tail)) / abs(mean)
    return spread > 3.0


def evaluate_gauges(rows: list[dict]) -> dict[str, dict[str, Any]]:
    """五大仪表盘：每项 {status, value, summary, symptom_key}。"""

    gauges: dict[str, dict[str, Any]] = {}
    reward = _series(rows, KEY_ALIASES["reward"])
    if reward:
        trend = _trend(reward)
        gauges["reward"] = {
            "status": "pass" if trend in ("up", "flat") else "warn",
            "value": round(reward[-1], 4),
            "summary": {"up": "总奖励在涨（注意分项是否只是惩罚在降）", "flat": "总奖励持平", "down": "总奖励在跌——优先看崩溃告警"}[trend],
            "symptom_key": "reward_up_perf_flat" if trend == "up" else None,
        }
    else:
        gauges["reward"] = {"status": "warn", "value": None, "summary": "未采集到奖励序列"}

    kl = _series(rows, KEY_ALIASES["kl"])
    if kl:
        tail = kl[-1]
        if tail <= 1e-6:
            gauges["kl"] = {"status": "warn", "value": round(tail, 8), "summary": "KL≈0，训练可能停滞", "symptom_key": "kl_zero"}
        elif _spiky(kl):
            gauges["kl"] = {"status": "warn", "value": round(tail, 8), "summary": "KL 尖峰频繁", "symptom_key": "kl_spike"}
        else:
            gauges["kl"] = {"status": "pass", "value": round(tail, 8), "summary": "KL 在自适应 lr 带宽内"}
    else:
        gauges["kl"] = {"status": "warn", "value": None, "summary": "未采集到 KL 序列"}

    entropy = _series(rows, KEY_ALIASES["entropy"])
    if entropy:
        tail = entropy[-1]
        head = sum(entropy[: max(1, len(entropy) // 4)]) / max(1, len(entropy) // 4)
        collapsed = tail < head * 0.05 or tail < 1e-4
        gauges["entropy"] = {
            "status": "warn" if collapsed else "pass",
            "value": round(tail, 6),
            "summary": "熵快速塌缩——探索不足" if collapsed else "熵水平正常",
            "symptom_key": "entropy_collapse" if collapsed else None,
        }
    else:
        gauges["entropy"] = {"status": "warn", "value": None, "summary": "未采集到熵序列"}

    value_loss = _series(rows, KEY_ALIASES["value_loss"])
    if value_loss:
        spiky = _spiky(value_loss)
        gauges["value_loss"] = {
            "status": "warn" if spiky else "pass",
            "value": round(value_loss[-1], 6),
            "summary": "value loss 尖峰" if spiky else "value loss 平稳",
            "symptom_key": "value_spike" if spiky else None,
        }
    else:
        gauges["value_loss"] = {"status": "warn", "value": None, "summary": "未采集到 value loss 序列"}

    episode = _series(rows, KEY_ALIASES["episode_length"])
    if episode:
        trend = _trend(episode)
        short = episode[-1] < 20
        status = "warn" if (short or trend == "down") else "pass"
        summary = {
            (True, "up"): "回合很短但在增长（早期学步阶段）",
            (True, "flat"): "回合长度短且不增长",
            (True, "down"): "回合长度变短——早期崩溃",
            (False, "up"): "回合长度在增长",
            (False, "flat"): "回合长度平稳",
            (False, "down"): "回合长度下降——检查是否有崩溃",
        }[(short, trend)]
        gauges["episode_length"] = {
            "status": status,
            "value": round(episode[-1], 2),
            "summary": summary,
            "symptom_key": "episode_short" if (short and trend != "up") or trend == "down" else None,
        }
    else:
        gauges["episode_length"] = {"status": "warn", "value": None, "summary": "未采集到回合长度序列"}

    return gauges


def build_health_report(rows: list[dict]) -> dict[str, Any]:
    """仪表盘 + 关联症状卡全文（⚠ 展开即得，步骤带跳转）。"""

    gauges = evaluate_gauges(rows)
    cards: list[dict] = []
    for gauge in gauges.values():
        key = gauge.get("symptom_key")
        if key and key in SYMPTOM_CARDS:
            cards.append({"id": key, **SYMPTOM_CARDS[key]})
    return {
        "gauges": gauges,
        "cards": cards,
        "rule": "排查铁律：先验接口（obs/action scale/command）→ 再查 reward → 最后调 PPO",
    }
