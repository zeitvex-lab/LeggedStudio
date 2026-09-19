"""Native MJLab training facade.

The control plane starts :mod:`native_worker` in the locked adapter runtime.
This module keeps a small synchronous facade for CLI and legacy callers; it
does not create a local MuJoCo training environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from contracts.policy_artifact import PolicyArtifact
from contracts.contract_legacy_v2 import ContractLegacyV2
from backend.robot_packages import package_for_contract


def resolve_torch_device(requested: str = "auto") -> str:
    """Resolve a device inside the isolated MJLab runtime."""
    import torch

    value = str(requested or "auto").strip().lower()
    if value == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if value == "cpu":
        return "cpu"
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
            raise ValueError(f"CUDA device index {index} is out of range")
        return value
    raise ValueError(f"unsupported device {requested!r}; use auto, cpu, cuda, or cuda:N")


def runtime_device_info(device: str) -> dict[str, Any]:
    import torch

    info = {
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
        info.update({"cuda_device_index": index, "cuda_device_name": props.name, "cuda_total_memory_bytes": int(props.total_memory)})
    return info


@dataclass
class TrainingConfig:
    algorithm: str = "PPO"
    num_envs: int = 4096
    max_iterations: int = 1000
    save_interval: int = 100
    learning_rate: float = 3e-4
    num_steps: int = 24
    num_minibatches: int = 4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_param: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 1.0
    episode_length_s: float = 20.0
    task_name: str = "forward_walk"
    terrain_type: str = "plane"
    device: str = "auto"
    reward_scales: Dict[str, float] = field(default_factory=dict)
    seed: int = 0
    backend: str = "native_mjlab"
    resolved_recipe: Dict[str, Any] = field(default_factory=dict)
    tau: float = 0.005
    batch_size: int = 256
    replay_size: int = 100_000
    alpha: float = 0.2
    policy_delay: int = 2
    exploration_noise: float = 0.1
    target_noise: float = 0.2
    target_noise_clip: float = 0.5

    def __post_init__(self) -> None:
        if self.backend != "native_mjlab":
            raise ValueError("TrainingConfig only supports native_mjlab")
        if self.algorithm.upper() != "PPO":
            raise ValueError("native MJLab training currently supports PPO only")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class MJLabTrainingAdapter:
    """Synchronous facade over the manager-based native MJLab worker."""

    def __init__(self, contract: ContractLegacyV2, config: TrainingConfig, output_dir: str):
        self.contract = contract
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_device = "cpu"
        self.runtime_info: dict[str, Any] = {}

    def setup_environment(self) -> None:
        if self.config.backend != "native_mjlab":
            raise ValueError("MJLabTrainingAdapter only supports native_mjlab")

    def setup_agent(self) -> None:
        self.runtime_device = resolve_torch_device(self.config.device)
        self.runtime_info = runtime_device_info(self.runtime_device)
        (self.output_dir / "runtime.json").write_text(json.dumps(self.runtime_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def train(self, progress_callback: Optional[Callable[[dict[str, Any]], None]] = None) -> PolicyArtifact:
        self.setup_environment()
        self.setup_agent()
        from adapters.mjlab.native_adapter import DEFAULT_EXTENSION, DEFAULT_SOURCE
        from adapters.mjlab.native_worker import run

        contract_path = self.output_dir / "contract.json"
        self.contract.to_json_file(str(contract_path))
        package = package_for_contract(self.contract.model_dump(mode="json"))
        config = {**self.config.to_dict(), "backend": "native_mjlab", "mode": "train", "robot_package": package, "generic_task": True, "contract_path": str(contract_path.resolve())}
        exit_code = run(config, DEFAULT_SOURCE, self.output_dir, DEFAULT_EXTENSION)
        if exit_code != 0:
            raise RuntimeError(f"native MJLab worker exited with code {exit_code}")
        artifact_path = self.output_dir / "artifact.json"
        if not artifact_path.exists():
            raise RuntimeError("native MJLab worker completed without an artifact")
        if progress_callback:
            progress_callback({"iteration": self.config.max_iterations - 1, "max_iterations": self.config.max_iterations, "progress": 1.0})
        return PolicyArtifact.from_json_file(str(artifact_path))


def train_from_contract(contract: ContractLegacyV2, config: Optional[TrainingConfig] = None, output_dir: Optional[str] = None, progress_callback: Optional[Callable] = None) -> PolicyArtifact:
    config = config or TrainingConfig()
    if output_dir is None:
        from datetime import datetime
        output_dir = f"outputs/training_{contract.contract_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return MJLabTrainingAdapter(contract, config, output_dir).train(progress_callback=progress_callback)
