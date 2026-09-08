"""Robot Contract v3 Pydantic models.

本文件与 contracts/schema/robot-contract-3.0.schema.json 逐字段对齐。
生成方式：python tools/generate_contract_models.py（datamodel-code-generator，
当前为按 schema 手工种子的等价实现，parity 由 contracts/tests 守护——
新增 schema 字段时必须同步本文件与 web/shared/generated/types.d.ts）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "robot-contract-3.0"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "robot-contract-3.0.schema.json"


class _V3Model(BaseModel):
    """schema 顶层 additionalProperties=true → extra=allow（前向兼容）。"""

    model_config = ConfigDict(extra="allow")


class ActuatorParamsV3(_V3Model):
    """$defs/actuatorParams：执行器参数（角色/关节/默认三级共用）。"""

    stiffness: Optional[float] = Field(default=None, ge=0)
    damping: Optional[float] = Field(default=None, ge=0)
    effort: Optional[float] = Field(default=None, ge=0)
    velocity_limit: Optional[float] = Field(default=None, ge=0)
    armature: Optional[float] = Field(default=None, ge=0)
    friction_loss: Optional[float] = Field(default=None, ge=0)
    mode: Optional[Literal["position", "velocity", "torque"]] = None
    action_scale: Optional[float] = Field(default=None, gt=0)


class MorphologySpec(_V3Model):
    """Layer 1：构型——代码唯一允许分支的维度。"""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    legs: int = Field(ge=0, le=8)
    leg_pattern: list[str] = Field(default_factory=list)
    leg_naming: str = Field(..., description="支持 {LR} 与 {role} 占位符")
    leg_ids: Optional[list[str]] = None
    actuated_via: Optional[str] = None
    extra_roles: Optional[list[str]] = None


class JointEntryV3(_V3Model):
    """Layer 3 条目：名字 + 归属 + 角色，不携带数值。"""

    name: str = Field(min_length=1)
    leg: Optional[str] = None
    role: str


class PassiveJointV3(_V3Model):
    name: str = Field(min_length=1)
    role: Optional[str] = None
    note: Optional[str] = None


class JointsSpecV3(_V3Model):
    actuated: list[JointEntryV3] = Field(min_length=1)
    passive: Optional[list[PassiveJointV3]] = None
    default_pose: Optional[list[float]] = None
    joint_limits: Optional[dict[str, dict[str, float]]] = None


class ActuatorProfileV3(_V3Model):
    default: Optional[ActuatorParamsV3] = None
    by_role: dict[str, ActuatorParamsV3] = Field(default_factory=dict)
    by_joint: dict[str, ActuatorParamsV3] = Field(default_factory=dict)


class ActionSpecV3(_V3Model):
    dimension: Optional[int] = Field(default=None, ge=1)
    joint_order: list[str] = Field(min_length=1)
    reindex_from_model: Optional[list[int]] = None
    action_scale: Optional[float] = Field(default=None, gt=0)
    action_clip: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)


class ObservationComponentV3(_V3Model):
    name: str = Field(min_length=1)
    width: int = Field(ge=1)
    scale: Optional[float] = None
    source: Literal["imu", "cmd", "actuated", "action", "world", "external"]
    wrap: Optional[bool] = None


class ObservationSpecV3(_V3Model):
    kind: Optional[str] = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    # components 为空 = 宽度声明待补全（v2 迁移的 history/视觉类观测）
    components: list[ObservationComponentV3] = Field(default_factory=list)
    dimension: int = Field(ge=0)
    normalizer: Optional[dict[str, Any]] = None


class ControlSpecV3(_V3Model):
    control_hz: Optional[int] = Field(default=None, ge=10, le=1000)
    physics_hz: Optional[int] = Field(default=None, ge=100, le=10000)
    decimation: Optional[int] = Field(default=None, ge=1)


class TaskRequirements(_V3Model):
    """$defs/taskRequirements：任务/算法包的对称需求声明（预埋，报告 6 §4.6）。"""

    requires_morphology: Optional[list[str]] = None
    requires_roles: Optional[list[str]] = None
    observation_template: Optional[str] = None
    action_role_order: Optional[list[str]] = None
    min_obs_dimension: Optional[int] = Field(default=None, ge=1)


class RobotContractV3(_V3Model):
    schema_version: Literal["robot-contract-3.0"] = SCHEMA_VERSION
    contract_id: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_-]+$")
    robot_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    family: Optional[str] = None
    morphology: MorphologySpec
    joints: JointsSpecV3
    actuator_profile: ActuatorProfileV3
    action: ActionSpecV3
    observation: ObservationSpecV3
    control: Optional[ControlSpecV3] = None
    default_pose: Optional[list[float]] = None
    size_class: Optional[Literal["S", "M", "L"]] = None
    locomotion_type: Optional[Literal["P", "W", "B", "H"]] = None
    urdf: Optional[dict[str, Any]] = None
    deployment: Optional[dict[str, Any]] = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    created_at: Optional[str] = None
    evidence: Optional[list[dict[str, Any]]] = None


def parse_v3(payload: dict[str, Any]) -> RobotContractV3:
    """从 dict 构造并校验契约 v3。"""

    return RobotContractV3.model_validate(payload)


def dump_v3(contract: RobotContractV3) -> dict[str, Any]:
    """导出为 schema 兼容 dict（roundtrip 用）。"""

    return contract.model_dump(mode="json", exclude_none=True)


def load_schema() -> dict[str, Any]:
    """读取 schema 真值源。"""

    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)
