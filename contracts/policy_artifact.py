"""
Policy Artifact
训练产物的完整记录（基于 RoboLab Artifact）
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import json


class TrainingMetrics(BaseModel):
    """训练指标"""
    iterations: int
    episodes: int
    success_rate: float = Field(ge=0.0, le=1.0)
    avg_reward: float
    final_reward: float
    training_duration_seconds: float

    # 额外指标
    forward_velocity: Optional[float] = None
    stability_score: Optional[float] = None
    energy_efficiency: Optional[float] = None


class ONNXValidation(BaseModel):
    """ONNX 验证结果"""
    exported: bool
    onnx_path: str
    max_numerical_diff: float
    opset_version: int
    input_shape: List[int]
    output_shape: List[int]
    inference_time_ms: float


class Sim2SimResult(BaseModel):
    """Sim2Sim 迁移测试结果"""
    source_env: str  # "mjlab"
    target_env: str  # "mujoco" / "isaacgym"
    source_success_rate: float
    target_success_rate: float
    performance_drop: float  # (source - target) / source
    tested_at: datetime


class PolicyArtifact(BaseModel):
    """
    Policy Artifact - 训练产物的完整记录
    包含所有复现和部署所需的信息
    """

    # ========== 基础信息 ==========
    artifact_id: str = Field(..., pattern="^[a-z0-9_-]+$")
    created_at: datetime = Field(default_factory=datetime.now)
    artifact_version: str = "1.0"

    # ========== Robot Contract（固化）==========
    robot_contract_id: str
    robot_contract_hash: str  # SHA-256，用于验证兼容性
    robot_contract_snapshot: Dict[str, Any]  # 完整 Contract 快照

    # ========== 训练配置 ==========
    task_name: str  # "forward_walk" / "trot" / "rough_terrain"
    algorithm: str  # "PPO" / "SAC" / "TD3"
    algorithm_config: Dict[str, Any]

    # ========== 训练结果 ==========
    metrics: TrainingMetrics

    # ========== 模型文件 ==========
    pytorch_model_path: str
    pytorch_model_hash: str  # SHA-256
    onnx_model_path: Optional[str] = None
    onnx_model_hash: Optional[str] = None

    # ========== Normalizer（必须固化）==========
    obs_normalizer: Dict[str, List[float]]  # {"mean": [...], "std": [...]}
    action_scale: float = 1.0

    # ========== 环境版本 ==========
    environment: str  # "mjlab"
    mjlab_version: str
    python_version: str
    pytorch_version: str
    cuda_version: str

    # ========== 验证报告 ==========
    onnx_validation: Optional[ONNXValidation] = None
    sim2sim_result: Optional[Sim2SimResult] = None

    # ========== 部署信息 ==========
    deployment_ready: bool = False
    deployment_notes: str = ""

    # ========== 元数据 ==========
    description: str = ""
    tags: List[str] = []
    author: str = ""

    def to_json_file(self, path: str):
        """保存为 JSON 文件"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.model_dump(), f, indent=2, default=str)

    @classmethod
    def from_json_file(cls, path: str) -> 'PolicyArtifact':
        """从 JSON 文件加载"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 转换时间戳
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)

    def is_compatible_with_contract(self, contract_hash: str) -> bool:
        """检查是否与指定 Contract 兼容"""
        return self.robot_contract_hash == contract_hash

    def get_summary(self) -> dict:
        """获取摘要信息"""
        return {
            "artifact_id": self.artifact_id,
            "task": self.task_name,
            "algorithm": self.algorithm,
            "success_rate": f"{self.metrics.success_rate * 100:.1f}%",
            "avg_reward": f"{self.metrics.avg_reward:.2f}",
            "iterations": self.metrics.iterations,
            "onnx_exported": self.onnx_model_path is not None,
            "deployment_ready": self.deployment_ready,
            "contract_hash": self.robot_contract_hash[:8] + "..."
        }

    def validate_integrity(self) -> bool:
        """验证 Artifact 完整性"""
        # 检查模型文件存在
        if not Path(self.pytorch_model_path).exists():
            return False

        # 检查哈希
        import hashlib
        with open(self.pytorch_model_path, 'rb') as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        if actual_hash != self.pytorch_model_hash:
            return False

        # 如果有 ONNX，也检查
        if self.onnx_model_path:
            if not Path(self.onnx_model_path).exists():
                return False
            with open(self.onnx_model_path, 'rb') as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != self.onnx_model_hash:
                return False

        return True


# ========== 工厂函数 ==========

def create_artifact_from_training(
    contract: 'RobotContractV2',
    task_name: str,
    algorithm: str,
    model_path: str,
    metrics: TrainingMetrics,
    **kwargs
) -> PolicyArtifact:
    """从训练结果创建 Artifact"""
    import hashlib
    import sys
    import torch

    # 计算模型哈希
    with open(model_path, 'rb') as f:
        model_hash = hashlib.sha256(f.read()).hexdigest()

    # 创建 Artifact
    artifact = PolicyArtifact(
        artifact_id=f"{contract.contract_id}_{task_name}_{algorithm.lower()}_v1",
        robot_contract_id=contract.contract_id,
        robot_contract_hash=contract.compute_hash(),
        robot_contract_snapshot=contract.model_dump(),

        task_name=task_name,
        algorithm=algorithm,
        algorithm_config=kwargs.get('algorithm_config', {}),

        metrics=metrics,

        pytorch_model_path=model_path,
        pytorch_model_hash=model_hash,

        obs_normalizer=kwargs.get('obs_normalizer', {"mean": [], "std": []}),
        action_scale=contract.action.action_scale,

        environment="mjlab",
        mjlab_version=kwargs.get('mjlab_version', "1.0.0"),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        pytorch_version=torch.__version__,
        cuda_version=torch.version.cuda or "N/A",

        description=kwargs.get('description', ""),
        tags=kwargs.get('tags', []),
        author=kwargs.get('author', "legged_studio")
    )

    return artifact


if __name__ == "__main__":
    # 测试
    from contracts.robot_contract_v2 import create_go2_contract

    contract = create_go2_contract()

    artifact = create_artifact_from_training(
        contract=contract,
        task_name="forward_walk",
        algorithm="PPO",
        model_path="outputs/model.pt",
        metrics=TrainingMetrics(
            iterations=1000,
            episodes=4096,
            success_rate=0.92,
            avg_reward=150.3,
            final_reward=180.5,
            training_duration_seconds=7200,
            forward_velocity=1.5
        ),
        tags=["mvp", "go2", "locomotion"]
    )

    print("Policy Artifact Created:")
    print(json.dumps(artifact.get_summary(), indent=2))
