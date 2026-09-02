"""
MJLab Training Worker
独立进程训练脚本
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from contracts.robot_contract_v2 import RobotContractV2
from adapters.mjlab.training_adapter import TrainingConfig, MJLabTrainingAdapter


def save_progress(output_dir: Path, progress: dict):
    """保存进度"""
    progress_file = output_dir / "progress.json"
    with open(progress_file, 'w') as f:
        json.dump(progress, f, indent=2)


def append_metrics(output_dir: Path, metrics: dict) -> None:
    with (output_dir / "metrics.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(metrics, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="MJLab Training Worker")
    parser.add_argument("--contract", required=True, help="Contract JSON path")
    parser.add_argument("--config", required=True, help="Training config JSON path")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--task-id", required=True, help="Task ID")

    args = parser.parse_args()

    print("=" * 70)
    print("MJLab Training Worker")
    print("=" * 70)
    print(f"Task ID: {args.task_id}")
    print(f"Contract: {args.contract}")
    print(f"Config: {args.config}")
    print(f"Output: {args.output}")
    print("=" * 70)
    print()

    # 加载 Contract
    print("[Worker] Loading Contract...")
    contract = RobotContractV2.from_json_file(args.contract)
    print(f"[Worker] Contract loaded: {contract.contract_id}")
    print(f"[Worker] Robot: {contract.family} ({contract.robot_id})")
    print()

    # 加载训练配置
    print("[Worker] Loading training config...")
    with open(args.config, 'r') as f:
        config_dict = json.load(f)

    config = TrainingConfig(**config_dict)
    print(f"[Worker] Algorithm: {config.algorithm}")
    print(f"[Worker] Envs: {config.num_envs}")
    print(f"[Worker] Iterations: {config.max_iterations}")
    print()

    # 创建适配器
    adapter = MJLabTrainingAdapter(
        contract=contract,
        config=config,
        output_dir=args.output
    )

    # 进度回调
    def progress_callback(metrics: dict):
        # 保存进度
        progress = {
            "iteration": metrics["iteration"],
            "max_iterations": config.max_iterations,
            "progress": (metrics["iteration"] + 1) / config.max_iterations,
            "reward_mean": metrics.get("reward_mean", 0.0),
            "updated_at": datetime.now().isoformat()
        }

        save_progress(Path(args.output), progress)
        append_metrics(Path(args.output), metrics)

        # 打印进度
        print(f"[Worker] Iteration {metrics['iteration'] + 1}/{config.max_iterations} "
              f"({progress['progress'] * 100:.1f}%) - "
              f"Reward: {metrics.get('reward_mean', 0.0):.2f}")

    # 开始训练
    try:
        print("[Worker] Starting training...")
        print()

        artifact = adapter.train(progress_callback=progress_callback)

        print()
        print("[Worker] Training completed successfully!")
        print(f"[Worker] Artifact: {artifact.artifact_id}")
        print(f"[Worker] Success rate: {artifact.metrics.success_rate * 100:.1f}%")
        print(f"[Worker] Avg reward: {artifact.metrics.avg_reward:.2f}")

        # 保存最终状态
        final_status = {
            "status": "completed",
            "artifact_id": artifact.artifact_id,
            "success_rate": artifact.metrics.success_rate,
            "avg_reward": artifact.metrics.avg_reward,
            "device": adapter.runtime_device,
            "runtime": adapter.runtime_info,
            "completed_at": datetime.now().isoformat()
        }

        status_file = Path(args.output) / "status.json"
        with open(status_file, 'w') as f:
            json.dump(final_status, f, indent=2)

        return 0

    except KeyboardInterrupt:
        print()
        print("[Worker] Training interrupted by user")
        return 130

    except Exception as e:
        print()
        print(f"[Worker] Training failed: {e}")
        import traceback
        traceback.print_exc()

        # 保存错误状态
        error_status = {
            "status": "failed",
            "error": str(e),
            "failed_at": datetime.now().isoformat()
        }

        status_file = Path(args.output) / "status.json"
        with open(status_file, 'w') as f:
            json.dump(error_status, f, indent=2)

        return 1


if __name__ == "__main__":
    sys.exit(main())
