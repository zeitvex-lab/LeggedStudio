"""
Policy Evaluator
策略评估工具（参考 RoboGauge 和 microduck）
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import numpy as np
from pathlib import Path
import json

from contracts.robot_contract_v2 import RobotContractV2
from contracts.policy_artifact import PolicyArtifact


@dataclass
class EpisodeResult:
    """单个 episode 结果"""
    episode_id: int
    total_reward: float
    episode_length: int
    success: bool
    forward_distance: float
    average_velocity: float
    energy_consumed: float
    max_height_deviation: float


@dataclass
class EvaluationMetrics:
    """评估指标"""
    # 基础统计
    num_episodes: int
    success_rate: float
    avg_reward: float
    std_reward: float
    avg_episode_length: float

    # 运动指标
    avg_forward_velocity: float
    std_forward_velocity: float
    avg_forward_distance: float

    # 稳定性指标
    avg_height_deviation: float
    stability_score: float

    # 能耗指标
    avg_energy: float
    energy_efficiency: float  # distance / energy

    # 分布
    reward_distribution: List[float]
    velocity_distribution: List[float]


@dataclass
class EvaluationResult:
    """完整评估结果"""
    artifact_id: str
    contract_id: str
    robot: str
    task: str

    metrics: EvaluationMetrics
    episodes: List[EpisodeResult]

    evaluated_at: str
    evaluation_config: Dict[str, Any]


class PolicyEvaluator:
    """
    策略评估器
    运行策略并收集性能指标
    """

    def __init__(
        self,
        contract: RobotContractV2,
        num_episodes: int = 100,
        deterministic: bool = True
    ):
        self.contract = contract
        self.num_episodes = num_episodes
        self.deterministic = deterministic

    def evaluate(
        self,
        artifact: PolicyArtifact,
        render: bool = False
    ) -> EvaluationResult:
        """
        评估策略

        Args:
            artifact: Policy Artifact
            render: 是否渲染（可视化）

        Returns:
            EvaluationResult
        """
        print(f"[Evaluator] Evaluating policy: {artifact.artifact_id}")
        print(f"[Evaluator] Running {self.num_episodes} episodes...")

        # 加载策略
        # TODO: 实际加载 PyTorch 模型
        # policy = self._load_policy(artifact)

        # 创建环境
        # TODO: 实际创建评估环境
        # env = self._create_eval_env()

        # 运行 episodes
        episodes = []
        for i in range(self.num_episodes):
            episode_result = self._run_episode(i, artifact, render=render)
            episodes.append(episode_result)

            if (i + 1) % 10 == 0:
                print(f"[Evaluator] Completed {i + 1}/{self.num_episodes} episodes")

        # 计算指标
        metrics = self._compute_metrics(episodes)

        # 创建结果
        from datetime import datetime
        result = EvaluationResult(
            artifact_id=artifact.artifact_id,
            contract_id=artifact.robot_contract_id,
            robot=self.contract.family,
            task=artifact.task_name,
            metrics=metrics,
            episodes=episodes,
            evaluated_at=datetime.now().isoformat(),
            evaluation_config={
                "num_episodes": self.num_episodes,
                "deterministic": self.deterministic
            }
        )

        print(f"\n[Evaluator] Evaluation completed!")
        print(f"  Success rate: {metrics.success_rate * 100:.1f}%")
        print(f"  Avg reward: {metrics.avg_reward:.2f}")
        print(f"  Avg velocity: {metrics.avg_forward_velocity:.2f} m/s")

        return result

    def _run_episode(
        self,
        episode_id: int,
        artifact: PolicyArtifact,
        render: bool = False
    ) -> EpisodeResult:
        """运行单个 episode"""

        # TODO: 实际运行策略
        # 临时：模拟结果
        total_reward = 150.0 + np.random.randn() * 20.0
        episode_length = 1000
        forward_distance = 20.0 + np.random.randn() * 3.0
        average_velocity = forward_distance / (episode_length * 0.02)  # 50Hz
        energy = 50.0 + np.random.randn() * 5.0
        height_deviation = 0.05 + np.random.rand() * 0.02

        success = total_reward > 100.0 and forward_distance > 15.0

        return EpisodeResult(
            episode_id=episode_id,
            total_reward=total_reward,
            episode_length=episode_length,
            success=success,
            forward_distance=forward_distance,
            average_velocity=average_velocity,
            energy_consumed=energy,
            max_height_deviation=height_deviation
        )

    def _compute_metrics(self, episodes: List[EpisodeResult]) -> EvaluationMetrics:
        """计算评估指标"""

        # 提取数据
        rewards = [ep.total_reward for ep in episodes]
        velocities = [ep.average_velocity for ep in episodes]
        distances = [ep.forward_distance for ep in episodes]
        energies = [ep.energy_consumed for ep in episodes]
        height_devs = [ep.max_height_deviation for ep in episodes]
        successes = [ep.success for ep in episodes]

        # 计算统计
        success_rate = sum(successes) / len(successes)
        avg_reward = np.mean(rewards)
        std_reward = np.std(rewards)
        avg_velocity = np.mean(velocities)
        std_velocity = np.std(velocities)
        avg_distance = np.mean(distances)
        avg_energy = np.mean(energies)
        avg_height_dev = np.mean(height_devs)

        # 稳定性评分（低高度偏差 + 低速度方差）
        stability_score = 1.0 / (1.0 + avg_height_dev + std_velocity * 0.1)

        # 能量效率
        energy_efficiency = avg_distance / avg_energy if avg_energy > 0 else 0.0

        return EvaluationMetrics(
            num_episodes=len(episodes),
            success_rate=success_rate,
            avg_reward=avg_reward,
            std_reward=std_reward,
            avg_episode_length=np.mean([ep.episode_length for ep in episodes]),
            avg_forward_velocity=avg_velocity,
            std_forward_velocity=std_velocity,
            avg_forward_distance=avg_distance,
            avg_height_deviation=avg_height_dev,
            stability_score=stability_score,
            avg_energy=avg_energy,
            energy_efficiency=energy_efficiency,
            reward_distribution=rewards,
            velocity_distribution=velocities
        )

    def save_result(self, result: EvaluationResult, output_path: str):
        """保存评估结果"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 转为字典（排除大列表）
        result_dict = {
            "artifact_id": result.artifact_id,
            "contract_id": result.contract_id,
            "robot": result.robot,
            "task": result.task,
            "evaluated_at": result.evaluated_at,
            "evaluation_config": result.evaluation_config,
            "metrics": {
                "num_episodes": result.metrics.num_episodes,
                "success_rate": result.metrics.success_rate,
                "avg_reward": result.metrics.avg_reward,
                "std_reward": result.metrics.std_reward,
                "avg_forward_velocity": result.metrics.avg_forward_velocity,
                "std_forward_velocity": result.metrics.std_forward_velocity,
                "avg_forward_distance": result.metrics.avg_forward_distance,
                "stability_score": result.metrics.stability_score,
                "energy_efficiency": result.metrics.energy_efficiency
            }
        }

        with open(output_path, 'w') as f:
            json.dump(result_dict, f, indent=2)

        print(f"[Evaluator] Result saved: {output_path}")


