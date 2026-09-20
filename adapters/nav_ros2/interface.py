"""外部导航栈接口的**声明数据**（H6）。纯数据 + 纯函数，**不 import 任何 ROS2 依赖**。

本模块回答四个问题（都是"谁能核对"的事实，不是口号）：

1. **有哪些外部栈、什么角色、接没接**：:data:`EXTERNAL_STACK`；
2. **借了哪些 Nav2 参数、每个值来自哪个源、三源一不一致**：:data:`BORROWED_PARAMS`
   —— 每个值都带 `sources`（源 → 值），由 `backend/test_nav_ros2_interface.py` 逐值回真源 YAML 核对；
3. **明确不搬什么、为什么**：:data:`NOT_MIGRATED`；
4. **外部栈该报什么遥测**（对齐 `06` §4.3 的 D2–D6 分级验收）：:data:`TELEMETRY_FIELDS`。

**"借参数"的含义在本仓是"对照"，不是"真值"**（`04_参数真值标准.md` 定了真值链）。所以
:data:`BORROWED_PARAMS` 的每一项都必须写 `our_truth`（本仓真值在哪、值是多少，或"无对应物"）
—— 否则这些数字会在几个月后被人当成我们的取值照搬。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

#: 三个参考源的仓库相对路径（**只借参数**的三个候选，逐个核对过）。
#: 注意三者不是同一套栈：`slam_nav2` / `rc_competition` 用 DWB，`go2_nav` 用 MPPI。
PARAM_SOURCES: dict[str, str] = {
    "slam_nav2": "00_resources/unitree-go2-slam-nav2/go2_slam_nav/config/nav2_params.yaml",
    "go2_nav": "00_resources/unitree_go2_nav/unitree_go2_nav/config/nav2_params.yaml",
    "rc_competition": "00_resources/rc_old/RC_WheelLeg/05_software/real/sim2real_ros2_v3/src/sim2real_nav2/config/nav2_params.yaml",
}

#: 外部导航栈组件登记（**全部未接入**；"接口占位"就是这一栏的现状）。
EXTERNAL_STACK: tuple[dict[str, str], ...] = (
    {
        "id": "nav2",
        "label": "Nav2（全局规划 / 局部控制 / 行为树）",
        "role": "外部 planner + controller",
        "status": "未接入（占位）",
        "reference": "00_resources/unitree-go2-slam-nav2",
        "note": "只借参数（见 BORROWED_PARAMS）；**不引运行时**——本仓规划/控制是纯 Python。",
    },
    {
        "id": "rtabmap",
        "label": "RTAB-Map（视觉/激光 SLAM）",
        "role": "外部定位与建图",
        "status": "未接入（占位）",
        "reference": "00_resources/unitree-go2-slam-nav2",
        "note": "本仓地图是 2D 栅格（backend/scenario_maps.py），不做 SLAM。",
    },
    {
        "id": "octomap",
        "label": "OctoMap（占据栅格）",
        "role": "外部三维占据地图",
        "status": "未接入（占位）",
        "reference": "00_resources/Odin-Nav-Stack",
        "note": "本仓用 2D 代价地图 + A*/Dijkstra；三维占据未做。",
    },
    {
        "id": "vlm",
        "label": "VLM / 语义目标（LightNav 类）",
        "role": "外部语义决策（B 类感知在策略外）",
        "status": "未接入（占位）",
        "reference": "00_resources/LightNav-0",
        "note": "与 B 类感知分层同轴：外部决策输出目标，RL 只管运动。",
    },
)

#: 借来的 Nav2 参考参数。每项：`sources`（逐源值）+ `agreement` + `our_truth`（本仓真值口径）。
#: `yaml_key` 是回真源核对时用的键名（测试按 `键: 值` 行匹配，不引入 YAML 依赖）。
BORROWED_PARAMS: tuple[dict[str, Any], ...] = (
    {
        "name": "planner.tolerance",
        "yaml_key": "tolerance",
        "unit": "m",
        "sources": {"slam_nav2": 0.5, "go2_nav": 0.5, "rc_competition": 0.5},
        "agreement": "consistent",
        "our_truth": "registry/arrival_criteria.json#waypoint.tolerance_m = 0.2 m（0.35 / 0.30 是 legacy 别名，用时会标 deviation）",
        "note": "三源一致 0.5，但**与本仓 0.2 不同**——参考值，不当真值用。",
    },
    {
        "name": "planner.use_astar",
        "yaml_key": "use_astar",
        "unit": "bool",
        "sources": {"slam_nav2": False, "go2_nav": False, "rc_competition": True},
        "agreement": "disagree",
        "our_truth": "无对应物（本仓规划器选择在 backend/navigation_plan.py 的 algorithm 参数：astar / dijkstra）",
        "note": "**两源 false、一源 true**：三源本就不是一套配置，别把任何一个当成「标准」。",
    },
    {
        "name": "controller.frequency",
        "yaml_key": "controller_frequency",
        "unit": "Hz",
        "sources": {"slam_nav2": 20.0, "go2_nav": 20.0, "rc_competition": 10.0},
        "agreement": "disagree",
        "our_truth": "契约 contract_v3.json#control.control_hz（每包自持；浏览器控制拍 = sim_dt × decimation）",
        "note": "仿真/真机两种栈取值不同（20 vs 10）——本仓不从 Nav2 取控制频率。",
    },
    {
        "name": "controller.max_vel_x",
        "yaml_key": "max_vel_x",
        "unit": "m/s",
        "sources": {"slam_nav2": 0.15, "rc_competition": 0.6},
        "agreement": "disagree",
        "our_truth": "registry/motion_commands.json（nav/teleop 两档上限，含裁剪明细）",
        "note": "**注意**：`go2_nav` 用的是 MPPI 控制器，没有 DWB 的 `max_vel_x`，故该源无值。",
    },
    {
        "name": "controller.max_vel_theta",
        "yaml_key": "max_vel_theta",
        "unit": "rad/s",
        "sources": {"slam_nav2": 1.0, "rc_competition": 2.0},
        "agreement": "disagree",
        "our_truth": "registry/motion_commands.json（wz 上限）；registry/follow_controller 侧另有 max_wz",
        "note": "同 max_vel_x：`go2_nav`（MPPI）无此项。",
    },
    {
        "name": "critics.PathAlign.scale",
        "yaml_key": "PathAlign.scale",
        "unit": "1",
        "sources": {"slam_nav2": 32.0, "rc_competition": 32.0},
        "agreement": "consistent",
        "our_truth": "无对应物（本仓不实现 DWB——§2.2 判其为负面对照）",
        "note": "两源一致 32；记录它只为将来若引入 DWB 类局部规划时有对照。",
    },
    {
        "name": "critics.GoalAlign.scale",
        "yaml_key": "GoalAlign.scale",
        "unit": "1",
        "sources": {"slam_nav2": 24.0, "rc_competition": 24.0},
        "agreement": "consistent",
        "our_truth": "无对应物（同 PathAlign.scale）",
        "note": "两源一致 24。",
    },
)

#: **明确不搬**（改这段之前先读理由——它们是"重依赖/硬件绑定/与浏览器栈不兼容"三类）。
NOT_MIGRATED: tuple[dict[str, str], ...] = (
    {"id": "nav2_full", "what": "Nav2 全家桶（AMCL / 行为树 / costmap 插件）", "why": "重运行时；本仓规划/控制已纯 Python 落地（H11–H13）。"},
    {"id": "odin_driver", "what": "Odin 厂商驱动（静态库 + 固件绑定）", "why": "硬件绑定，且是闭源静态库，无法在本仓验证。"},
    {"id": "habitat_vlm", "what": "Habitat / VLM 评测栈（`LightNav-0/{habitat_server,evt_bench,serving}`）", "why": "另一套评测栈，与浏览器 MuJoCo 栈不兼容。"},
    {"id": "gpu_raycast", "what": "GPU 光线投射（`MGDP/warp_sensor`）", "why": "只借 D435 相机模型参数；GPU 依赖与浏览器侧渲染路径冲突。"},
)

#: 外部栈应报的遥测，对齐 `06` §4.3 的 D2–D6 分级验收。
#: `owner` = `external`（外部栈该给）/ `repo`（本仓已有等价物）；`level` = 该字段服务于哪一级。
#: **形状是占位草案**：真接入时以真机日志为准（这里声明的是"要报什么"，不是"字段长什么样"）。
TELEMETRY_FIELDS: tuple[dict[str, str], ...] = (
    {"id": "state_estimate", "label": "状态估计（位姿 + 速度）", "level": "D2", "owner": "external",
     "shape": "pose[7] + twist[6]", "note": "D2 影子模式的判据是「状态估计与预处理链路正确」。"},
    {"id": "preprocess_trace", "label": "预处理链路轨迹（订阅 → 滤波 → 下发）", "level": "D2", "owner": "external",
     "shape": "事件序列（时间戳 + 阶段 + 值）", "note": "用于定位「值对了但时机错」。"},
    {"id": "joint_command", "label": "关节指令（位置/速度）", "level": "D3", "owner": "external",
     "shape": "float32[n_dof] × 2", "note": "D3 判据是「关节方向与幅度正确」。"},
    {"id": "joint_state", "label": "关节反馈", "level": "D3", "owner": "external",
     "shape": "float32[n_dof]", "note": "与 joint_command 对比才判得出方向/幅度。"},
    {"id": "cmd_vel_in", "label": "上层速度指令（进入仲裁前）", "level": "D4", "owner": "external",
     "shape": "float32[3]", "note": "D4 平地低速：看急停/watchdog 是否真的截断。"},
    {"id": "cmd_vel_out", "label": "仲裁/限幅后实际下发", "level": "D4", "owner": "repo",
     "shape": "float32[3]", "note": "本仓已有：backend/motion_commands.py + backend/command_arbiter.py。"},
    {"id": "estop_state", "label": "急停状态", "level": "D4", "owner": "repo",
     "shape": "枚举（含触发源）", "note": "本仓已有：backend/deploy_pack.py 生成的 fsm_safety_template.py（ESTOP 分支）。"},
    {"id": "watchdog_state", "label": "看门狗状态与剩余时间", "level": "D4", "owner": "repo",
     "shape": "枚举 + 秒", "note": "本仓已有：backend/deploy_pack.py 的 fsm_safety_template.py（命令超时回退）。"},
    {"id": "route_progress", "label": "航线进度", "level": "D5/D6", "owner": "repo",
     "shape": "float(0..1) + 当前航点", "note": "本仓已有：backend/navigation_api.py 与 web/sim2sim/navigation.js 的 route_completion。"},
    {"id": "failure_attribution", "label": "失败归因（原因码 + 细节）", "level": "D5/D6", "owner": "repo",
     "shape": "枚举 + 明细", "note": "本仓已有：backend/follow_controller.py（H12 终止原因 stuck / timeout / …）。"},
)


def _repo_root() -> Path:
    """仓库根（`adapters/nav_ros2/interface.py` 往上三层）。"""
    return Path(__file__).resolve().parents[2]


def availability() -> dict[str, Any]:
    """**如实报告**外部栈的可用性（不猜、不美化）。

    判据只有一条：Python 侧能否 `import rclpy`（ROS2 的 Python 绑定）。本仓**不要求**它存在——
    存在也只说明"这台机器装了 ROS2"，**不等于**本包接上了导航栈（本包一行导航代码都没有）。
    """
    root = _repo_root()
    return {
        "ros2_importable": importlib.util.find_spec("rclpy") is not None,
        "runtime_required": False,  # 本仓核心不依赖 ROS2：这是设计，不是现状
        "connected": False,  # 接口占位：没有任何外部栈被接上
        "reference_sources_present": {
            name: (root / relative).is_file() for name, relative in PARAM_SOURCES.items()
        },
    }


def describe() -> dict[str, Any]:
    """接口摘要（**稳定形状**：字段名与顺序半年后还得一样，下游/文档都读它）。"""
    return {
        "schema": "nav-ros2-interface-1.0",
        "external_stack": [dict(item) for item in EXTERNAL_STACK],
        "borrowed_params": [dict(item) for item in BORROWED_PARAMS],
        "not_migrated": [dict(item) for item in NOT_MIGRATED],
        "telemetry_fields": [dict(item) for item in TELEMETRY_FIELDS],
        "availability": availability(),
    }
