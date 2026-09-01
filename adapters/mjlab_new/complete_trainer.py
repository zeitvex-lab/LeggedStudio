"""Compatibility entry point for the Contract-driven MuJoCo trainer."""

import numpy as np
import torch
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import time

from contracts.robot_contract_v2 import RobotContractV2
from contracts.policy_artifact import PolicyArtifact, TrainingMetrics, create_artifact_from_training
from adapters.mjlab_new.training_adapter import MJLabTrainingAdapter, TrainingConfig


class RunningMeanStd:
    """运行时均值和标准差（用于 Normalizer）"""

    def __init__(self, shape):
        self.mean = np.zeros(shape, dtype=np.float32)
        self.var = np.ones(shape, dtype=np.float32)
        self.count = 1e-4

    def update(self, x):
        """更新统计量"""
        batch_mean = np.mean(x, axis=0)
        batch_var = np.var(x, axis=0)
        batch_count = x.shape[0]

        self.update_from_moments(batch_mean, batch_var, batch_count)

    def update_from_moments(self, batch_mean, batch_var, batch_count):
        """从 moments 更新"""
        delta = batch_mean - self.mean
        total_count = self.count + batch_count

        new_mean = self.mean + delta * batch_count / total_count
        m_a = self.var * self.count
        m_b = batch_var * batch_count
        M2 = m_a + m_b + delta ** 2 * self.count * batch_count / total_count
        new_var = M2 / total_count

        self.mean = new_mean
        self.var = new_var
        self.count = total_count


class CompleteTrainer:
    """
    Backwards-compatible wrapper around the real MuJoCo/PPO adapter.

    Older callers can keep using ``CompleteTrainer`` while all new training
    flows share the same Contract-driven environment and artifact semantics.
    """

    def __init__(
        self,
        contract: RobotContractV2,
        config: Dict[str, Any],
        output_dir: str
    ):
        self.contract = contract
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = dict(config)
        self.adapter = MJLabTrainingAdapter(
            contract=contract,
            config=TrainingConfig(**{key: value for key, value in self.config.items() if key in TrainingConfig.__annotations__}),
            output_dir=output_dir,
        )

    def train(
        self,
        progress_callback: Optional[Callable[[dict], None]] = None
    ) -> PolicyArtifact:
        """Execute real MuJoCo rollouts and PPO updates."""
        return self.adapter.train(progress_callback=progress_callback)

# ========== 便捷函数 ==========

def train_go2_forward_walk(output_dir: Optional[str] = None) -> PolicyArtifact:
    """训练 Go2 forward walk（快速测试）"""
    from contracts.robot_contract_v2 import create_go2_contract

    contract = create_go2_contract()

    if output_dir is None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"outputs/go2_forward_walk_{timestamp}"

    config = {
        "task_name": "forward_walk",
        "num_envs": 64,  # 快速测试
        "max_iterations": 10,
        "learning_rate": 3e-4,
        "episode_length_s": 20.0
    }

    trainer = CompleteTrainer(contract, config, output_dir)

    def progress_callback(metrics):
        if metrics['iteration'] % 2 == 0:
            print(f"  Iteration {metrics['iteration']}: "
                  f"Reward={metrics['reward_mean']:.2f}, "
                  f"Success={metrics['success_rate']*100:.1f}%")

    artifact = trainer.train(progress_callback=progress_callback)

    return artifact


if __name__ == "__main__":
    print("=" * 70)
    print("Complete Training Integration Test")
    print("=" * 70)
    print()

    artifact = train_go2_forward_walk()

    print("\n" + "=" * 70)
    print("Training completed!")
    print("=" * 70)
    print("\nArtifact summary:")
    import json
    print(json.dumps(artifact.get_summary(), indent=2))
