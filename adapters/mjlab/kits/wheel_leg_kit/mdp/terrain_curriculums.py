# ------------------------------------------------------------------------------
# 越障技能族级化（2026-09-25）：本文件由 zex-w 包
# ``assets/robots/zex-w/training/source/robot/mdp/curriculums.py`` 的**地形级课程**
# 四函数逐字上移（``terrain_levels_vel_strict`` / ``terrain_levels_ramp_strict`` /
# ``terrain_levels_flat_warmup`` / ``terrain_levels_obstacle_release``）。
#
# 为什么它们是**族级**：四者只依赖 mjlab 的地形实体与命令管理器接口
# （``env.scene.terrain`` 的 terrain_levels / terrain_types / terrain_origins，
# 以及 ``command_name`` 指向的命令项），不含任何机型关节 / 尺寸 / 质量引用；
# "障碍释放课程"（``terrain_levels_obstacle_release``）就是族级越障课程的课程项。
#
# 包侧 ``robot/mdp/curriculums.py`` 保留同名再导出（入口不变），命令课程
# （adaptive_command_vel / command_axis_levels_vel / command_levels_adaptive）留包。
# ------------------------------------------------------------------------------
"""Terrain-level curricula shared by the wheel-leg family (verbatim move)."""

from __future__ import annotations

from typing import TYPE_CHECKING
import torch

