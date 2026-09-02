"""
MJLab Training Adapter
基于 MJLab 和 RC_WheelLeg 的训练适配器
"""

import sys
import json
import numpy as np
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

# 导入 Contract
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from contracts.robot_contract_v2 import RobotContractV2
from contracts.policy_artifact import PolicyArtifact, TrainingMetrics
from adapters.mjlab.algorithms.registry import create_algorithm
from adapters.mjlab.algorithms.off_policy import OffPolicyAlgorithm


def resolve_torch_device(requested: str = "auto") -> str:
    """Resolve a user device request without silently hiding CUDA failures."""
    import torch

    value = str(requested or "auto").strip().lower()
    if value == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if value == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        return "cuda"
    if value.startswith("cuda:"):
        if not torch.cuda.is_available():
            raise RuntimeError(f"{value} was requested but CUDA is unavailable")
        try:
            index = int(value.split(":", 1)[1])
        except ValueError as exc:
            raise ValueError(f"invalid CUDA device {requested!r}") from exc
        if index < 0 or index >= torch.cuda.device_count():
            raise ValueError(f"CUDA device index {index} is out of range (count={torch.cuda.device_count()})")
        return f"cuda:{index}"
    if value == "cpu":
        return "cpu"
    raise ValueError(f"unsupported device {requested!r}; use auto, cpu, cuda, or cuda:N")


def runtime_device_info(device: str) -> dict[str, Any]:
    import torch

    info: dict[str, Any] = {
        "requested": device,
        "resolved": device,
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_version": torch.version.cuda,
        "cuda_device_count": int(torch.cuda.device_count()),
    }
    if device.startswith("cuda") and torch.cuda.is_available():
        index = torch.device(device).index or 0
        props = torch.cuda.get_device_properties(index)
        info.update({
            "cuda_device_index": index,
            "cuda_device_name": props.name,
            "cuda_total_memory_bytes": int(props.total_memory),
        })
    return info


@dataclass
class TrainingConfig:
    """训练配置"""
    algorithm: str = "PPO"
    num_envs: int = 4096
    max_iterations: int = 1000
    save_interval: int = 100

    # PPO 参数
    learning_rate: float = 3e-4
    num_steps: int = 24
    num_minibatches: int = 4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_param: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 1.0

    # 环境参数
    episode_length_s: float = 20.0
    task_name: str = "forward_walk"
    terrain_type: str = "plane"
    device: str = "auto"
    reward_scales: Dict[str, float] = field(default_factory=dict)
    seed: int = 0
    backend: str = "local_mujoco"
    resolved_recipe: Dict[str, Any] = field(default_factory=dict)

    # Off-policy algorithm parameters. They are ignored by PPO but remain in
    # the resolved recipe so a run can be reproduced from one config shape.
    tau: float = 0.005
    batch_size: int = 256
    replay_size: int = 100_000
    alpha: float = 0.2
    policy_delay: int = 2
    exploration_noise: float = 0.1
    target_noise: float = 0.2
    target_noise_clip: float = 0.5

    def to_dict(self) -> dict:
        return self.__dict__


