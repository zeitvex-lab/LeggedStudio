"""BACKEND.TRAINING.models

拆分自 backend/training_api.py（原 god file，~960 行）的独立子模块。
保持原有路由路径与响应结构不变，仅供 backend/training_api 聚合。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import Any, List, Optional, Literal
from datetime import datetime
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

from backend.training_config_helpers import (  # noqa: F401
    _terrain_mixes, _observation_summary, _terminations_summary,
    _domain_randomization, _schema_workspace, _schema_cache_path,
    _schema_interpreter, _read_profile_mtime, _dump_schema_via_worker,
)
from backend.training_manager import get_training_manager
from backend.robot_presets import get_robot_preset
from backend.robot_packages import package_for_contract
from contracts.robot_contract_v2 import RobotContractV2
from adapters.mjlab.env_factory import get_reward_terms
from adapters.mjlab.algorithms.registry import list_algorithms
from adapters.mjlab.recipe_registry import list_tasks, resolve_recipe
from adapters.backend_adapter import list_backend_descriptors


router = APIRouter(prefix="/api/training", tags=["training"])



class CreateTrainingRequest(BaseModel):
    """创建训练请求"""
    contract: dict  # Robot Contract JSON
    algorithm: str = "PPO"
    num_envs: int = 4096
    max_iterations: int = 1000
    learning_rate: float = 3e-4
    save_interval: int = 100
    # B23：None = 请求未提供 → 沿用任务真值（Recipe/训练源码里 env_cfg 自带的
    # episode_length_s，如 microduck standup 6s）；只有显式提供才覆盖（V2 单一真值 +
    # V4 杜绝静默变差）。显式提供时必须 > 0；None 跳过 gt 校验（pydantic 语义）。
    episode_length_s: float | None = Field(default=None, gt=0.0)
    task_name: str = "forward_walk"
    profile_id: str | None = None
    terrain_type: str = "plane"
    device: str = Field(default="auto", pattern=r"^(auto|cpu|cuda(?::\d+)?)$")
    smoke: bool = False  # 冒烟档：64 envs × 5 iters（microduck-studio smoke_argv 模式，报告 4 §4）
    reward_scales: dict[str, float] = Field(default_factory=dict)
    reward_overrides: bool = False
    reward_params: dict[str, dict] = Field(default_factory=dict)
    terrain: dict = Field(default_factory=dict)
    command_ranges: dict[str, list[float]] = Field(default_factory=dict)
    noise: dict = Field(default_factory=dict)
    curriculum: dict = Field(default_factory=dict)
    # Shared advanced fields. PPO ignores off-policy-only values; keeping one
    # request shape makes Web, CLI, and future adapters interchangeable.
    num_steps: int = Field(default=24, ge=4, le=4096)
    num_minibatches: int = Field(default=4, ge=1, le=64)
    gamma: float = Field(default=0.99, gt=0.0, lt=1.0)
    gae_lambda: float = Field(default=0.95, gt=0.0, le=1.0)
    clip_param: float = Field(default=0.2, gt=0.0, lt=1.0)
    entropy_coef: float = Field(default=0.01, ge=0.0)
    tau: float = Field(default=0.005, gt=0.0, le=1.0)
    batch_size: int = Field(default=256, ge=1, le=8192)
    replay_size: int = Field(default=100_000, ge=1024, le=10_000_000)
    alpha: float = Field(default=0.2, gt=0.0)
    policy_delay: int = Field(default=2, ge=1, le=16)
    exploration_noise: float = Field(default=0.1, ge=0.0, le=2.0)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)
    # Resume-from-checkpoint (Feature 13): an absolute path to a native model_*.pt
    # (or model_final.pt). When present, the worker loads it and continues the
    # learning loop from that checkpoint's iteration instead of starting fresh.
    resume_from: str | None = Field(default=None, description="Absolute path to a native .pt checkpoint to resume from")
    # Generic dot-path overrides over the profile's full config tree (e.g.
    # "environment.sim.mujoco.timestep": 0.002). Applied by the worker after
    # the recipe so user edits always win; unknown paths are skipped there.
    overrides: dict[str, Any] = Field(default_factory=dict)
    backend: str = "native_mjlab"  # runtime-validated; other frameworks reserved (unilab)

class TrainingStatusResponse(BaseModel):
    """训练状态响应"""
    task_id: str
    contract_id: str
    robot: str
    algorithm: str
    status: str
    progress: float
    created_at: str
    current_iteration: int
    max_iterations: int
    reward: float

class CompareTrainingRequest(CreateTrainingRequest):
    algorithms: list[str] = Field(default_factory=lambda: ["PPO"], min_length=1, max_length=6)