from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def terrain_levels_vel_strict(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    command_name: str,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> dict[str, torch.Tensor]:
    """Velocity-based terrain curriculum aligned with standard legged_gym logic.

    Upgrade:   robot travels beyond half the terrain tile width (> 4m).
    Downgrade: actual distance < 50% of commanded target distance.

    This matches DreamWaQ / HIMLoco / LocoLeggedWheel curriculum behaviour:
    - Promotion is easy (any traversal past 4m qualifies).
    - Demotion requires consistently failing to cover half the expected distance.
    """
    asset: Entity = env.scene[asset_cfg.name]

    terrain = env.scene.terrain
    assert terrain is not None
    terrain_generator = terrain.cfg.terrain_generator
    assert terrain_generator is not None

    command = env.command_manager.get_command(command_name)
    assert command is not None

    # Horizontal displacement from episode start
    distance = torch.norm(
        asset.data.root_link_pos_w[env_ids, :2] - env.scene.env_origins[env_ids, :2],
        dim=1,
    )

    cmd_speed = torch.norm(command[env_ids, :2], dim=1)

    # Upgrade: crossed half the tile width
    move_up = distance > terrain_generator.size[0] / 2

    # Downgrade: traveled less than 33% of commanded target distance.
    # Absolute threshold ≈ cmd_speed × 10m, identical to DreamWaQ / HIMLoco / LocoLeggedWheel
    # which use 50% × 20s episode = 10m. Adjusted for the longer 30s episode here.
    move_down = (distance < cmd_speed * env.max_episode_length_s * 0.33) & ~move_up



    terrain.update_env_origins(env_ids, move_up, move_down)

    levels = terrain.terrain_levels.float()
    result: dict[str, torch.Tensor] = {
        "mean": torch.mean(levels),
        "max": torch.max(levels),
    }

    sub_terrain_names = list(terrain_generator.sub_terrains.keys())
    terrain_origins = terrain.terrain_origins
    assert terrain_origins is not None
    num_cols = terrain_origins.shape[1]
    if num_cols == len(sub_terrain_names):
        types = terrain.terrain_types
        for i, name in enumerate(sub_terrain_names):
            mask = types == i
            if mask.any():
                result[name] = torch.mean(levels[mask])

    return result


def terrain_levels_ramp_strict(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    command_name: str,
    ramp_steps: int = 50 * 24,
    move_up_expected_distance_ratio: float = 0.60,
    move_down_distance_ratio: float = 0.50,
    min_command_speed: float = 0.15,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> dict[str, torch.Tensor]:
    """Terrain curriculum active from start, with strict promotion and time-ramped max level."""
    asset: Entity = env.scene[asset_cfg.name]
    terrain = env.scene.terrain
    assert terrain is not None
    terrain_generator = terrain.cfg.terrain_generator
    assert terrain_generator is not None
    assert terrain.terrain_origins is not None
    assert terrain.env_origins is not None

    command = env.command_manager.get_command(command_name)
    assert command is not None

    distance = torch.norm(
        asset.data.root_link_pos_w[env_ids, :2] - env.scene.env_origins[env_ids, :2],
        dim=1,
    )
    cmd_speed = torch.norm(command[env_ids, :2], dim=1)
    active_command = cmd_speed >= min_command_speed

    expected_distance = cmd_speed * env.max_episode_length_s
    move_up = (distance > expected_distance * move_up_expected_distance_ratio) & active_command
    move_down = (
        (distance < expected_distance * move_down_distance_ratio)
        & active_command
        & ~move_up
    )

    terrain.terrain_levels[env_ids] += 1 * move_up - 1 * move_down

    max_level = max(int(terrain.max_terrain_level) - 1, 0)
    if ramp_steps <= 0:
        level_cap = max_level
    else:
        progress = max(0.0, min(1.0, env.common_step_counter / ramp_steps))
        level_cap = int(round(progress * max_level))
    terrain.terrain_levels[env_ids] = torch.clamp(
        terrain.terrain_levels[env_ids],
        min=0,
        max=min(level_cap, max_level),
    )

    terrain.env_origins[env_ids] = terrain.terrain_origins[
        terrain.terrain_levels[env_ids], terrain.terrain_types[env_ids]
    ]

    levels = terrain.terrain_levels.float()
    result: dict[str, torch.Tensor] = {
        "mean": torch.mean(levels),
        "max": torch.max(levels),
        "level_cap": torch.tensor(float(level_cap), device=env.device),
    }

    sub_terrain_names = list(terrain_generator.sub_terrains.keys())
    num_cols = terrain.terrain_origins.shape[1]
    if num_cols == len(sub_terrain_names):
        types = terrain.terrain_types
        for i, name in enumerate(sub_terrain_names):
            mask = types == i
            if mask.any():
                result[name] = torch.mean(levels[mask])

    return result


def terrain_levels_flat_warmup(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    command_name: str,
    warmup_steps: int = 4800,
    flat_terrain_name: str = "flat",
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> dict[str, torch.Tensor]:
    """Keep all reset envs on flat level 0 before enabling terrain curriculum."""
    terrain = env.scene.terrain
    assert terrain is not None
    terrain_generator = terrain.cfg.terrain_generator
    assert terrain_generator is not None
    assert terrain.terrain_origins is not None
    assert terrain.env_origins is not None

    sub_terrain_names = list(terrain_generator.sub_terrains.keys())
    flat_type = sub_terrain_names.index(flat_terrain_name) if flat_terrain_name in sub_terrain_names else 0

    if env.common_step_counter < warmup_steps:
        terrain.terrain_levels[env_ids] = 0
        terrain.terrain_types[env_ids] = flat_type
        terrain.env_origins[env_ids] = terrain.terrain_origins[0, flat_type]
        if not hasattr(terrain, "_flat_warmup_env_released"):
            terrain._flat_warmup_env_released = torch.zeros(
                env.num_envs, dtype=torch.bool, device=env.device
            )
        terrain._flat_warmup_env_released[env_ids] = False

        levels = terrain.terrain_levels.float()
        result: dict[str, torch.Tensor] = {
            "mean": torch.mean(levels),
            "max": torch.max(levels),
            "warmup_active": torch.ones((), device=env.device),
        }
        for i, name in enumerate(sub_terrain_names):
            mask = terrain.terrain_types == i
            if mask.any():
                result[name] = torch.mean(levels[mask])
        return result

    if not hasattr(terrain, "_flat_warmup_released"):
        terrain._flat_warmup_released = True
        terrain._flat_warmup_release_counts = 0
    if not hasattr(terrain, "_flat_warmup_env_released"):
        terrain._flat_warmup_env_released = torch.zeros(
            env.num_envs, dtype=torch.bool, device=env.device
        )

    newly_released = env_ids[~terrain._flat_warmup_env_released[env_ids]]
    if len(newly_released) > 0:
        proportions = torch.tensor(
            [sub.proportion for sub in terrain_generator.sub_terrains.values()],
            device=env.device,
            dtype=torch.float,
        )
        proportions = proportions / torch.clamp(proportions.sum(), min=1.0e-6)
        terrain.terrain_types[newly_released] = torch.multinomial(
            proportions, len(newly_released), replacement=True
        )
        terrain.terrain_levels[newly_released] = 0
        terrain.env_origins[newly_released] = terrain.terrain_origins[
            terrain.terrain_levels[newly_released], terrain.terrain_types[newly_released]
        ]
        terrain._flat_warmup_env_released[newly_released] = True
        terrain._flat_warmup_release_counts += len(newly_released)

    result = terrain_levels_vel_strict(env, env_ids, command_name, asset_cfg=asset_cfg)
    result["warmup_active"] = torch.zeros((), device=env.device)
    result["released_envs"] = torch.tensor(float(getattr(terrain, "_flat_warmup_release_counts", 0)), device=env.device)
    return result


def terrain_levels_obstacle_release(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    command_name: str,
    release_schedule: tuple[tuple[int, tuple[str, ...]], ...],
    initial_terrain_names: tuple[str, ...] = ("flat", "random_rough", "perlin_noise", "sloped_terrain"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> dict[str, torch.Tensor]:
    """Release obstacle terrain types gradually while keeping standard level progression."""
    terrain = env.scene.terrain
    assert terrain is not None
    terrain_generator = terrain.cfg.terrain_generator
    assert terrain_generator is not None
    assert terrain.terrain_origins is not None
    assert terrain.env_origins is not None

    sub_terrain_names = list(terrain_generator.sub_terrains.keys())
    allowed_names = list(initial_terrain_names)
    for step, names in release_schedule:
        if env.common_step_counter >= step:
            allowed_names.extend(names)
    allowed_type_ids = [
        sub_terrain_names.index(name) for name in allowed_names if name in sub_terrain_names
    ]
    if not allowed_type_ids:
        allowed_type_ids = [0]

    if not hasattr(terrain, "_obstacle_release_env_allowed"):
        terrain._obstacle_release_env_allowed = torch.zeros(
            env.num_envs, dtype=torch.bool, device=env.device
        )
        terrain._last_allowed_count = len(allowed_type_ids)

    # If new terrains were released, force all envs to eventually resample upon their next reset
    if len(allowed_type_ids) > terrain._last_allowed_count:
        terrain._obstacle_release_env_allowed.fill_(False)
        terrain._last_allowed_count = len(allowed_type_ids)

    allowed_tensor = torch.tensor(allowed_type_ids, dtype=torch.long, device=env.device)
    current_allowed = torch.isin(terrain.terrain_types[env_ids], allowed_tensor)
    need_resample = env_ids[~terrain._obstacle_release_env_allowed[env_ids] | ~current_allowed]

    if len(need_resample) > 0:
        proportions = torch.tensor(
            [terrain_generator.sub_terrains[sub_terrain_names[i]].proportion for i in allowed_type_ids],
            device=env.device,
            dtype=torch.float,
        )
        proportions = proportions / torch.clamp(proportions.sum(), min=1.0e-6)
        sampled = allowed_tensor[torch.multinomial(proportions, len(need_resample), replacement=True)]

        # Check which envs actually changed terrain type
        changed_mask = terrain.terrain_types[need_resample] != sampled
        changed_envs = need_resample[changed_mask]

        terrain.terrain_types[need_resample] = sampled
        # Only reset the level to 0 if the terrain type was actually changed
        if len(changed_envs) > 0:
            terrain.terrain_levels[changed_envs] = 0

        terrain.env_origins[need_resample] = terrain.terrain_origins[
            terrain.terrain_levels[need_resample], terrain.terrain_types[need_resample]
        ]
        terrain._obstacle_release_env_allowed[need_resample] = True

    result = terrain_levels_vel_strict(env, env_ids, command_name, asset_cfg=asset_cfg)
    result["allowed_types"] = torch.tensor(float(len(allowed_type_ids)), device=env.device)
    for name in ("pyramid_stairs", "pyramid_stairs_inv", "random_grid", "rc_wall"):
        result[f"{name}_released"] = torch.tensor(float(name in allowed_names), device=env.device)
    return result