# ========== 便捷函数 ==========

def evaluate_artifact(
    artifact_path: str,
    contract_path: str,
    num_episodes: int = 100,
    output_path: Optional[str] = None
) -> EvaluationResult:
    """
    从文件评估 Artifact

    Args:
        artifact_path: Artifact JSON 路径
        contract_path: Contract JSON 路径
        num_episodes: 评估 episode 数
        output_path: 结果输出路径（可选）

    Returns:
        EvaluationResult
    """
    # 加载
    artifact = PolicyArtifact.from_json_file(artifact_path)
    contract = RobotContractV2.from_json_file(contract_path)

    # 评估
    evaluator = PolicyEvaluator(contract, num_episodes=num_episodes)
    result = evaluator.evaluate(artifact)

    # 保存
    if output_path:
        evaluator.save_result(result, output_path)

    return result


if __name__ == "__main__":
    # 测试
    from contracts.robot_contract_v2 import create_go2_contract
    from contracts.policy_artifact import create_artifact_from_training, TrainingMetrics

    # 创建测试 Artifact
    contract = create_go2_contract()
    artifact = create_artifact_from_training(
        contract=contract,
        task_name="forward_walk",
        algorithm="PPO",
        model_path="outputs/test_model.pt",
        metrics=TrainingMetrics(
            iterations=1000,
            episodes=4096,
            success_rate=0.85,
            avg_reward=150.0,
            final_reward=180.0,
            training_duration_seconds=7200
        )
    )

    # 评估
    evaluator = PolicyEvaluator(contract, num_episodes=10)
    result = evaluator.evaluate(artifact)

    print("\nEvaluation completed!")
    print(f"Success rate: {result.metrics.success_rate * 100:.1f}%")
    print(f"Avg reward: {result.metrics.avg_reward:.2f}")
    print(f"Avg velocity: {result.metrics.avg_forward_velocity:.2f} m/s")
    print(f"Stability: {result.metrics.stability_score:.3f}")
