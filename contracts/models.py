"""MVP Pydantic contracts for robot assets and adaptation presets.

Only Pydantic is required at runtime.  The models use the Pydantic v1 API
surface where possible, so the package also works in environments that have not
yet migrated to v2.  Inventory facts are deliberately kept close to the JSON
schema emitted by ``tools/scan_quadruped_assets.py``.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, Field, root_validator, validator


class SizeClass(str, Enum):
    """Legged Studio mass taxonomy (half-open intervals)."""

    S = "S"  # 0 < mass_kg < 15
    M = "M"  # 15 <= mass_kg < 35
    L = "L"  # mass_kg >= 35


SizeClassLike = SizeClass | Literal["S", "M", "L"]


class Readiness(str, Enum):
    """Asset preparation level reported by the scanner."""

    DIRECT_MUJOCO_CANDIDATE = "direct_mujoco_candidate"
    MORPHOLOGY_ONLY = "morphology_only"
    ADAPTER_REQUIRED = "adapter_required"
    REPAIR_REQUIRED = "repair_required"
    SUPPORTING = "supporting"
    STATIC_CANDIDATE = "static_candidate"


class AssetRole(str, Enum):
    ROBOT = "robot"
    SCENE = "scene"
    TASK_FRAGMENT = "task_fragment"


class Locomotion(str, Enum):
    POINT_FOOT = "point_foot"
    WHEELED_LEG = "wheeled_leg"


def size_class_for_mass(mass_kg: float | int | None) -> SizeClass | None:
    """Return the canonical S/M/L bucket for a positive mass in kilograms.

    ``None`` is returned for missing or non-positive mass because scene/task
    fragments have no robot body mass.  The intervals intentionally match the
    inventory and product documents: S < 15, M >= 15 and < 35, L >= 35.
    """

    if mass_kg is None:
        return None
    mass = float(mass_kg)
    if mass <= 0:
        return None
    if mass < 15:
        return SizeClass.S
    if mass < 35:
        return SizeClass.M
    return SizeClass.L


class _Model(BaseModel):
    """Pydantic v1/v2-compatible base with forward-compatible extra fields."""

    class Config:
        extra = "allow"
        validate_assignment = True


class AssetRecord(_Model):
    """One record from ``QUADRUPED_ASSET_INVENTORY.json``."""

    path: str
    format: str
    model_name: Optional[str] = None
    family: Optional[str] = None
    quadruped: bool = True
    leg_groups_detected: list[str] = Field(default_factory=list)
    role: AssetRole = AssetRole.ROBOT
    sha256: Optional[str] = None
    bytes: Optional[int] = Field(default=None, ge=0)
    link_count: Optional[int] = Field(default=None, ge=0)
    joint_count: Optional[int] = Field(default=None, ge=0)
    # MJCF-specific topology counters.  URDF records normally leave these null.
    body_count: Optional[int] = Field(default=None, ge=0)
    free_joint_count: Optional[int] = Field(default=None, ge=0)
    movable_joint_count: Optional[int] = Field(default=None, ge=0)
    fixed_joint_count: Optional[int] = Field(default=None, ge=0)
    actuator_count: Optional[int] = Field(default=None, ge=0)
    actuated_joint_count: Optional[int] = Field(default=None, ge=0)
    joint_type_counts: dict[str, int] = Field(default_factory=dict)
    joint_names: list[str] = Field(default_factory=list)
    mass_body_count: Optional[int] = Field(default=None, ge=0)
    mass_body_total: Optional[int] = Field(default=None, ge=0)
    locomotion: Optional[Locomotion] = None
    wheel_joint_count: Optional[int] = Field(default=None, ge=0)
    wheel_actuator_count: Optional[int] = Field(default=None, ge=0)
    explicit_mass_kg: Optional[float] = Field(default=None, ge=0)
    classification_mass_kg: Optional[float] = Field(default=None, ge=0)
    classification_mass_source: Optional[str] = None
    size_class_by_mass: Optional[SizeClass] = None
    explicit_mass_term_count: Optional[int] = Field(default=None, ge=0)
    mesh_ref_count: Optional[int] = Field(default=None, ge=0)
    missing_mesh_ref_count: Optional[int] = Field(default=None, ge=0)
    missing_mesh_refs: list[str] = Field(default_factory=list)
    include_ref_count: Optional[int] = Field(default=None, ge=0)
    missing_include_ref_count: Optional[int] = Field(default=None, ge=0)
    missing_include_refs: list[str] = Field(default_factory=list)
    quality: Optional[str] = None
    duplicate_group: Optional[int | str] = None
    mujoco_probe: Optional[dict[str, Any]] = None
    readiness: Optional[Readiness] = None

    @root_validator(skip_on_failure=True)
    def fill_or_validate_size_class(cls, values: dict[str, Any]) -> dict[str, Any]:
        mass = values.get("classification_mass_kg")
        expected = size_class_for_mass(mass)
        declared = values.get("size_class_by_mass")
        if declared is None and expected is not None:
            values["size_class_by_mass"] = expected
        elif declared is not None and expected is not None and declared != expected.value:
            raise ValueError(
                "size_class_by_mass does not match classification_mass_kg "
                f"({declared!r} != {expected.value!r})"
            )
        return values

    @property
    def is_robot(self) -> bool:
        return self.role == AssetRole.ROBOT and self.quadruped

    @property
    def usable(self) -> bool:
        """Whether the record is a reasonable candidate for adapter work."""

        return (
            self.is_robot
            and self.quality not in {"rejected", "parse_error"}
            and self.readiness != Readiness.REPAIR_REQUIRED
            and (self.missing_mesh_ref_count or 0) == 0
            and (self.missing_include_ref_count or 0) == 0
        )


class InventoryDocument(_Model):
    """Validated top-level inventory document."""

    schema_version: str
    document_role: Optional[str] = None
    human_summary: Optional[str] = None
    product_docs: list[str] = Field(default_factory=list)
    workspace: Optional[str] = None
    size_taxonomy: dict[str, Any] = Field(default_factory=dict)
    scan_scope: dict[str, Any] = Field(default_factory=dict)
    mujoco_probe: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    records: list[AssetRecord] = Field(default_factory=list)
    duplicate_groups: list[Any] = Field(default_factory=list)
    parse_errors: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def robot_assets(self) -> list[AssetRecord]:
        return [record for record in self.records if record.is_robot]


class JointMapping(_Model):
    """Map each canonical joint to external vector indices.

    Each index list is parallel to ``canonical_order``.  MuJoCo values are qpos
    addresses, not zero-based joint ordinals; a floating base therefore usually
    makes the first articulated joint start at qpos index 7.
    """

    canonical_order: list[str]
    training_indices: list[int]
    mujoco_indices: list[int]
    deploy_indices: list[int]
    direction_multipliers: Optional[list[float]] = None

    @root_validator(skip_on_failure=True)
    def validate_lengths(cls, values: dict[str, Any]) -> dict[str, Any]:
        names = values.get("canonical_order") or []
        for key in ("training_indices", "mujoco_indices", "deploy_indices"):
            indices = values.get(key) or []
            if len(indices) != len(names):
                raise ValueError(f"{key} must have one entry per canonical joint")
            if len(set(indices)) != len(indices) or any(index < 0 for index in indices):
                raise ValueError(f"{key} must contain unique non-negative indices")
        directions = values.get("direction_multipliers")
        if directions is not None and len(directions) != len(names):
            raise ValueError("direction_multipliers must have one entry per canonical joint")
        if directions is not None and any(value not in (-1.0, 1.0) for value in directions):
            raise ValueError("direction_multipliers values must be -1 or 1")
        return values


class CoordinateFrame(_Model):
    name: str
    parent: Optional[str] = None
    quaternion_order: Literal["wxyz", "xyzw"] = "wxyz"
    description: str = ""


class ContractEvidence(_Model):
    """A local source supporting one or more contract fields."""

    source_id: str
    path: str
    sha256: str
    supports: list[str]
    note: str = ""

    @validator("source_id")
    def validate_source_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9_]+", value):
            raise ValueError("source_id must contain only lowercase letters, digits, and underscores")
        return value

    @validator("sha256")
    def validate_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value

    @validator("supports")
    def validate_supports(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("supports must contain at least one non-empty field path")
        return value


class RobotContract(_Model):
    """Versioned interface consumed by a simulator, policy, or deploy adapter."""

    schema_version: str = "robot-contract-1.0"
    robot_id: str
    model_revision: str
    joints: JointMapping
    actuated_joint_names: list[str]
    passive_joint_names: list[str] = Field(default_factory=list)
    control_hz: Optional[int] = Field(default=None, ge=10, le=1000)
    physics_hz: Optional[int] = Field(default=None, ge=100, le=10000)
    action_scale: Optional[float] = Field(default=None, gt=0, le=1.0)
    default_pose: Optional[list[float]] = None
    frames: dict[str, CoordinateFrame] = Field(default_factory=dict)
    description: str = ""
    maintainer: str = ""
    source_repo: str = ""
    asset_path: Optional[str] = None
    asset_family: Optional[str] = None
    evidence: list[ContractEvidence] = Field(default_factory=list)

    @validator("robot_id")
    def validate_robot_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9_]+", value):
            raise ValueError("robot_id must contain only lowercase letters, digits, and underscores")
        return value

    @root_validator(skip_on_failure=True)
    def validate_pose_and_rates(cls, values: dict[str, Any]) -> dict[str, Any]:
        actuated = values.get("actuated_joint_names") or []
        pose = values.get("default_pose")
        if pose is not None and len(pose) != len(actuated):
            raise ValueError(
                f"default_pose length {len(pose)} does not match actuated joints {len(actuated)}"
            )
        if values.get("physics_hz") and values.get("control_hz"):
            if values["physics_hz"] % values["control_hz"] != 0:
                raise ValueError("physics_hz must be an integer multiple of control_hz")
        if len(set(actuated)) != len(actuated):
            raise ValueError("actuated_joint_names must be unique")
        canonical = (values.get("joints") or {}).canonical_order if values.get("joints") else []
        if actuated != canonical:
            raise ValueError("actuated_joint_names must match joints.canonical_order")
        source_ids = [source.source_id for source in values.get("evidence") or []]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("evidence source_id values must be unique")
        return values


def load_inventory(path: str | Path) -> InventoryDocument:
    """Load and validate an inventory JSON file."""

    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    # Prefer the v2 API while retaining the v1 fallback.
    model_validate = getattr(InventoryDocument, "model_validate", None)
    if model_validate is not None:
        return model_validate(payload)
    return InventoryDocument.parse_obj(payload)


def load_robot_contract(path: str | Path) -> RobotContract:
    """Load and validate a versioned Robot Contract JSON fixture."""

    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    model_validate = getattr(RobotContract, "model_validate", None)
    if model_validate is not None:
        return model_validate(payload)
    return RobotContract.parse_obj(payload)


def load_asset_records(path: str | Path, **filters: Any) -> list[AssetRecord]:
    """Load an inventory and return records matching ``filter_assets`` kwargs."""

    return filter_assets(load_inventory(path).records, **filters)


def filter_assets(
    records: Iterable[AssetRecord],
    *,
    family: str | Sequence[str] | None = None,
    size_class: SizeClassLike | None = None,
    locomotion: Locomotion | str | None = None,
    readiness: Readiness | str | Sequence[Readiness | str] | None = None,
    role: AssetRole | str | None = AssetRole.ROBOT,
    usable_only: bool = False,
) -> list[AssetRecord]:
    """Filter asset records without mutating inventory data.

    ``family`` and ``readiness`` accept either one value or a sequence.  By
    default only robot records are returned; pass ``role=None`` to include
    scenes and task fragments.
    """

    def values(value: Any) -> set[str] | None:
        if value is None:
            return None
        if isinstance(value, (str, Enum)):
            return {value.value if isinstance(value, Enum) else value}
        return {item.value if isinstance(item, Enum) else str(item) for item in value}

    families = values(family)
    sizes = values(size_class)
    locomotions = values(locomotion)
    readinesses = values(readiness)
    roles = values(role)
    result: list[AssetRecord] = []
    for record in records:
        if families is not None and record.family not in families:
            continue
        if sizes is not None and (record.size_class_by_mass is None or record.size_class_by_mass.value not in sizes):
            continue
        if locomotions is not None and (record.locomotion is None or record.locomotion.value not in locomotions):
            continue
        if readinesses is not None and (record.readiness is None or record.readiness.value not in readinesses):
            continue
        if roles is not None and record.role.value not in roles:
            continue
        if usable_only and not record.usable:
            continue
        result.append(record)
    return result
