# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：本文件由 b2w_velocity/mdp/{name}.py **逐字上移**
# （== go2w_velocity 同名文件 sha256 一致；m20_velocity 同名文件亦逐字一致）。
# 包侧 mdp/__init__ 改为从本 kit 模块星导入，组合顺序与原 mdp/__init__ 相同。
# ------------------------------------------------------------------------------
"""Go2-W domain randomization.

``randomize_field`` is a generic MuJoCo model-field randomizer (friction,
mass, damping, ...) that the shared mjlab 1.6 distribution does not ship.
It is local to this package so the Go2-W velocity task can keep its
domain-randomization events without modifying the shared mjlab runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Literal, Tuple

import torch

from mjlab.entity import EntityIndexing
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.utils.lab_api.math import (
    sample_gaussian,
    sample_log_uniform,
    sample_uniform,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


class FieldSpec:
    """How a model field should be randomized (entity type + addressing)."""

    def __init__(
        self,
        entity_type: Literal["dof", "joint", "body", "geom", "site", "actuator"],
        use_address: bool = False,
        default_axes: list[int] | None = None,
        valid_axes: list[int] | None = None,
    ) -> None:
        self.entity_type = entity_type
        self.use_address = use_address
        self.default_axes = default_axes
        self.valid_axes = valid_axes


FIELD_SPECS = {
    "dof_armature": FieldSpec("dof", use_address=True),
    "dof_frictionloss": FieldSpec("dof", use_address=True),
    "dof_damping": FieldSpec("dof", use_address=True),
    "jnt_range": FieldSpec("joint"),
    "jnt_stiffness": FieldSpec("joint"),
    "body_mass": FieldSpec("body"),
    "body_ipos": FieldSpec("body", default_axes=[0, 1, 2]),
    "body_iquat": FieldSpec("body", default_axes=[0, 1, 2, 3]),
    "body_inertia": FieldSpec("body"),
    "body_pos": FieldSpec("body", default_axes=[0, 1, 2]),
    "body_quat": FieldSpec("body", default_axes=[0, 1, 2, 3]),
    "geom_friction": FieldSpec("geom", default_axes=[0], valid_axes=[0, 1, 2]),
    "geom_pos": FieldSpec("geom", default_axes=[0, 1, 2]),
    "geom_quat": FieldSpec("geom", default_axes=[0, 1, 2, 3]),
    "geom_rgba": FieldSpec("geom", default_axes=[0, 1, 2, 3]),
    "site_pos": FieldSpec("site", default_axes=[0, 1, 2]),
    "site_quat": FieldSpec("site", default_axes=[0, 1, 2, 3]),
    "qpos0": FieldSpec("joint", use_address=True),
}


def _get_entity_indices(
    indexing: EntityIndexing, asset_cfg, spec: FieldSpec
) -> torch.Tensor:
    match spec.entity_type:
        case "dof":
            return indexing.joint_v_adr[asset_cfg.joint_ids]
        case "joint" if spec.use_address:
            return indexing.joint_q_adr[asset_cfg.joint_ids]
        case "joint":
            return indexing.joint_ids[asset_cfg.joint_ids]
        case "body":
            return indexing.body_ids[asset_cfg.body_ids]
        case "geom":
            return indexing.geom_ids[asset_cfg.geom_ids]
        case "site":
            return indexing.site_ids[asset_cfg.site_ids]
        case "actuator":
            assert indexing.ctrl_ids is not None
            return indexing.ctrl_ids[asset_cfg.actuator_ids]
        case _:
            raise ValueError(f"Unknown entity type: {spec.entity_type}")


def _determine_target_axes(
    model_field,
    spec: FieldSpec,
    axes: list[int] | None,
    ranges: Tuple[float, float] | Dict[int, Tuple[float, float]],
) -> list[int]:
    field_ndim = len(model_field.shape) - 1  # Subtract env dimension

    if axes is not None:
        target_axes = axes
    elif isinstance(ranges, dict):
        target_axes = list(ranges.keys())
    elif spec.default_axes is not None:
        target_axes = spec.default_axes
    else:
        if field_ndim > 1:
            target_axes = list(range(model_field.shape[-1]))
        else:
            target_axes = [0]

    if spec.valid_axes is not None:
        invalid_axes = set(target_axes) - set(spec.valid_axes)
        if invalid_axes:
            raise ValueError(
                f"Invalid axes {invalid_axes} for field. Valid axes: {spec.valid_axes}"
            )

    return target_axes


def _prepare_axis_ranges(
    ranges: Tuple[float, float] | Dict[int, Tuple[float, float]],
    target_axes: list[int],
    field: str,
) -> Dict[int, Tuple[float, float]]:
    if isinstance(ranges, tuple):
        return {axis: ranges for axis in target_axes}
    elif isinstance(ranges, dict):
        missing_axes = set(target_axes) - set(ranges.keys())
        if missing_axes:
            raise ValueError(
                f"Missing ranges for axes {missing_axes} in field '{field}'. "
                f"Required axes: {target_axes}"
            )
        return {axis: ranges[axis] for axis in target_axes}
    else:
        raise TypeError(f"ranges must be tuple or dict, got {type(ranges)}")


def _sample_distribution(
    distribution: str,
    lower: torch.Tensor,
    upper: torch.Tensor,
    shape: tuple,
    device: str,
) -> torch.Tensor:
    if distribution == "uniform":
        return sample_uniform(lower, upper, shape, device=device)
    elif distribution == "log_uniform":
        return sample_log_uniform(lower, upper, shape, device=device)
    elif distribution == "gaussian":
        return sample_gaussian(lower, upper, shape, device=device)
    else:
        raise ValueError(f"Unknown distribution: {distribution}")


def _generate_random_values(
    distribution: str,
    axis_ranges: Dict[int, Tuple[float, float]],
    indexed_data: torch.Tensor,
    target_axes: list[int],
    device,
    operation: str,
) -> torch.Tensor:
    if operation == "scale":
        result = torch.ones_like(indexed_data)
    elif operation == "add":
        result = torch.zeros_like(indexed_data)
    else:
        assert operation == "abs"
        result = indexed_data.clone()

    for axis in target_axes:
        lower, upper = axis_ranges[axis]
        lower_bound = torch.tensor([lower], device=device)
        upper_bound = torch.tensor([upper], device=device)

        if len(indexed_data.shape) > 2:  # Multi-dimensional field.
            shape = (*indexed_data.shape[:-1], 1)
        else:
            shape = indexed_data.shape

        random_vals = _sample_distribution(distribution, lower_bound, upper_bound, shape, device)

        if len(indexed_data.shape) > 2:
            result[..., axis] = random_vals.squeeze(-1)
        else:
            result = random_vals

    return result


def _apply_operation(
    model_field,
    env_grid,
    entity_grid,
    indexed_data,
    random_values,
    operation,
) -> None:
    if operation == "add":
        model_field[env_grid, entity_grid] = indexed_data + random_values
    elif operation == "scale":
        model_field[env_grid, entity_grid] = indexed_data * random_values
    elif operation == "abs":
        model_field[env_grid, entity_grid] = random_values
    else:
        raise ValueError(f"Unknown operation: {operation}")


def randomize_field(
    env: "ManagerBasedRlEnv",
    env_ids: torch.Tensor | None,
    field: str,
    ranges: Tuple[float, float] | Dict[int, Tuple[float, float]],
    distribution: Literal["uniform", "log_uniform", "gaussian"] = "uniform",
    operation: Literal["add", "scale", "abs"] = "abs",
    asset_cfg=None,
    axes: list[int] | None = None,
) -> None:
    """Randomize a MuJoCo model field (friction, mass, damping, ...).

    For ``scale``/``add`` the stored default field is used so randomization
    does not accumulate across resets.
    """
    if field not in FIELD_SPECS:
        raise ValueError(
            f"Unknown field '{field}'. Supported fields: {list(FIELD_SPECS.keys())}"
        )

    spec = FIELD_SPECS[field]
    asset_cfg = asset_cfg or _DEFAULT_ASSET_CFG
    asset = env.scene[asset_cfg.name]

    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device, dtype=torch.int)
    else:
        env_ids = env_ids.to(env.device, dtype=torch.int)

    model_field = getattr(env.sim.model, field)

    entity_indices = _get_entity_indices(asset.indexing, asset_cfg, spec)
    target_axes = _determine_target_axes(model_field, spec, axes, ranges)
    axis_ranges = _prepare_axis_ranges(ranges, target_axes, field)

    env_grid, entity_grid = torch.meshgrid(env_ids, entity_indices, indexing="ij")
    indexed_data = model_field[env_grid, entity_grid]

    if operation in ("scale", "add"):
        default_field = env.sim.get_default_field(field)
        base_values = default_field[entity_indices].unsqueeze(0).expand_as(indexed_data)
    else:
        base_values = indexed_data

    random_values = _generate_random_values(
        distribution, axis_ranges, base_values, target_axes, env.device, operation
    )

    _apply_operation(model_field, env_grid, entity_grid, base_values, random_values, operation)
