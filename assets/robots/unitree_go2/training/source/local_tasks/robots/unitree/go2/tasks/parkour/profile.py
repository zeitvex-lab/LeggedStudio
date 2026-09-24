"""Go2 侧的越障（PIE parkour）配方身份与相机档位（机型侧，薄委托）。

族级配方声明在 `adapters.mjlab.kits.quadruped_kit.skills.parkour/profile.py`；
本模块只填**机型身份**（`task_id` / `experiment_name`）与**本机型可用的相机档位 id**
（`registry/cameras.json` 的 `pie-front-depth-106x60`，深度的位姿/分辨率/视场真值都在那里）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.parkour.profile import ParkourProfile

#: `task_id` 与包内注册名（`config/go2/__init__.py` 的 `register_mjlab_task`）一致。
GO2_PARKOUR = ParkourProfile(
    task_id="Unitree-Go2-PIE",
    experiment_name="go2_pie",
    camera_profile="pie-front-depth-106x60",
)
