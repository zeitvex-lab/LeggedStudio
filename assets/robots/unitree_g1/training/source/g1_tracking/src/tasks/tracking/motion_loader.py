"""Reference-motion loader for the G1 motion-tracking (DeepMimic-style) task.

Loads ``.pkl`` reference motions produced by the LeggedGym-Ex retarget pipeline
(BSD-3-Clause) and serves frame data to rewards / observations / resets.

pkl dictionary layout (per clip)::

    fps                          float
    root_pos                     (F, 3)   root link position, world frame
    root_lin_vel                 (F, 3)   root linear velocity, world frame
    root_rot                     (F, 4)   root orientation quaternion, **xyzw**
    root_ang_vel                 (F, 3)   root angular velocity, world frame
    dof_pos                      (F, 29)  joint angles, robot (DDS) joint order
    dof_vel                      (F, 29)  joint velocities, robot joint order
    key_body_pos_relative_to_base (F, 19, 3) key-body offsets from root,
                                            world orientation

mjlab / MuJoCo use **wxyz** quaternions, so ``root_rot`` is converted to wxyz
at load time (the xyzw->wxyz swap is the whole conversion; no re-rotation).
``dof_pos``/``dof_vel`` are reordered into the robot entity's joint order via
name matching (a no-op when both sides use the Unitree DDS order).

Frame scheduling follows the upstream DeepMimic task: each env walks its own
frame index starting from a random frame (reference state initialization) and
wraps around at clip end. The index is derived from ``episode_length_buf`` so
rewards / observations stay perfectly consistent without extra per-step events.
"""

from __future__ import annotations

import glob
import os
import pickle
from typing import TYPE_CHECKING

import numpy as np
import torch

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

# Joint order used by the reference pkl files (legged_gym G1 29-dof
# common config == Unitree DDS order).
PKL_JOINT_ORDER: tuple[str, ...] = (
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
    "waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint",
    "left_shoulder_pitch_joint", "left_shoulder_roll_joint", "left_shoulder_yaw_joint",
    "left_elbow_joint", "left_wrist_roll_joint", "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint", "right_shoulder_roll_joint", "right_shoulder_yaw_joint",
    "right_elbow_joint", "right_wrist_roll_joint", "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
)

# Key-body order used by ``key_body_pos_relative_to_base``. Derived from the
# upstream ``asset.key_bodies`` substring list expanded against the G1 URDF
# body order (["ankle_roll", "knee", "hip", "torso", "wrist_yaw",
# "shoulder_roll", "shoulder_pitch", "elbow"]) and verified numerically
# against the raw retarget output.
KEY_BODY_NAMES: tuple[str, ...] = (
    "left_ankle_roll_link", "right_ankle_roll_link",
    "left_knee_link", "right_knee_link",
    "left_hip_pitch_link", "left_hip_roll_link", "left_hip_yaw_link",
    "right_hip_pitch_link", "right_hip_roll_link", "right_hip_yaw_link",
    "torso_link",
    "left_wrist_yaw_link", "right_wrist_yaw_link",
    "left_shoulder_roll_link", "right_shoulder_roll_link",
    "left_shoulder_pitch_link", "right_shoulder_pitch_link",
    "left_elbow_link", "right_elbow_link",
)


def _xyzw_to_wxyz(quat_xyzw: np.ndarray) -> np.ndarray:
    """Convert (..., 4) xyzw quaternions to wxyz in place-free."""
    return np.concatenate([quat_xyzw[:, 3:4], quat_xyzw[:, 0:3]], axis=-1)


