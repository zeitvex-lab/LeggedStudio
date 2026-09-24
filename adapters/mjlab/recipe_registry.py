"""Task/recipe registry inspired by RoboLab TaskSpec and MJLab managers.

B7：任务变体表的数据真值 = ``registry/skills/velocity_base.json`` 的
``tasks`` 键（backend/skill_registry.task_variants()）——新增技能/任务只写
JSON，不改代码。
"""

from __future__ import annotations

from typing import Any

from contracts.scenario_contract import TrainingRecipe
from adapters.mjlab.env_factory import get_reward_preset, get_reward_terms
from backend.skill_registry import SkillRegistryError, task_variants


def _tasks() -> dict[str, dict[str, Any]]:
    try:
        return task_variants()
    except SkillRegistryError as exc:
        raise RuntimeError(f"技能注册表不可用：{exc}") from exc


TASKS: dict[str, dict[str, Any]] = _tasks()

REWARD_ALIASES = {
    "tracking_lin_vel": "track_linear_velocity",
    "tracking_ang_vel": "track_angular_velocity",
    "orientation": "body_orientation_l2",
    "torques": "joint_torques_l2",
    "dof_vel": "joint_vel_l2",
    "dof_acc": "joint_acc_l2",
    "action_rate": "action_rate_l2",
    "feet_air_time": "air_time",
}


def _package_extension_profile(config: dict[str, Any], task_name: str) -> dict[str, Any] | None:
    """U9：查找「包扩展任务」训练档案 —— profile_id 全仓唯一命中 + 声明 env/runner
    entrypoints + 档案声明合法（valid） + 档案 ``task_name`` 与请求一致。

    背景（00_know/05_任务清单.md §U9）：带 entrypoints 的档案（lite3-velocity 等）
    由 native_worker 按 ``profile.entrypoints`` 注册 ``LeggedStudio-<profile_id>``
    的**包扩展任务**训练（L7 已 14/14 机型跑通）；``profile.task_name``（如
    "velocity"）只是产物逻辑名，不在通用 TASKS 表（registry/skills/velocity_base.json
    的 4 个通用任务）里 —— 拿它查表必然 "unknown task" 400。

    这里只读 robot_packages 的持久索引（纯 JSON，不 import torch/mjlab，控制面
    零重栈）。找不到 / 不完整 / 跨包歧义 / 请求的 task_name 与档案声明不一致 →
    返回 None，调用方按未知任务报错（fail-closed：豁免必须由包数据显式声明，
    不能靠猜）。
    """
    profile_id = str(config.get("profile_id") or "").strip()
    if not profile_id or not task_name:
        return None
    from backend.robot_packages import list_robot_packages

    matches = [
        profile
        for record in list_robot_packages()
        for profile in (record.get("training_profiles") or [])
        if str(profile.get("profile_id", "")) == profile_id
    ]
    if len(matches) != 1:
        return None  # 未声明，或同名档案跨包歧义 → 不豁免
    profile = matches[0]
    entrypoints = profile.get("entrypoints")
    if not isinstance(entrypoints, dict) or not entrypoints.get("env") or not entrypoints.get("runner"):
        return None
    if str(profile.get("task_name", "")) != task_name:
        return None
    if not profile.get("valid", False):
        return None
    return profile


def _resolve_package_extension_recipe(config: dict[str, Any], profile: dict[str, Any]) -> TrainingRecipe:
    """U9：包扩展任务的**诚实**配方。

    - 奖励**不并通用预设**（那是通用任务的表，不是包任务真值，编造等于撒谎）：
      只回显请求显式提供的覆盖值。worker 在 profile 模式（preserve_profile=True）
      本就丢弃 recipe 奖励、保留包任务真值，recipe 里的奖励只是显式覆盖的透传。
    - environment 带上来源标注（``source=package-extension`` + native_task_id），
      UI 预览据此如实展示"配方由包扩展提供"。标注放进 environment 字典而不是给
      TrainingRecipe 加新字段，是为了**通用配方的 dump 逐字节不变**（B9 冒烟门
      按 canonical digest 比对既有 Run，配方形状多键会让全部既有冒烟证据失效）。
    """
    algorithm = str(config.get("algorithm", "PPO")).upper()
    if algorithm not in {"PPO", "SAC", "TD3"}:
        raise ValueError(f"unknown algorithm {algorithm}")
    backend = str(config.get("backend", "native_mjlab"))
    if backend != "native_mjlab":
        raise ValueError("Legged Studio training supports only the native_mjlab backend")
    rewards = {str(key): float(value) for key, value in config.get("reward_scales", {}).items() if value is not None}
    environment = {
        "num_envs": int(config.get("num_envs", 4096)),
        "terrain_type": str(config.get("terrain_type") or profile.get("terrain_type") or "plane"),
        "terrain": dict(config.get("terrain", {})),
        "command_ranges": dict(config.get("command_ranges", {})),
        "noise": dict(config.get("noise", {})),
        "curriculum": dict(config.get("curriculum", {})),
        "reward_params": dict(config.get("reward_params", {})),
        "source": "package-extension",
        "native_task_id": f"LeggedStudio-{profile.get('profile_id')}",
    }
    # B23 语义同通用路径：只有显式提供才写键，None → 键不存在（worker 守卫保留任务真值）。
    _episode_length_s = config.get("episode_length_s")
    if _episode_length_s is not None:
        environment["episode_length_s"] = float(_episode_length_s)
    algorithm_config = {key: value for key, value in config.items() if key not in {"task_name", "algorithm", "reward_scales", "num_envs", "episode_length_s", "terrain_type"}}
    return TrainingRecipe(task_name=str(config.get("task_name")), algorithm=algorithm, backend=backend, reward_scales=rewards, environment=environment, algorithm_config=algorithm_config, seed=int(config.get("seed", 0)))


