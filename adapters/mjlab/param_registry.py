"""Curated parameter descriptor catalog for training-profile configs.

The raw profile dump carries ~1400 leaf paths; editing that wall of dot-paths
is unusable. This module curates the ~45 commonly-tuned parameters into
descriptors (中文 label / unit / hint / type) mapped to the five console
categories, plus pattern rules for term collections that no static list can
enumerate (reward weights, domain-randomization event params, action scales,
observation noise, termination thresholds).

:func:`resolve_params` walks the JSON dump produced by
``config_introspect.dump_config_tree`` and emits resolved descriptors:

    [{"path", "category", "label", "unit", "hint", "type",
      "value", "default", "advanced", "readonly", "group"}, ...]

Only the standard library is imported (plus the stdlib-only
``config_introspect``), so the control plane can unit-test the resolver
without mjlab or torch.
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

from adapters.mjlab.config_introspect import get_by_path

CATEGORY_ORDER = ("simulator", "environment", "embodiment", "learning", "robustness")

CATEGORY_LABELS = {
    "simulator": "仿真器与运行时",
    "environment": "环境与地形",
    "embodiment": "机器人与观测",
    "learning": "算法与超参数",
    "robustness": "奖励与鲁棒性",
}

# ---------------------------------------------------------------------------
# Fixed descriptors: well-known paths verified against the real mjlab
# ManagerBasedRlEnvCfg / RslRlOnPolicyRunnerCfg dumps (zex-w, unitree_go2).
# type is a hint for the editor; the resolver always re-infers it from the
# actual value. "allow_list" opts list-valued paths into the resolved output
# (range pairs / readonly network shapes); everything else list/dict/None is
# left to the expert tree.
# ---------------------------------------------------------------------------
FIXED_DESCRIPTORS: list[dict] = [
    # ---- simulator -------------------------------------------------------
    {"path": "environment.sim.mujoco.timestep", "category": "simulator",
     "label": "物理步长", "unit": "s", "hint": "单步物理仿真时长，越小越精确、越慢", "type": "float"},
    {"path": "environment.sim.mujoco.iterations", "category": "simulator",
     "label": "求解器迭代次数", "hint": "每步最大求解迭代，增大更稳定但更慢", "type": "int"},
    {"path": "environment.sim.mujoco.ls_iterations", "category": "simulator",
     "label": "线搜索迭代次数", "hint": "求解器线搜索最大迭代次数", "type": "int"},
    {"path": "environment.sim.mujoco.impratio", "category": "simulator",
     "label": "摩擦锥比 impratio", "hint": "切向/法向阻抗比，越大摩擦越硬", "type": "int"},
    {"path": "environment.sim.mujoco.cone", "category": "simulator",
     "label": "摩擦锥类型", "hint": "elliptic（默认）/ pyramidal", "type": "str"},
    {"path": "environment.scene.num_envs", "category": "simulator",
     "label": "并行环境数", "hint": "越大采样越快、显存占用越高；GPU 推荐 2048+", "type": "int"},
    {"path": "environment.episode_length_s", "category": "simulator",
     "label": "回合长度", "unit": "s", "hint": "单回合仿真时长，过长拖慢早期探索", "type": "float"},
    {"path": "runner.seed", "category": "simulator",
     "label": "随机种子", "hint": "相同种子 + 相同配置可复现实验", "type": "int"},
    {"path": "runner.max_iterations", "category": "simulator",
     "label": "最大迭代数", "hint": "训练迭代上限；崎岖地形通常需要 2000+", "type": "int"},
    {"path": "runner.save_interval", "category": "simulator",
     "label": "检查点保存间隔", "hint": "每 N 次迭代保存一个 model_<iter>.pt", "type": "int"},
    # ---- environment -----------------------------------------------------
    {"path": "environment.scene.terrain.terrain_type", "category": "environment",
     "label": "地形类型", "hint": "generator=程序生成地形；由训练配方决定", "type": "str", "readonly": True},
    {"path": "environment.scene.terrain.terrain_generator.curriculum", "category": "environment",
     "label": "地形课程", "hint": "开启后按训练进度逐步提升地形难度", "type": "bool"},
    {"path": "environment.scene.terrain.max_init_terrain_level", "category": "environment",
     "label": "初始难度上限", "hint": "初始地形难度等级上限，越低起步越简单", "type": "int"},
    {"path": "environment.commands.twist.ranges.lin_vel_x", "category": "environment",
     "label": "前进速度范围", "unit": "m/s", "hint": "线速度指令采样区间 [min, max]", "type": "list", "allow_list": True},
    {"path": "environment.commands.twist.ranges.lin_vel_y", "category": "environment",
     "label": "侧移速度范围", "unit": "m/s", "hint": "侧向线速度指令采样区间 [min, max]", "type": "list", "allow_list": True},
    {"path": "environment.commands.twist.ranges.ang_vel_z", "category": "environment",
     "label": "转向角速度范围", "unit": "rad/s", "hint": "偏航角速度指令采样区间 [min, max]", "type": "list", "allow_list": True},
    {"path": "environment.commands.twist.resampling_time_range", "category": "environment",
     "label": "指令重采样间隔", "unit": "s", "hint": "指令重采样时间区间 [min, max]", "type": "list", "allow_list": True},
    {"path": "environment.commands.twist.rel_standing_envs", "category": "environment",
     "label": "站立环境比例", "hint": "采样到零指令（原地站立）的环境占比", "type": "float"},
    # ---- learning --------------------------------------------------------
    {"path": "runner.algorithm.learning_rate", "category": "learning",
     "label": "学习率", "hint": "自适应 KL 调度下的初始学习率", "type": "float"},
    {"path": "runner.algorithm.desired_kl", "category": "learning",
     "label": "目标 KL 散度", "hint": "自适应学习率调度的目标 KL，越大更新越激进", "type": "float"},
    {"path": "runner.algorithm.gamma", "category": "learning",
     "label": "折扣因子 γ", "hint": "越接近 1 越重视长期回报", "type": "float"},
    {"path": "runner.algorithm.lam", "category": "learning",
     "label": "GAE λ", "hint": "优势估计的偏差-方差折中", "type": "float"},
    {"path": "runner.algorithm.clip_param", "category": "learning",
     "label": "裁剪范围 ε", "hint": "策略比率裁剪，限制单次更新幅度", "type": "float"},
    {"path": "runner.algorithm.entropy_coef", "category": "learning",
     "label": "熵系数", "hint": "鼓励探索；奖励坍缩时可适当调大", "type": "float"},
    {"path": "runner.algorithm.num_learning_epochs", "category": "learning",
     "label": "每批学习轮数", "hint": "每次更新遍历 rollout 数据的轮数", "type": "int"},
    {"path": "runner.algorithm.num_mini_batches", "category": "learning",
     "label": "小批量数", "hint": "rollout 切成的 minibatch 数", "type": "int"},
    {"path": "runner.algorithm.max_grad_norm", "category": "learning",
     "label": "梯度裁剪上限", "hint": "梯度范数超过该值时截断", "type": "float"},
    {"path": "runner.algorithm.value_loss_coef", "category": "learning",
     "label": "价值损失系数", "hint": "critic 损失在总损失中的权重", "type": "float"},
    {"path": "runner.num_steps_per_env", "category": "learning",
     "label": "每环境采样步数", "hint": "每次更新前每个环境收集的步数", "type": "int"},
    {"path": "runner.actor.hidden_dims", "category": "learning",
     "label": "网络结构", "hint": "策略 MLP 各层宽度，由 runner 配方决定", "type": "list",
     "readonly": True, "allow_list": True},
    {"path": "runner.actor.activation", "category": "learning",
     "label": "激活函数", "hint": "由 runner 配方决定", "type": "str", "readonly": True},
    {"path": "runner.actor.obs_normalization", "category": "learning",
     "label": "观测归一化", "hint": "由 runner 配方决定", "type": "bool", "readonly": True},
]

# ---------------------------------------------------------------------------
# Pattern rules: term collections that only exist at runtime. Each expands
# against the dump tree; labels come from the term name plus the maps below.
# ---------------------------------------------------------------------------

_EVENT_LABELS = {
    "push_robot": "推力扰动",
    "body_mass_base": "质量随机化",
    "body_friction": "摩擦随机化",
    "base_com": "质心随机化",
    "actuator_stiffness": "刚度随机化",
    "actuator_damping": "阻尼随机化",
    "reset_base": "初始状态随机化",
    "reset_joints": "初始关节随机化",
    "reset_scene": "场景重置",
}

_TERMINATION_LABELS = {
    "bad_orientation": "姿态倾覆",
    "base_ground_contact": "基部触地",
    "illegal_contact": "非法接触",
    "nan_detection": "NaN 检测",
    "time_out": "超时",
}


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    return "json"


def _is_scalar(value: Any) -> bool:
    return value is not None and isinstance(value, (bool, int, float, str))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_range_pair(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(_is_number(item) for item in value)
    )


def _descriptor(path: str, category: str, label: str, value: Any, *, unit: str = "",
                hint: str = "", readonly: bool = False, advanced: bool = False,
                group: str = "") -> dict:
    return {
        "path": path,
        "category": category,
        "label": label,
        "unit": unit,
        "hint": hint,
        "type": _infer_type(value),
        "value": value,
        "default": value,
        "advanced": advanced,
        "readonly": readonly,
        "group": group,
    }


def _iter_nodes(node: Any) -> Iterator[tuple[str, dict]]:
    """Yield ``(name, child_dict)`` for dict-valued members of a dump node."""
    if not isinstance(node, dict):
        return
    for name, child in node.items():
        if isinstance(child, dict):
            yield str(name), child


def _humanize_joint_key(key: str) -> str:
    """Turn a joint regex like ``.*_hip_abduction_joint`` into a short label."""
    text = str(key)
    if "(?!" in text:  # negative-lookahead exclusions → “其余关节”
        return "其余关节"
    cleaned = text.replace(".*", "").strip("_^$").strip("_")
    return cleaned or text


def _resolve_fixed(tree: dict, descriptor: dict) -> Optional[dict]:
    value = get_by_path(tree, descriptor["path"])
    if not _is_scalar(value) and not (descriptor.get("allow_list") and isinstance(value, list)):
        return None
    return _descriptor(
        descriptor["path"],
        descriptor["category"],
        descriptor["label"],
        value,
        unit=descriptor.get("unit", ""),
        hint=descriptor.get("hint", ""),
        readonly=bool(descriptor.get("readonly")),
        advanced=bool(descriptor.get("advanced", False)),
    )


def _expand_curriculum(tree: dict) -> list[dict]:
    node = get_by_path(tree, "environment.curriculum")
    if not isinstance(node, dict) or not node:
        return []
    names = "、".join(str(key) for key in node)
    return [_descriptor(
        "environment.curriculum", "environment", "课程学习项", names,
        hint=f"配方内置课程（{len(node)} 项，由训练配方决定）", readonly=True, group="课程学习",
    )]


def _dot_path_safe(key: Any) -> bool:
    """True if a dict key can be addressed through dot-path overrides.

    Keys containing dots (e.g. joint regex ``.*_hip_abduction_joint``) cannot
    round-trip through :func:`config_introspect.set_by_path` splitting, so they
    are surfaced as a readonly summary instead of editable cards.
    """
    return "." not in str(key)


def _expand_actions(tree: dict) -> list[dict]:
    params: list[dict] = []
    for term, cfg in _iter_nodes(get_by_path(tree, "environment.actions")):
        scale = cfg.get("scale")
        if _is_number(scale):
            params.append(_descriptor(
                f"environment.actions.{term}.scale", "embodiment",
                f"动作缩放：{term}", scale,
                hint="动作经缩放后写入控制目标", group="动作缩放",
            ))
        elif isinstance(scale, dict):
            safe_items = [(key, value) for key, value in scale.items()
                          if _dot_path_safe(key) and _is_number(value)]
            if safe_items:
                for key, value in safe_items:
                    params.append(_descriptor(
                        f"environment.actions.{term}.scale.{key}", "embodiment",
                        f"动作缩放：{term}·{_humanize_joint_key(key)}", value,
                        hint="动作经缩放后写入控制目标", group="动作缩放",
                    ))
            else:
                summary = "、".join(
                    f"{_humanize_joint_key(key)}={value}" for key, value in scale.items()
                )
                params.append(_descriptor(
                    f"environment.actions.{term}.scale", "embodiment",
                    f"动作缩放：{term}·按关节", summary,
                    hint="按关节正则的缩放（键名含点号，不可经点路径覆盖，由训练配方决定）",
                    readonly=True, group="动作缩放",
                ))
        cutoff = cfg.get("cut_off_frequency")
        if _is_number(cutoff):
            params.append(_descriptor(
                f"environment.actions.{term}.cut_off_frequency", "embodiment",
                f"动作低通截止：{term}", cutoff, unit="Hz",
                hint="动作低通滤波截止频率，越低越平滑", group="动作缩放",
            ))
    return params


def _expand_observation_noise(tree: dict) -> list[dict]:
    params: list[dict] = []
    for group, group_cfg in _iter_nodes(get_by_path(tree, "environment.observations")):
        for term, term_cfg in _iter_nodes(group_cfg.get("terms")):
            noise = term_cfg.get("noise")
            if _is_number(noise):
                params.append(_descriptor(
                    f"environment.observations.{group}.terms.{term}.noise", "embodiment",
                    f"观测噪声：{group}·{term}", noise,
                    hint="加性高斯观测噪声标准差（0 为无噪声）", group="观测噪声",
                ))
    return params


def _expand_reward_weights(tree: dict) -> list[dict]:
    params: list[dict] = []
    for term, cfg in _iter_nodes(get_by_path(tree, "environment.rewards")):
        weight = cfg.get("weight")
        if not _is_number(weight):
            continue
        func = str(cfg.get("func", "") or "")
        hint = f"奖励函数 {func.removeprefix('fn:')}" if func else "负值为惩罚项"
        params.append(_descriptor(
            f"environment.rewards.{term}.weight", "robustness",
            f"奖励权重：{term}", weight, hint=hint, group="奖励权重",
        ))
    return params


def _humanize_param_part(part: str) -> str:
    """Label-friendly names for positional dict keys (e.g. COM ``ranges.0``)."""
    return {"0": "x", "1": "y", "2": "z"}.get(part, part)


def _walk_event_leaves(prefix: str, node: dict) -> Iterator[tuple[str, Any]]:
    """Depth-first walk of an event ``params`` payload, skipping ``asset_cfg``.

    Yields ``(relative_key_path, value)`` for numeric scalars and range pairs;
    strings / None / nested asset metadata stay in the expert tree.
    """
    for key, value in node.items():
        if key == "asset_cfg":
            continue
        child_path = f"{prefix}.{key}"
        if isinstance(value, dict):
            yield from _walk_event_leaves(child_path, value)
        elif _is_range_pair(value) or isinstance(value, (bool, int, float)):
            yield child_path, value


def _expand_event_params(tree: dict) -> list[dict]:
    params: list[dict] = []
    for event, cfg in _iter_nodes(get_by_path(tree, "environment.events")):
        event_label = _EVENT_LABELS.get(event, f"事件 {event}")
        params_node = cfg.get("params")
        if not isinstance(params_node, dict):
            continue
        for key_path, value in _walk_event_leaves("params", params_node):
            label_tail = ".".join(
                _humanize_param_part(part) for part in key_path.removeprefix("params.").split(".")
            )
            params.append(_descriptor(
                f"environment.events.{event}.{key_path}", "robustness",
                f"{event_label}·{label_tail}", value,
                hint="均匀采样区间 [min, max]" if _is_range_pair(value) else "",
                group="域随机化",
            ))
    return params


def _expand_termination_params(tree: dict) -> list[dict]:
    params: list[dict] = []
    for term, cfg in _iter_nodes(get_by_path(tree, "environment.terminations")):
        params_node = cfg.get("params")
        if not isinstance(params_node, dict):
            continue
        term_label = _TERMINATION_LABELS.get(term, term)
        for key, value in params_node.items():
            if not _is_number(value):
                continue
            params.append(_descriptor(
                f"environment.terminations.{term}.params.{key}", "robustness",
                f"终止阈值：{term_label}·{key}", value,
                hint="触发终止的判定阈值，由训练配方决定", readonly=True, group="终止条件",
            ))
    return params


def resolve_params(tree: dict) -> list[dict]:
    """Resolve the curated catalog against a dumped profile config tree.

    Fixed descriptors missing from the tree (or holding ``None`` / container
    values) are skipped; pattern rules expand only scalar / range-pair leaves
    so everything else stays in the expert tree. Output preserves catalog
    order: fixed descriptors first, then curriculum / action / observation /
    reward / event / termination expansions.
    """
    if not isinstance(tree, dict):
        return []
    params: list[dict] = []
    for descriptor in FIXED_DESCRIPTORS:
        resolved = _resolve_fixed(tree, descriptor)
        if resolved is not None:
            params.append(resolved)
    params.extend(_expand_curriculum(tree))
    params.extend(_expand_actions(tree))
    params.extend(_expand_observation_noise(tree))
    params.extend(_expand_reward_weights(tree))
    params.extend(_expand_event_params(tree))
    params.extend(_expand_termination_params(tree))
    return params


def category_counts(params: list[dict]) -> dict[str, int]:
    """Per-category resolved-parameter counts (for console badges)."""
    counts = {category: 0 for category in CATEGORY_ORDER}
    for param in params:
        category = param.get("category")
        if category in counts:
            counts[category] += 1
    return counts
