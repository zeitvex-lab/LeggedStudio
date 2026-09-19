"""
Robot Contract V2
基于 RoboLab TensorContract + RC_WheelLeg 部署契约
统一的机器人配置标准
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import hashlib
import json
from contracts.asset_paths import resolve_asset_path


class ObservationSpec(BaseModel):
    """观测规格"""
    dimension: int
    components: List[str]  # ["base_lin_vel", "base_ang_vel", "joint_pos", ...]
    normalizer: Optional[Dict[str, List[float]]] = None  # {"mean": [...], "std": [...]}


class ActionSpec(BaseModel):
    """动作规格"""
    dimension: int
    joint_order: List[str]  # 明确的关节顺序
    action_scale: float = 1.0
    action_clip: Optional[List[float]] = None  # [min, max]


class JointConfig(BaseModel):
    """关节配置"""
    actuated_joints: List[str]  # 驱动关节（腿）
    passive_joints: List[str] = []  # 被动关节（轮）
    joint_limits: Optional[Dict[str, List[float]]] = None  # {joint_name: [min, max]}
    default_pose: List[float]  # 默认站姿

    @field_validator('default_pose')
    def validate_pose_length(cls, v, info):
        actuated = info.data.get('actuated_joints', [])
        if len(v) != len(actuated):
            raise ValueError(f"default_pose length must match actuated_joints")
        return v


class URDFInfo(BaseModel):
    """URDF 信息"""
    path: str
    hash: str  # SHA-256
    total_mass_kg: float
    # 对齐 v3 真值词表（morphology.mass_source：mjcf_compiled=取编译后 MJCF inertial，
    # 本仓 14 包全部为此；urdf_inertial=取 URDF inertial）。旧四值词表早已被 4 个包的
    # 存量数据越界（mj_model/mjcf-sum/mjcf_inertial_sum），create 层如实拒但挡的是自家机型。
    mass_source: str = Field(
        ...,
        pattern="^(mjcf_compiled|urdf_inertial)$"
    )
    mesh_files: List[str] = []

    @field_validator('path')
    def validate_path_exists(cls, v):
        if not resolve_asset_path(v).exists():
            raise ValueError(f"URDF file not found: {v}")
        return v


class ControlConfig(BaseModel):
    """控制配置"""
    control_hz: int = 50
    physics_hz: int = 1000
    decimation: int = Field(default=20, ge=1)  # physics_hz / control_hz

    @field_validator('decimation')
    def validate_decimation(cls, v, info):
        physics_hz = info.data.get('physics_hz', 1000)
        control_hz = info.data.get('control_hz', 50)
        expected = physics_hz // control_hz
        if v != expected:
            raise ValueError(f"decimation should be {expected}")
        return v


class DeploymentMapping(BaseModel):
    """部署映射（参考 RC_WheelLeg）"""
    can_bus_mapping: Optional[Dict[str, int]] = None  # {joint_name: can_id}
    motor_direction: Optional[Dict[str, int]] = None  # {joint_name: ±1}
    zero_offset: Optional[Dict[str, float]] = None  # {joint_name: offset_rad}


class ContractLegacyV2(BaseModel):
    """
    Robot Contract V2
    统一的机器人配置契约，贯穿验证→训练→评估→部署
    """

    # ========== 基础信息 ==========
    schema_version: str = "robot-contract-2.0"
    contract_id: str = Field(..., pattern="^[a-z0-9_-]+$")
    created_at: datetime = Field(default_factory=datetime.now)

    # ========== 机器人标识 ==========
    robot_id: str  # go2, a1, etc.
    family: str  # "Unitree Go2"
    size_class: str = Field(..., pattern="^(S|M|L)$")
    # v2 兼容视图对齐 v3 真值：P/W 之外 B（双足）与 H（人形）早已是 14 包现实
    #（v3 schema 枚举与 contracts/locomotion_view.LOCOMOTION_ENUM 同源）；此前 create 层
    # 拿旧 pattern 校验会把 g1/wuji_hand 等直接拒之门外（L7 多机型试跑实测抓到）。
    locomotion_type: str = Field(..., pattern="^(P|B|W|H)$")

    # ========== URDF 信息 ==========
    urdf: URDFInfo

    # ========== 关节配置 ==========
    joints: JointConfig

    # ========== 观测/动作规格 ==========
    observation: ObservationSpec
    action: ActionSpec

    # ========== 控制配置 ==========
    control: ControlConfig

    # ========== 部署映射（可选）==========
    deployment: Optional[DeploymentMapping] = None

    # ========== 元数据 ==========
    description: str = ""
    tags: List[str] = []
    source: str = ""  # 来源（用户创建/URDF Studio/导入）

    # ========== 版本和兼容性 ==========
    min_mjlab_version: str = "1.0.0"
    python_version: str = "3.12"

    def compute_hash(self) -> str:
        """计算 Contract 的 SHA-256 哈希"""
        # 排除时间戳，只哈希核心配置
        core_dict = self.model_dump(
            exclude={'created_at', 'description', 'tags', 'source'}
        )
        content = json.dumps(core_dict, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def to_json_file(self, path: str):
        """保存为 JSON 文件"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.model_dump(), f, indent=2, default=str)

    @classmethod
    def from_json_file(cls, path: str) -> 'ContractLegacyV2':
        """从 JSON 文件加载"""
        # Accept contracts created by Windows editors and PowerShell, which
        # commonly prepend a UTF-8 BOM.
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        return cls(**data)

    def validate_compatibility(self, artifact_contract_hash: str) -> bool:
        """验证与 Policy Artifact 的兼容性"""
        return self.compute_hash() == artifact_contract_hash

    def get_summary(self) -> dict:
        """获取摘要信息"""
        return {
            "contract_id": self.contract_id,
            "robot": f"{self.family} ({self.robot_id})",
            "classification": f"{self.size_class}-{self.locomotion_type}",
            "dof": len(self.joints.actuated_joints),
            "obs_dim": self.observation.dimension,
            "act_dim": self.action.dimension,
            "urdf_hash": self.urdf.hash[:8],
            "contract_hash": self.compute_hash()[:8]
        }


