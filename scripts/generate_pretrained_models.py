"""
Pretrained Model Generator
生成预训练模型（Go2 forward walk 和 trot）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from contracts.robot_contract_v2 import create_go2_contract
from adapters.mjlab.complete_trainer import CompleteTrainer
from datetime import datetime
import json


def train_go2_forward_walk():
    """训练 Go2 forward walk 模型"""
    print("=" * 70)
    print("Training Go2 Forward Walk Model")
    print("=" * 70)
    print()

    contract = create_go2_contract()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"pretrained_models/go2_forward_walk_{timestamp}"

    config = {
        "task_name": "forward_walk",
        "num_envs": 4096,
        "max_iterations": 1000,
        "learning_rate": 3e-4,
        "episode_length_s": 20.0,
        "reward_scales": {
            "tracking_lin_vel": 1.5,
            "tracking_ang_vel": 0.5,
            "orientation": -2.0,
            "base_height": -1.0,
            "torques": -0.0002,
            "action_rate": -0.01
        }
    }

    trainer = CompleteTrainer(contract, config, output_dir)

    def progress_callback(metrics):
        if (metrics['iteration'] + 1) % 50 == 0:
            print(f"  Iteration {metrics['iteration'] + 1}: "
                  f"Reward={metrics['reward_mean']:.2f}, "
                  f"Success={metrics['success_rate']*100:.1f}%")

    artifact = trainer.train(progress_callback=progress_callback)

    print("\n✅ Go2 Forward Walk model trained!")
    print(f"   Output: {output_dir}")
    print(f"   Success rate: {artifact.metrics.success_rate * 100:.1f}%")
    print(f"   Avg reward: {artifact.metrics.avg_reward:.2f}")

    return artifact


def train_go2_trot():
    """训练 Go2 trot 模型"""
    print("\n" + "=" * 70)
    print("Training Go2 Trot Model")
    print("=" * 70)
    print()

    contract = create_go2_contract()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"pretrained_models/go2_trot_{timestamp}"

    config = {
        "task_name": "trot",
        "num_envs": 4096,
        "max_iterations": 1000,
        "learning_rate": 3e-4,
        "episode_length_s": 20.0,
        "reward_scales": {
            "tracking_lin_vel": 2.0,
            "feet_air_time": 1.5,
            "orientation": -1.5,
            "torques": -0.0001,
            "action_rate": -0.02
        }
    }

    trainer = CompleteTrainer(contract, config, output_dir)

    def progress_callback(metrics):
        if (metrics['iteration'] + 1) % 50 == 0:
            print(f"  Iteration {metrics['iteration'] + 1}: "
                  f"Reward={metrics['reward_mean']:.2f}, "
                  f"Success={metrics['success_rate']*100:.1f}%")

    artifact = trainer.train(progress_callback=progress_callback)

    print("\n✅ Go2 Trot model trained!")
    print(f"   Output: {output_dir}")
    print(f"   Success rate: {artifact.metrics.success_rate * 100:.1f}%")
    print(f"   Avg reward: {artifact.metrics.avg_reward:.2f}")

    return artifact


def create_pretrained_models_index():
    """创建预训练模型索引"""
    pretrained_dir = Path("pretrained_models")

    if not pretrained_dir.exists():
        print("No pretrained models found")
        return

    models = []
    for artifact_file in pretrained_dir.glob("*/artifact.json"):
        with open(artifact_file, 'r') as f:
            artifact = json.load(f)

        models.append({
            "id": artifact["artifact_id"],
            "name": artifact["task_name"],
            "robot": artifact["robot_contract_snapshot"]["robot_id"],
            "algorithm": artifact["algorithm"],
            "success_rate": artifact["metrics"]["success_rate"],
            "avg_reward": artifact["metrics"]["avg_reward"],
            "path": str(artifact_file.parent)
        })

    # 保存索引
    index_path = pretrained_dir / "index.json"
    with open(index_path, 'w') as f:
        json.dump(models, f, indent=2)

    print(f"\n📋 Pretrained models index created: {index_path}")
    print(f"   Total models: {len(models)}")

    return models


if __name__ == "__main__":
    print("🚀 Generating Pretrained Models")
    print()

    # 训练模型
    artifact1 = train_go2_forward_walk()
    artifact2 = train_go2_trot()

    # 创建索引
    print("\n" + "=" * 70)
    models = create_pretrained_models_index()

    print("\n" + "=" * 70)
    print("✅ All pretrained models generated!")
    print("=" * 70)
