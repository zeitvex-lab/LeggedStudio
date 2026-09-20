"""``adapters/nav_ros2`` —— 外部导航栈的**接口占位**（H6）。

**这里没有任何 ROS2/Nav2 代码，而且短期内也不该有**。本包存在的理由是把"外挂导航栈"这件事
登记成**可核对的数据**（有哪些外部模块、借了哪些参数、哪些明确不搬、外部栈该报什么遥测），
而不是散在文档里的一句话。

三条纪律（改动前先读）：

1. **不进核心**：本仓的规划/控制走纯 Python（`backend/navigation_plan.py`、
   `backend/follow_controller.py`、`backend/dwa_planner.py`、`backend/mpc_tracker.py`），
   导航不依赖 ROS2 运行时。本包**只声明接口形态**，`import` 它不得引入任何外部依赖。
2. **只借参数，且只作对照**：Nav2 侧的数字（容差 / 控制频率 / 速度 / critic 权重）是**参考值**，
   **不是本仓真值**——本仓真值另有出处（到达容差 `registry/arrival_criteria.json`、
   控制频率 `contract_v3.json` 的 `control`、跟随参数 `registry/motion_commands.json`）。
   每个参考值都在 :data:`~adapters.nav_ros2.interface.BORROWED_PARAMS` 里记着**来自哪个源**，
   有出处、可复跑核对（见 `backend/test_nav_ros2_interface.py` 与真实 YAML 的逐值比对）。
3. **明确不搬的也要写下来**：:data:`~adapters.nav_ros2.interface.NOT_MIGRATED` 写清"不搬什么、
   为什么"——否则下一个人会"顺手"把它们搬进来，而重依赖/硬件绑定正是本仓反复拒绝的那类引入。
"""

from adapters.nav_ros2.interface import (
    BORROWED_PARAMS,
    EXTERNAL_STACK,
    NOT_MIGRATED,
    PARAM_SOURCES,
    TELEMETRY_FIELDS,
    availability,
    describe,
)

__all__ = [
    "BORROWED_PARAMS",
    "EXTERNAL_STACK",
    "NOT_MIGRATED",
    "PARAM_SOURCES",
    "TELEMETRY_FIELDS",
    "availability",
    "describe",
]