def resolve_recipe(config: dict[str, Any]) -> TrainingRecipe:
    task_name = str(config.get("task_name", "forward_walk"))
    if task_name in TASKS:
        algorithm = str(config.get("algorithm", "PPO")).upper()
        if algorithm not in {"PPO", "SAC", "TD3"}:
            raise ValueError(f"unknown algorithm {algorithm}")
        rewards = {REWARD_ALIASES.get(str(key), str(key)): float(value) for key, value in get_reward_preset(task_name).items()}
        rewards.update({str(key): float(value) for key, value in config.get("reward_scales", {}).items()})
        rewards = {key: value for key, value in rewards.items() if value is not None}
        # 能力矩阵精确报错（清单 ⑬）：请求了声明为不支持的奖励项时，启动即失败并说明原因，
        # 杜绝"配置了 reward 但训练里静默不生效"。
        from adapters.mjlab.env_factory import get_reward_terms as _get_reward_terms
        _term_table = _get_reward_terms()
        _unsupported = sorted(
            name for name, value in rewards.items()
            if name in _term_table and not _term_table[name].get("supported", True)
        )
        if _unsupported:
            _reasons = "; ".join(f"{name}: {_term_table[name].get('reason', 'not implemented')}" for name in _unsupported)
            raise ValueError(f"reward terms not supported by the generic mjlab task — {_reasons}")
        environment = {
            "num_envs": int(config.get("num_envs", 4096)),
            "terrain_type": str(config.get("terrain_type") or TASKS[task_name]["terrain"]),
            "terrain": dict(config.get("terrain", {})),
            "command_ranges": dict(config.get("command_ranges", {})),
            "noise": dict(config.get("noise", {})),
            "curriculum": dict(config.get("curriculum", {})),
            "reward_params": dict(config.get("reward_params", {})),
        }
        # B23：只有请求**显式提供** episode_length_s 才写进 recipe 的 environment；
        # 省略（None）→ 键不存在（不是 null），worker 守卫因此保留 env_cfg 的任务真值
        # （profile/训练源码），而不是拿硬默认 20.0 冒充真值。
        _episode_length_s = config.get("episode_length_s")
        if _episode_length_s is not None:
            environment["episode_length_s"] = float(_episode_length_s)
        algorithm_config = {key: value for key, value in config.items() if key not in {"task_name", "algorithm", "reward_scales", "num_envs", "episode_length_s", "terrain_type"}}
        backend = str(config.get("backend", "native_mjlab"))
        if backend != "native_mjlab":
            raise ValueError("Legged Studio training supports only the native_mjlab backend")
        return TrainingRecipe(task_name=task_name, algorithm=algorithm, backend=backend, reward_scales=rewards, environment=environment, algorithm_config=algorithm_config, seed=int(config.get("seed", 0)))
    # U9：通用表不认识的任务名，若是合法包扩展档案的产物逻辑名则按包扩展解析
    # （豁免只发生在通用表本会 400 的请求上；通用任务一律照旧，产物零漂移）。
    profile = _package_extension_profile(config, task_name)
    if profile is not None:
        return _resolve_package_extension_recipe(config, profile)
    raise ValueError(f"unknown task {task_name}; available: {', '.join(sorted(TASKS))}")


def list_tasks() -> list[dict[str, Any]]:
    return [{"id": key, **value, "reward_terms": list(get_reward_terms())} for key, value in TASKS.items()]
