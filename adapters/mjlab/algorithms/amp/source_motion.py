"""AMP 专家转移加载器（算法插件层；由 quadruped_kit/skills/imitation/motion.py 逐字上移）。

上移理由（2026-10-04）：AMP 源口径实现归算法插件层（跨族可用），族 Kit 改薄 re-export；
去机型化设计（motion_root/joint_count 由调用方传入）本就与机型无关，逐字保留。
来源：`go2_skills/amp_dreamwaq/motion.py`（`Go2AmpMotionLoader`，逐字上移）。
去机型化改动只有两处：

1. 数据目录从 `Path(__file__).parents[3]/assets/motions/go2_amp` 改为
   调用方传入的 `motion_root`（机型/族侧决定专家数据放哪）；
2. 帧布局的切分由 `joint_count`/`legs` **派生**而不是写死 12/4 ——
   源帧格式（README 有契约）为：

       root pos(3) + root quat(4) + 关节位置(n) + 足端位置(3×腿数)
       + 体线速度(3) + 体角速度(3) + 关节速度(n)

   判别器只吃 `q, 体线/角速度, dq, 地形相对根高`（四元数与足端字段显式省略），
   共 `2n + 7` 维（四足 12 关节 = 31 维）。
"""

from __future__ import annotations

import json
from pathlib import Path

import torch


def frame_layout(joint_count: int, legs: int) -> dict[str, object]:
    """源帧的字段切分（由关节数/腿数派生）。"""
    joint_pos = slice(7, 7 + joint_count)
    body_vel = slice(7 + joint_count + 3 * legs, 7 + joint_count + 3 * legs + 6)
    joint_vel = slice(
        7 + joint_count + 3 * legs + 6, 7 + 2 * joint_count + 3 * legs + 6
    )
    return {
        "joint_pos": joint_pos,
        "body_vel": body_vel,
        "joint_vel": joint_vel,
        "root_height": slice(2, 3),
        "frame_dim": 13 + 3 * legs + 2 * joint_count,
        "state_dim": 2 * joint_count + 7,
    }


class AmpMotionLoader:
    """加权、预载的 AMP 状态转移采样器（在策略 dt 上采样连续时间）。

    采样数学与源 AMPLoader 逐字一致：每段动作按 `MotionWeight` 加权抽取，
    在 `[0, 轨迹时长]` 上取连续时间 t 与 t+dt 两个时刻做线性插值
    （专家帧率与策略 dt 不同，拿相邻帧当转移不是源语义）。
    """

    def __init__(
        self,
        device: torch.device,
        dt: float,
        motion_root: str | Path | None,
        joint_count: int,
        legs: int = 4,
        preload: int = 2_000_000,
    ) -> None:
        if motion_root is None:
            raise ValueError("AMP 动作为族级资源：调用方必须给出 motion_root（专家数据目录）")
        self.device, self.dt = device, float(dt)
        layout = frame_layout(int(joint_count), int(legs))
        self.state_dim = int(layout["state_dim"])
        root = Path(motion_root)
        frames, frame_durations, weights = [], [], []
        for path in sorted(root.glob("*.txt")):
            payload = json.loads(path.read_text())
            data = torch.tensor(payload["Frames"], dtype=torch.float32, device=device)
            if data.shape[1] != int(layout["frame_dim"]):
                raise ValueError(
                    f"{path.name}: 帧宽 {data.shape[1]} ≠ 派生宽度 {layout['frame_dim']}"
                    f"（关节 {joint_count} × 腿 {legs} 的源格式）"
                )
            frames.append(data)
            frame_durations.append(float(payload["FrameDuration"]))
            weights.append(float(payload["MotionWeight"]))
        if not frames:
            raise FileNotFoundError(f"AMP 动作目录没有 .txt 数据：{root}")
        self.frames = frames
        self.frame_durations = frame_durations
        self.weights = torch.tensor(weights, device=device)
        self.weights /= self.weights.sum()
        self.layout = layout
        # 源用两百万条转移。训练保留该默认；测试可显式给小值。
        # 源用 NumPy 的 CPU 加权采样器；CUDA multinomial 在部分消费级 GPU 上拒绝
        # 这个两百万规模的 launch，故保留源的采样域、只把抽到的索引搬上卡。
        motion_ids = torch.multinomial(self.weights.cpu(), preload, replacement=True).to(device)
        self.states = torch.empty((preload, self.state_dim), device=device)
        self.next_states = torch.empty_like(self.states)
        # 采样**限定在单段动作内**：拼接动作会在文件边界造出假专家转移。
        for index, frame in enumerate(self.frames):
            mask = motion_ids == index
            count = int(mask.sum())
            if count:
                duration = self.frame_durations[index]
                trajectory_length = (frame.shape[0] - 1) * duration
                # 与 AMPLoader 完全一致：连续时间采样后在 t 与 t+dt 取值。
                times = torch.clamp(
                    torch.rand(count, device=device) * trajectory_length - (self.dt + duration),
                    min=0.0,
                )
                self.states[mask] = self._state_at_time(frame, times, trajectory_length)
                self.next_states[mask] = self._state_at_time(
                    frame, times + self.dt, trajectory_length
                )

    def sample(self, count: int) -> tuple[torch.Tensor, torch.Tensor]:
        ids = torch.randint(0, self.states.shape[0], (count,), device=self.device)
        return self.states[ids], self.next_states[ids]

    def _state_at_time(
        self, frames: torch.Tensor, times: torch.Tensor, trajectory_length: float
    ) -> torch.Tensor:
        phase = times / trajectory_length * frames.shape[0]
        low = torch.floor(phase).long().clamp_max(frames.shape[0] - 1)
        high = torch.ceil(phase).long().clamp_max(frames.shape[0] - 1)
        blend = (phase - low).unsqueeze(1)
        data = frames[low] * (1.0 - blend) + frames[high] * blend
        # 源判别器状态：q、体线/角速度、dq、地形相对根高（四元数与足端字段省略）。
        layout = self.layout
        return torch.cat(
            (
                data[:, layout["joint_pos"]],
                data[:, layout["body_vel"]],
                data[:, layout["joint_vel"]],
                data[:, layout["root_height"]],
            ),
            dim=1,
        )