# ========== 工厂函数 ==========

def create_go2_contract() -> ContractLegacyV2:
    """创建 Go2 的标准 Contract（MVP 主线）"""
    canonical_fixture = Path(__file__).parent / "fixtures" / "unitree_go2.v2.json"
    if canonical_fixture.exists():
        return ContractLegacyV2.from_json_file(str(canonical_fixture))

    return ContractLegacyV2(
        contract_id="go2_mvp_v1",
        robot_id="go2",
        family="Unitree Go2",
        size_class="M",
        locomotion_type="P",

        urdf=URDFInfo(
            path="assets/go2_description/urdf/go2.urdf",
            hash="",  # 需要计算
            total_mass_kg=15.0,
            mass_source="urdf_inertial"
        ),

        joints=JointConfig(
            actuated_joints=[
                "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
                "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
                "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
                "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint"
            ],
            passive_joints=[],
            default_pose=[0.0] * 12
        ),

        observation=ObservationSpec(
            dimension=48,  # 示例：3(base_vel) + 3(ang_vel) + 12(joint_pos) + 12(joint_vel) + 18(...)
            components=[
                "base_lin_vel",
                "base_ang_vel",
                "projected_gravity",
                "joint_pos",
                "joint_vel",
                "last_action"
            ]
        ),

        action=ActionSpec(
            dimension=12,
            joint_order=[
                "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
                "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
                "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
                "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint"
            ],
            action_scale=0.25
        ),

        control=ControlConfig(
            control_hz=50,
            physics_hz=1000,
            decimation=20
        ),

        description="Unitree Go2 MVP Contract - M-P classification",
        tags=["mvp", "go2", "point-foot"],
        source="manual_creation"
    )


if __name__ == "__main__":
    # 测试
    contract = create_go2_contract()
    print("Go2 Contract Created:")
    print(json.dumps(contract.get_summary(), indent=2))
    print(f"\nContract Hash: {contract.compute_hash()}")
