"""算法能力目录（**单一词汇表**）：内置 runner 算法 + 插件注册表。

## 为什么需要这一层（2026-09-19 收口）

此前"算法"在两个地方各有一份词汇表：本模块的 ``ALGORITHM_REGISTRY``（PPO/SAC/TD3）
与插件注册表 ``registry.json``（cts/dreamwaq/amp/distill/him/hora/appo）。于是
"算法能不能跑"变成两个问题的乘积，谁都答不全：

* 产品 API 只认 ``{PPO}``，非 PPO **一律 501**（连"为什么不能跑"都说不清）；
* profile 里写着 ``"algorithm": "HIM"``、``"algorithm_plugin": "him"``，而两个词表都不认它。

本模块把两者合成**一份清单**，并把"能不能跑"拆成三个必须分开的字段——混起来就会出现
"注册了 = 能跑"的假绿：

| 字段 | 含义 | 判据来源 |
|---|---|---|
| ``registered`` | 在词汇表里（有名字、有出处、有许可） | 本模块 / ``registry.json`` |
| ``native_supported`` | 能接进 mjlab native runner | 内置：dataclass cfg 直接可用；插件：有 ``class_name`` 绑定 |
| ``product_open`` | **产品内可创建训练** | 今天只有 PPO；其余要么未接线、要么已接线但未经真训练验证 |

``available`` 保留为 ``product_open`` 的别名：前端（``web/training_create.html``）用它
决定下拉框是否可点，语义就是"这个现在能不能选"，与 ``product_open`` 同义。

## 两条路径（不要混）

1. **内置 runner 路径**（``kind="native"``）：mjlab 原生 dataclass cfg
   （``RslRlOnPolicyRunnerCfg`` / ``RslRlPpoAlgorithmCfg``），由 ``kits/``（形态 Kit）
   与包内训练源直接构造。它**没有 class_name 绑定**，也不该假装成插件——把它塞进插件
   注册表要凭空编一套 class_name 字符串（那是虚构，不是统一）。
2. **插件路径**（``kind="plugin"``）：注册在 ``registry.json`` 的算法，由
   ``bind_algorithm_to_runner_cfg`` 把变体的 class_name 写进 runner cfg；
   只在 profile **显式声明** ``algorithm_plugin`` 时启用（见 ``apply_algorithm_plugin``）。
"""

from __future__ import annotations

from typing import Any

#: 内置 runner 算法（不经过插件层）。`product_open` 是**产品内的开关**，不是能力声明。
NATIVE_ALGORITHMS: dict[str, dict[str, Any]] = {
    "PPO": {
        "label": "PPO",
        "family": "on_policy",
        "native_supported": True,
        "product_open": True,
        "impl": "mjlab.rl.RslRlPpoAlgorithmCfg（dataclass cfg，无 class_name 绑定）",
        "description": "稳定的 on-policy 基线，适合速度跟踪和快速验证",
        "config_fields": ["learning_rate", "num_steps", "num_minibatches", "gamma", "gae_lambda", "clip_param", "entropy_coef"],
    },
    "SAC": {
        "label": "SAC",
        "family": "off_policy",
        "native_supported": False,
        "product_open": False,
        "impl": "adapters/mjlab/algorithms/off_policy.py（未接进 runner）",
        "description": "带熵正则的连续动作 off-policy 算法，适合样本复用",
        "config_fields": ["learning_rate", "gamma", "tau", "batch_size", "replay_size", "alpha"],
    },
    "TD3": {
        "label": "TD3",
        "family": "off_policy",
        "native_supported": False,
        "product_open": False,
        "impl": "adapters/mjlab/algorithms/off_policy.py（未接进 runner）",
        "description": "双 Q 网络连续动作算法，适合低噪声精调",
        "config_fields": ["learning_rate", "gamma", "tau", "batch_size", "replay_size", "policy_delay", "exploration_noise"],
    },
}


def _plugin_entries() -> list[dict[str, Any]]:
    """从插件注册表派生条目（**纯 JSON，控制面安全**）。"""

    from adapters.mjlab.algorithms.plugin_registry import load_registry

    plugins = load_registry()["plugins"]
    entries: list[dict[str, Any]] = []
    for name, entry in sorted(plugins.items()):
        metadata = entry.get("metadata") or {}
        label = str(metadata.get("label") or name)
        entries.append({
            "id": name,
            "kind": "plugin",
            "label": label,
            "family": entry.get("family") or "on_policy",
            "registered": True,
            # 插件自带 variants（class_name 绑定）⇒ 能接进 native runner；
            # 但**未经真训练验证前产品内不开放**（fail-closed，见模块头）。
            "native_supported": bool(entry.get("variants")),
            "product_open": False,
            "upstream": metadata.get("upstream"),
            "license": metadata.get("license"),
            "supported_obs_types": list(metadata.get("supported_obs_types") or []),
            "variants": sorted(entry.get("variants") or {}),
            "impl": f"{entry.get('module')}:{entry.get('plugin_class')}",
            "description": f"{label}（上游：{metadata.get('upstream')}）",
            "config_fields": [],
        })
    return entries


