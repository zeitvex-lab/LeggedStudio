"""Environment config utilities for GenesisLab + RSL-RL."""

from __future__ import annotations

import argparse

from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnvCfg


def load_env_cfg(entry_point: str) -> ManagerBasedRlEnvCfg:
    """Load a :class:`ManagerBasedRlEnvCfg` from a module entry point.

    Args:
        entry_point: String of the form ``"module.path:ClassName"``.
    """
    module_name, class_name = entry_point.split(":")
    module = __import__(module_name, fromlist=[class_name])
    cfg_cls = getattr(module, class_name)
    return cfg_cls()


def apply_cli_overrides(cfg: ManagerBasedRlEnvCfg, args: argparse.Namespace) -> None:
    """Apply common command-line overrides to an env config.

    Currently supported overrides:

    - ``seed``: if the config exposes a top-level ``seed`` field
    - ``num_envs``: if ``cfg.scene.num_envs`` exists
    - ``window``: if present and True, set ``cfg.scene.viewer = True`` (for play)
    """
    if hasattr(cfg, "seed") and args.seed is not None:
        cfg.seed = args.seed

    if getattr(args, "num_envs", None) is not None and hasattr(cfg, "scene") and hasattr(cfg.scene, "num_envs"):
        setattr(cfg.scene, "num_envs", args.num_envs)

    # Viewer flag is mainly used by play/inference scripts; safe no-op if absent.
    if getattr(args, "window", False) and hasattr(cfg, "scene") and hasattr(cfg.scene, "viewer"):
        setattr(cfg.scene, "viewer", True)


__all__ = ["load_env_cfg", "apply_cli_overrides"]

