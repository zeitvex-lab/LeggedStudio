"""Go2 侧薄委托：AMP 专家转移加载器（族级实现在 `quadruped_kit/skills/imitation/motion.py`）。

本模块只保留 go2 的两个机型量：

* **数据目录**：`assets/motions/go2_amp`（包内 LLoco 数据，出处与许可见该目录 README）；
* **帧布局**：关节数与腿数从 go2 契约绑定派生（12 关节 × 4 腿 ⇒ 49 维帧 / 31 维状态）。

采样数学在族级唯一实现（含"限定在单段动作内采样"与"连续时间插值"两条源语义）。
"""

from __future__ import annotations

from pathlib import Path

import torch

from adapters.mjlab.kits.quadruped_kit.skills.imitation.motion import (
    AmpMotionLoader as _KitAmpMotionLoader,
)

from ..binding import GO2

#: 包内专家数据目录（源格式契约见 `assets/motions/go2_amp/README.md`）。
GO2_AMP_MOTION_ROOT: Path = Path(__file__).resolve().parents[3] / "assets" / "motions" / "go2_amp"


class Go2AmpMotionLoader(_KitAmpMotionLoader):
    """go2 口径的专家加载器（旧调用面：`(device, dt, preload=...)`）。"""

    def __init__(
        self, device: torch.device, dt: float, preload: int = 2_000_000
    ) -> None:
        super().__init__(
            device,
            dt=dt,
            motion_root=GO2_AMP_MOTION_ROOT,
            joint_count=len(GO2.joint_order),
            preload=preload,
        )
