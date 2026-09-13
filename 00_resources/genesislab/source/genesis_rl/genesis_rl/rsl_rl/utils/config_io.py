"""Config and checkpoint IO helpers for GenesisLab + RSL-RL."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import os

import yaml

from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnvCfg


def load_train_cfg(path: str) -> dict[str, Any]:
    """Load an RSL-RL runner configuration from a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_env_and_train_cfg(
    env_cfg: ManagerBasedRlEnvCfg,
    train_cfg: dict[str, Any],
    params_dir: str,
) -> None:
    """Persist env and training configs next to a run directory.

    This writes:

    - ``env.yaml``  (if the env cfg exposes ``to_dict()``)
    - ``train.yaml`` (always)
    """
    os.makedirs(params_dir, exist_ok=True)

    env_cfg_dict = env_cfg.to_dict() if hasattr(env_cfg, "to_dict") else None  # type: ignore[assignment]
    if env_cfg_dict is not None:
        with open(os.path.join(params_dir, "env.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(env_cfg_dict, f, sort_keys=False)

    with open(os.path.join(params_dir, "train.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(train_cfg, f, sort_keys=False)


def infer_paths_from_checkpoint(args: argparse.Namespace) -> None:
    """Infer env-id, train-cfg and log-dir from a checkpoint path when possible.

    This allows a minimal CLI where the user only provides ``--checkpoint`` and
    everything else is resolved relative to the run directory, i.e.:

    - ``train.yaml`` is expected at ``{run_dir}/params/train.yaml``
    - ``env_id`` is read from ``train.yaml['env_id']`` if not provided
    - ``log_dir`` defaults to the checkpoint run directory if not overridden
    """
    ckpt_path = Path(args.checkpoint).expanduser().resolve()
    run_dir = ckpt_path.parent
    params_dir = run_dir / "params"

    # Infer train-cfg path if not provided.
    if not getattr(args, "train_cfg", None):
        candidate = params_dir / "train.yaml"
        if not candidate.is_file():
            raise FileNotFoundError(
                f"Could not infer train config for checkpoint '{ckpt_path}'.\n"
                f"Expected to find: {candidate}"
            )
        args.train_cfg = str(candidate)

    # Infer log-dir if user did not explicitly override it (assume default).
    # Default from args_cli is ``runs/rsl_rl``; in that case we prefer the run dir.
    if getattr(args, "log_dir", None) in (None, "runs/rsl_rl"):
        args.log_dir = str(run_dir)

    # Infer env-id from train.yaml if missing.
    if getattr(args, "env_id", None) is None and args.train_cfg is not None:
        train_cfg = load_train_cfg(args.train_cfg)
        env_id = train_cfg.get("env_id", None)
        if env_id is None:
            raise ValueError(
                "No '--env-id' provided and the inferred train config does not "
                "contain an 'env_id' field.\n"
                f"Train config path: {args.train_cfg}\n"
                "Please either re-train with a newer train script (which stores 'env_id' "
                "into train.yaml) or pass '--env-id' explicitly."
            )
        args.env_id = env_id


__all__ = ["load_train_cfg", "save_env_and_train_cfg", "infer_paths_from_checkpoint"]