def list_algorithms() -> list[dict[str, Any]]:
    """算法清单（**单一来源**）：内置 runner 算法 + 插件注册表。

    ``available`` 是 ``product_open`` 的别名（前端按它决定能不能选）。
    """

    entries: list[dict[str, Any]] = []
    for key, value in NATIVE_ALGORITHMS.items():
        item = {"id": key, "kind": "native", "registered": True, **value}
        item["available"] = item["product_open"]
        entries.append(item)
    for item in _plugin_entries():
        item["available"] = item["product_open"]
        entries.append(item)
    return entries


def resolve_algorithm(name: str, *, plugin: str | None = None) -> dict[str, Any]:
    """把算法标签解析成统一裁决；未登记的名字 **fail-closed**。

    规则（按序，命中即停）：

    1. ``plugin`` 显式给了 ⇒ 以它为准（profile 的 ``algorithm_plugin`` 是**最明确的意图**，
       不做别名猜测：``algorithm`` 只是人读标签，允许与插件名不同大小写/不同写法）；
    2. 否则标签**大写**命中内置（``PPO`` / ``SAC`` / ``TD3``）；
    3. 否则标签**小写**命中插件名（``him`` / ``cts`` …）。

    解析不到时抛 ``ValueError``，消息里同时列出两套词汇——调用方（API/CLI/worker）
    只需把它翻成自己的错误形态，不各自再判一次。
    """

    label = str(name or "").strip()
    if plugin:
        plugin_name = str(plugin).strip()
        entry = _plugin_entry(plugin_name)
        return {**entry, "requested": label, "resolved_by": "algorithm_plugin"}

    if not label:
        raise ValueError("算法名不能为空")

    upper = label.upper()
    if upper in NATIVE_ALGORITHMS:
        item = {"id": upper, "kind": "native", "registered": True, **NATIVE_ALGORITHMS[upper]}
        item["available"] = item["product_open"]
        return {**item, "requested": label, "resolved_by": "native_label"}

    lower = label.lower()
    if lower in {entry["id"] for entry in _plugin_entries()}:
        entry = _plugin_entry(lower)
        return {**entry, "requested": label, "resolved_by": "plugin_name"}

    raise ValueError(
        f"未知算法 {label!r}；已登记：内置 {sorted(NATIVE_ALGORITHMS)} / "
        f"插件 {sorted(entry['id'] for entry in _plugin_entries())}"
    )


def _plugin_entry(plugin_name: str) -> dict[str, Any]:
    """取某插件的目录条目；未登记 fail-closed（与 ``list_algorithms`` 同源）。"""

    for entry in _plugin_entries():
        if entry["id"] == plugin_name:
            entry = dict(entry)
            entry["available"] = entry["product_open"]
            return entry
    raise ValueError(
        f"未知算法插件 {plugin_name!r}；已登记插件：{sorted(entry['id'] for entry in _plugin_entries())}"
    )


def resolve(name: str) -> Any:
    """Resolve a registered algorithm plugin by name (training stack required).

    Fail-closed: an unknown name raises ``ValueError`` listing the plugin
    names available in ``registry.json``.  The name check itself is pure JSON
    (control-plane safe); the returned plugin instance is only materialized
    when the training stack (torch) is importable.
    """
    from adapters.mjlab.algorithms.plugin_registry import list_plugins as _list_plugins
    from adapters.mjlab.algorithms.plugin_registry import resolve_plugin

    available = _list_plugins()
    if name not in available:
        raise ValueError(f"unknown algorithm {name!r}; available: {', '.join(available)}")
    return resolve_plugin(name)


def create_algorithm(name: str, num_obs: int, num_actions: int, config: dict[str, Any], device: str):
    # Keep registry discovery available in the lightweight control-plane
    # environment.  Training dependencies are loaded only when a run starts.
    from adapters.mjlab.algorithms.off_policy import OffPolicyConfig, SACAlgorithm, TD3Algorithm
    from adapters.mjlab.algorithms.ppo import PPOAlgorithm, PPOConfig

    normalized = name.upper()
    if normalized not in NATIVE_ALGORITHMS:
        raise ValueError(f"unknown algorithm {name}; available: {', '.join(NATIVE_ALGORITHMS)}")
    if normalized == "PPO":
        return PPOAlgorithm(
            num_obs=num_obs,
            num_actions=num_actions,
            config=PPOConfig(**{key: value for key, value in config.items() if key in PPOConfig.__annotations__}),
            device=device,
        )
    off_policy = OffPolicyConfig(**{key: value for key, value in config.items() if key in OffPolicyConfig.__annotations__})
    cls = SACAlgorithm if normalized == "SAC" else TD3Algorithm
    return cls(num_obs=num_obs, num_actions=num_actions, config=off_policy, device=device)


__all__ = [
    "NATIVE_ALGORITHMS",
    "create_algorithm",
    "list_algorithms",
    "resolve",
    "resolve_algorithm",
]