class MJLabTrainingAdapter:
    """
    MJLab 训练适配器
    基于 Robot Contract 创建环境并执行训练
    """

    def __init__(
        self,
        contract: RobotContractV2,
        config: TrainingConfig,
        output_dir: str
    ):
        self.contract = contract
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.env = None
        self.agent = None
        self.metrics_history = []
        self.started_at = None
        self.runtime_device = "cpu"
        self.runtime_info: dict[str, Any] = {}

    def setup_environment(self):
        """设置训练环境"""
        print("[Adapter] Setting up environment...")

        # 这里需要根据实际的 MJLab API 创建环境
        # 参考 RC_WheelLeg 的 env.py

        from adapters.mjlab.env_factory import EnvFactory, get_reward_preset
        reward_scales = get_reward_preset(self.config.task_name)
        reward_scales.update(self.config.reward_scales)
        env_config = EnvFactory.create_from_contract(self.contract, {
            "num_envs": self.config.num_envs,
            "episode_length_s": self.config.episode_length_s,
            "terrain": {"terrain_type": self.config.terrain_type, "measure_heights": True},
            "reward_scales": reward_scales,
        })

        # 保存环境配置
        with open(self.output_dir / "env_config.json", 'w') as f:
            json.dump(env_config, f, indent=2)

        from adapters.mjlab.mujoco_env import ContractMujocoEnv
        self.env = ContractMujocoEnv(
            self.contract,
            self.config.num_envs,
            self.config.episode_length_s,
            seed=self.config.seed,
            reward_scales=reward_scales,
            command_ranges=env_config.get("command_ranges"),
        )

        print(f"[Adapter] Environment configured with {self.config.num_envs} envs")

        # TODO: 实际创建 mjlab 环境
        # from mjlab import create_env
        # self.env = create_env(env_config)

    def setup_agent(self):
        """设置训练智能体（PPO/SAC/TD3）"""
        print(f"[Adapter] Setting up {self.config.algorithm} agent...")

        agent_config = self.config.to_dict()

        # 保存智能体配置
        with open(self.output_dir / "agent_config.json", 'w') as f:
            json.dump(agent_config, f, indent=2)

        self.runtime_device = resolve_torch_device(self.config.device)
        self.runtime_info = runtime_device_info(self.runtime_device)
        (self.output_dir / "runtime.json").write_text(
            json.dumps(self.runtime_info, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[Adapter] Runtime device: {self.runtime_device} ({self.runtime_info.get('cuda_device_name', 'CPU')})")

        self.agent = create_algorithm(
            name=self.config.algorithm,
            num_obs=self.contract.observation.dimension,
            num_actions=self.contract.action.dimension,
            config=agent_config,
            device=self.runtime_device,
        )

    def train(
        self,
        progress_callback: Optional[Callable[[dict], None]] = None
    ) -> PolicyArtifact:
        """
        执行训练

        Args:
            progress_callback: 进度回调函数，接收 {"iteration": int, "metrics": dict}

        Returns:
            PolicyArtifact: 训练产物
        """
        print("[Adapter] Starting training...")

        # 设置环境和智能体
        self.setup_environment()
        self.setup_agent()

        self.started_at = time.time()
        observations = self.env.reset()
        num_steps = max(4, self.config.num_steps)
        for iteration in range(self.config.max_iterations):
            self.env.resample_commands()
            if isinstance(self.agent, OffPolicyAlgorithm):
                metrics_history = []
                for _ in range(num_steps):
                    actions, _ = self.agent.act(observations, deterministic=False)
                    next_observations, rewards, dones, _ = self.env.step(actions)
                    self.agent.add_transition(observations, actions, rewards, next_observations, dones.astype(np.float32))
                    update_metrics = self.agent.update()
                    metrics_history.append(update_metrics)
                    observations = next_observations
                    if np.any(dones):
                        reset_observations = self.env.reset()
                        observations[dones] = reset_observations[dones]
                metrics = {
                    "iteration": iteration,
                    "reward_mean": float(np.mean(rewards)),
                    "reward_std": float(np.std(rewards)),
                    "episode_length": num_steps,
                    "learning_rate": self.config.learning_rate,
                    "device": self.runtime_device,
                    **(metrics_history[-1] if metrics_history else {}),
                }
                self.metrics_history.append(metrics)
                if progress_callback:
                    progress_callback(metrics)
                if (iteration + 1) % self.config.save_interval == 0:
                    self._save_checkpoint(iteration)
                continue
            rollout_obs, rollout_actions, rollout_rewards, rollout_dones, rollout_values, rollout_log_probs = [], [], [], [], [], []
            for _ in range(num_steps):
                actions, values, log_probs = self.agent.act_with_log_prob(observations)
                next_observations, rewards, dones, _ = self.env.step(actions)
                rollout_obs.append(observations)
                rollout_actions.append(actions)
                rollout_rewards.append(rewards)
                rollout_dones.append(dones.astype(np.float32))
                rollout_values.append(values)
                rollout_log_probs.append(log_probs)
                observations = next_observations
                if np.any(dones):
                    observations[dones] = self.env.reset()[dones]
            next_values = self.agent.act(observations, deterministic=True)[1].reshape(-1)
            rewards = np.asarray(rollout_rewards, dtype=np.float32)
            dones = np.asarray(rollout_dones, dtype=np.float32)
            values = np.asarray(rollout_values, dtype=np.float32)
            returns, advantages = self.agent.compute_returns(rewards, dones, values, next_values)
            update_metrics = self.agent.update(
                np.asarray(rollout_obs).reshape(-1, self.contract.observation.dimension),
                np.asarray(rollout_actions).reshape(-1, self.contract.action.dimension),
                returns.reshape(-1), advantages.reshape(-1), np.asarray(rollout_log_probs).reshape(-1),
            )
            metrics = {"iteration": iteration, "reward_mean": float(rewards.mean()), "reward_std": float(rewards.std()), "episode_length": num_steps, "learning_rate": self.config.learning_rate, "device": self.runtime_device, **update_metrics}

            self.metrics_history.append(metrics)

            # 回调
            if progress_callback:
                progress_callback(metrics)

            # 保存检查点
            if (iteration + 1) % self.config.save_interval == 0:
                self._save_checkpoint(iteration)

            # 打印进度
            if (iteration + 1) % 10 == 0:
                print(f"[Adapter] Iteration {iteration + 1}/{self.config.max_iterations} "
                      f"- Reward: {metrics['reward_mean']:.2f}")

        self.env.close()
        print("[Adapter] Training completed!")

        # 保存最终模型
        final_model_path = self._save_final_model()

        # 创建 Policy Artifact
        artifact = self._create_artifact(final_model_path)

        return artifact

    def _save_checkpoint(self, iteration: int):
        """保存检查点"""
        checkpoint_dir = self.output_dir / "checkpoints"
        checkpoint_dir.mkdir(exist_ok=True)

        checkpoint_path = checkpoint_dir / f"model_{iteration:04d}.pt"

        self.agent.save(str(checkpoint_path))

        print(f"[Adapter] Checkpoint saved: {checkpoint_path}")

    def _save_final_model(self) -> str:
        """保存最终模型"""
        model_path = self.output_dir / "model_final.pt"

        self.agent.save(str(model_path))

        print(f"[Adapter] Final model saved: {model_path}")

        return str(model_path)

    def _create_artifact(self, model_path: str) -> PolicyArtifact:
        """创建 Policy Artifact"""
        import hashlib

        # 计算模型哈希
        with open(model_path, 'rb') as f:
            model_hash = hashlib.sha256(f.read()).hexdigest()

        # 计算训练指标
        final_metrics = self.metrics_history[-1] if self.metrics_history else {}
        avg_reward = np.mean([m['reward_mean'] for m in self.metrics_history[-100:]])

        # 创建 Artifact
        from contracts.policy_artifact import create_artifact_from_training

        artifact = create_artifact_from_training(
            contract=self.contract,
            task_name=self.config.task_name,
            algorithm=self.config.algorithm,
            model_path=model_path,
            metrics=TrainingMetrics(
                iterations=self.config.max_iterations,
                episodes=self.config.num_envs * self.config.max_iterations,
                success_rate=float(np.mean([m.get('reward_mean', 0.0) > 0 for m in self.metrics_history])) if self.metrics_history else 0.0,
                avg_reward=avg_reward,
                final_reward=final_metrics.get('reward_mean', 0.0),
                training_duration_seconds=time.time() - self.started_at if self.started_at else 0.0
            ),
            algorithm_config=self.config.to_dict(),
            obs_normalizer={"mean": [], "std": []},
            mjlab_version="1.6.0-contract-mujoco",
            tags=["training", self.contract.robot_id]
        )

        # 保存 Artifact
        artifact_path = self.output_dir / "artifact.json"
        artifact.to_json_file(str(artifact_path))

        print(f"[Adapter] Artifact created: {artifact_path}")

        return artifact


# ========== 便捷函数 ==========

def train_from_contract(
    contract: RobotContractV2,
    config: Optional[TrainingConfig] = None,
    output_dir: Optional[str] = None,
    progress_callback: Optional[Callable] = None
) -> PolicyArtifact:
    """
    从 Contract 开始训练

    Args:
        contract: Robot Contract
        config: 训练配置，None 使用默认
        output_dir: 输出目录，None 自动生成
        progress_callback: 进度回调

    Returns:
        PolicyArtifact
    """
    if config is None:
        config = TrainingConfig()

    if output_dir is None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"outputs/training_{contract.contract_id}_{timestamp}"

    adapter = MJLabTrainingAdapter(
        contract=contract,
        config=config,
        output_dir=output_dir
    )

    artifact = adapter.train(progress_callback=progress_callback)

    return artifact


if __name__ == "__main__":
    # 测试
    from contracts.robot_contract_v2 import create_go2_contract

    contract = create_go2_contract()

    # 快速测试配置
    config = TrainingConfig(
        num_envs=64,
        max_iterations=5,
        save_interval=2
    )

    def progress_callback(metrics):
        print(f"Progress: Iteration {metrics['iteration']}, Reward: {metrics['reward_mean']:.2f}")

    artifact = train_from_contract(
        contract=contract,
        config=config,
        progress_callback=progress_callback
    )

    print("\nTraining completed!")
    print("Artifact summary:")
    print(json.dumps(artifact.get_summary(), indent=2))