class TrackingMotionManager:
    """Loads tracking reference motions and owns per-env frame state.

    Singleton per process, keyed by motion directory (mirrors the AMP task's
    MotionResetManager pattern so startup / reset events and reward / obs
    terms all share one copy of the data).
    """

    _instance: dict[str, TrackingMotionManager] = {}

    def __init__(self, motion_dir: str, device: str) -> None:
        self.device = device
        self.motion_dir = motion_dir

        clips: list[dict[str, torch.Tensor]] = []
        self.clip_names: list[str] = []
        for path in sorted(glob.glob(os.path.join(motion_dir, "*.pkl"))):
            with open(path, "rb") as f:
                data = pickle.load(f)
            fps = float(data["fps"])
            frames = int(data["root_pos"].shape[0])
            clips.append({
                "root_pos": torch.as_tensor(data["root_pos"], dtype=torch.float32),
                # xyzw -> wxyz (MuJoCo/mjlab convention).
                "root_quat": torch.as_tensor(
                    _xyzw_to_wxyz(np.asarray(data["root_rot"], dtype=np.float32)),
                    dtype=torch.float32,
                ),
                "root_lin_vel_w": torch.as_tensor(
                    data.get("root_lin_vel", np.zeros((frames, 3), np.float32)),
                    dtype=torch.float32,
                ),
                "root_ang_vel_w": torch.as_tensor(
                    data.get("root_ang_vel", np.zeros((frames, 3), np.float32)),
                    dtype=torch.float32,
                ),
                "dof_pos": torch.as_tensor(data["dof_pos"], dtype=torch.float32),
                "dof_vel": torch.as_tensor(
                    data.get("dof_vel", np.zeros_like(data["dof_pos"])),
                    dtype=torch.float32,
                ),
                "key_body_pos": torch.as_tensor(
                    data["key_body_pos_relative_to_base"], dtype=torch.float32
                ).reshape(frames, -1, 3),
                "dt": 1.0 / fps,
            })
            self.clip_names.append(os.path.splitext(os.path.basename(path))[0])
        if not clips:
            raise FileNotFoundError(f"no tracking .pkl motions found under: {motion_dir}")

        self.clip_dt = clips[0]["dt"]
        # Concatenate clips into one timeline; per-env frame indices stay
        # within their clip's segment so wrapping never crosses a boundary.
        self.clip_starts = torch.tensor(
            [0] + [int(c["root_pos"].shape[0]) for c in clips[:-1]],
            dtype=torch.long,
        ).to(device)
        self.clip_lens = torch.tensor(
            [int(c["root_pos"].shape[0]) for c in clips], dtype=torch.long
        ).to(device)
        self.frames: dict[str, torch.Tensor] = {
            key: torch.cat([c[key] for c in clips], dim=0).to(device)
            for key in (
                "root_pos", "root_quat", "root_lin_vel_w", "root_ang_vel_w",
                "dof_pos", "dof_vel",
            )
        }
        self.frames["key_body_pos"] = torch.cat(
            [c["key_body_pos"] for c in clips], dim=0
        ).to(device)
        total = int(self.frames["root_pos"].shape[0])
        self.num_clips = len(clips)
        self.total_frames = total
        print(
            f"[TrackingMotionManager] {self.num_clips} clips, {total} frames "
            f"({total * self.clip_dt:.1f}s) from {motion_dir}"
        )

        # Per-env state (populated in reset()).
        self.env_clip_idx: torch.Tensor | None = None
        self.env_frame_offset: torch.Tensor | None = None
        # Resolved robot-side indices (set in resolve_robot_layout).
        self.joint_reindex: torch.Tensor | None = None  # pkl col -> robot col
        self.key_body_ids: torch.Tensor | None = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, motion_dir: str, env: ManagerBasedRlEnv) -> TrackingMotionManager:
        key = os.path.abspath(motion_dir)
        if key not in cls._instance:
            cls._instance[key] = TrackingMotionManager(key, str(env.device))
        return cls._instance[key]

    def resolve_robot_layout(self, env: ManagerBasedRlEnv, asset_cfg_name: str = "robot") -> None:
        """Resolve joint / body index mappings against the robot entity."""
        from mjlab.entity import Entity

        asset: Entity = env.scene[asset_cfg_name]
        robot_joints = tuple(str(n) for n in asset.joint_names)
        missing = [n for n in PKL_JOINT_ORDER if n not in robot_joints]
        if missing:
            raise ValueError(f"robot is missing tracking joints: {missing}")
        # pkl column k -> robot joint index.
        self.joint_reindex = torch.tensor(
            [robot_joints.index(n) for n in PKL_JOINT_ORDER], dtype=torch.long, device=self.device
        )
        body_names = tuple(str(n) for n in asset.body_names)
        missing_bodies = [n for n in KEY_BODY_NAMES if n not in body_names]
        if missing_bodies:
            raise ValueError(f"robot is missing tracking key bodies: {missing_bodies}")
        self.key_body_ids = torch.tensor(
            [body_names.index(n) for n in KEY_BODY_NAMES], dtype=torch.long, device=self.device
        )

    # ------------------------------------------------------------------
    # Per-env frame state
    # ------------------------------------------------------------------

    def init_envs(self, env: ManagerBasedRlEnv) -> None:
        n = env.num_envs
        self.env_clip_idx = torch.zeros(n, dtype=torch.long, device=self.device)
        self.env_frame_offset = torch.zeros(n, dtype=torch.long, device=self.device)

    def sample_frames(self, num: int) -> tuple[torch.Tensor, torch.Tensor]:
        """Random (clip_idx, frame_offset) pairs for `num` envs."""
        clip_idx = torch.randint(0, self.num_clips, (num,), device=self.device)
        lens = self.clip_lens[clip_idx]
        frame_offset = (torch.rand(num, device=self.device) * lens.float()).long() % lens
        return clip_idx, frame_offset

    def current_frame_index(self, env: ManagerBasedRlEnv) -> torch.Tensor:
        """Global frame index per env for the current policy step.

        Uses ``episode_length_buf`` (incremented before reward / obs compute)
        so every consumer sees the same, deterministic reference clock.
        """
        if self.env_clip_idx is None or self.env_clip_idx.shape[0] != env.num_envs:
            # Observation managers probe term shapes at construction time,
            # before the startup event runs — fall back to frame 0.
            self.init_envs(env)
        local = (self.env_frame_offset + env.episode_length_buf) % self.clip_lens[self.env_clip_idx]
        return self.clip_starts[self.env_clip_idx] + local

    def _joint_reindex_or_slice(self):
        """Identity fallback before resolve_robot_layout (manager probes run early)."""
        return self.joint_reindex if self.joint_reindex is not None else slice(None)

    def get_key_body_ids(self):
        """Identity fallback for key-body ids before robot layout resolution."""
        return self.key_body_ids if self.key_body_ids is not None else slice(None)

    # ------------------------------------------------------------------
    # Reference accessors (batched over envs)
    # ------------------------------------------------------------------

    def get_ref_dof_pos(self, env: ManagerBasedRlEnv) -> torch.Tensor:
        idx = self.current_frame_index(env)
        return self.frames["dof_pos"][idx][:, self._joint_reindex_or_slice()]

    def get_ref_dof_vel(self, env: ManagerBasedRlEnv) -> torch.Tensor:
        idx = self.current_frame_index(env)
        return self.frames["dof_vel"][idx][:, self._joint_reindex_or_slice()]

    def get_ref_base_pos(self, env: ManagerBasedRlEnv) -> torch.Tensor:
        return self.frames["root_pos"][self.current_frame_index(env)]

    def get_ref_base_quat(self, env: ManagerBasedRlEnv) -> torch.Tensor:
        return self.frames["root_quat"][self.current_frame_index(env)]

    def get_ref_base_lin_vel_w(self, env: ManagerBasedRlEnv) -> torch.Tensor:
        return self.frames["root_lin_vel_w"][self.current_frame_index(env)]

    def get_ref_base_ang_vel_w(self, env: ManagerBasedRlEnv) -> torch.Tensor:
        return self.frames["root_ang_vel_w"][self.current_frame_index(env)]

    def get_ref_key_body_pos(self, env: ManagerBasedRlEnv) -> torch.Tensor:
        return self.frames["key_body_pos"][self.current_frame_index(env)]

    # ------------------------------------------------------------------
    # Reference state initialization (RSI)
    # ------------------------------------------------------------------

    def reset_envs(
        self,
        env: ManagerBasedRlEnv,
        env_ids: torch.Tensor,
        rsi_prob: float,
        asset_cfg,
    ) -> None:
        """Reference state initialization for the given envs.

        With probability ``rsi_prob`` the env is teleported onto the sampled
        reference frame (root pose + velocity + joint state); otherwise the
        env keeps the default init state and only the reference clock is
        sampled (mirrors upstream ``reference_state_initialization_prob``).
        """
        from mjlab.entity import Entity

        if self.env_clip_idx is None or self.env_clip_idx.shape[0] != env.num_envs:
            self.init_envs(env)
        if env_ids.numel() == 0:
            return

        clip_idx, frame_offset = self.sample_frames(int(env_ids.numel()))
        self.env_clip_idx[env_ids] = clip_idx
        self.env_frame_offset[env_ids] = frame_offset

        rsi_mask = torch.rand(env_ids.numel(), device=self.device) < rsi_prob
        rsi_ids = env_ids[rsi_mask]
        if rsi_ids.numel() == 0:
            return

        local = frame_offset[rsi_mask]
        global_idx = self.clip_starts[clip_idx[rsi_mask]] + local

        asset: Entity = env.scene[asset_cfg.name]

        root_pos = self.frames["root_pos"][global_idx].clone()
        positions = env.scene.env_origins[rsi_ids].clone()
        # Keep xy on the env origin; use the reference height (clamped away
        # from the ground to avoid initial penetration).
        positions[:, 2] = positions[:, 2] + torch.clamp(root_pos[:, 2], min=0.55)
        root_pose = torch.cat([positions, self.frames["root_quat"][global_idx]], dim=-1)
        asset.write_root_link_pose_to_sim(root_pose, env_ids=rsi_ids)

        root_vel = torch.cat(
            [
                self.frames["root_lin_vel_w"][global_idx],
                self.frames["root_ang_vel_w"][global_idx],
            ],
            dim=-1,
        )
        asset.write_root_link_velocity_to_sim(root_vel, env_ids=rsi_ids)

        joint_pos = self.frames["dof_pos"][global_idx][:, self.joint_reindex]
        joint_vel = self.frames["dof_vel"][global_idx][:, self.joint_reindex]
        soft_limits = asset.data.soft_joint_pos_limits
        joint_ids = asset_cfg.joint_ids
        if isinstance(joint_ids, (list, tuple)):
            joint_ids_t = torch.tensor(joint_ids, dtype=torch.long, device=self.device)
        else:
            joint_ids_t = joint_ids
        limits = soft_limits[rsi_ids][:, joint_ids_t]
        joint_pos = joint_pos.clamp(limits[..., 0], limits[..., 1])
        asset.write_joint_state_to_sim(
            joint_pos, joint_vel[:, joint_ids_t], env_ids=rsi_ids, joint_ids=joint_ids_t
        )
