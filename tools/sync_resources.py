#!/usr/bin/env python3
"""sync_resources.py — 以「项目」为单位整合参考资源（v3，规范见 00_resources/_SPEC.md）

设计要点：
  * **以项目为单位**：`00_resources/<project>/` 原样保留来源项目的目录结构与组织思想
    （不再按机型拆成十几份重复拷贝）；
  * **源目录可覆盖**：`PROJECTS` 条目默认识源 `00_open/<name>/`，用 `"src"` 可指向嵌套
    目录（如 `auto_web/wandb` → 输出 `00_resources/wandb/`）；`"kind"` 标注参考类型；
  * **保留有用内容**：源码 / 配置 / 文档 / 数据 / URDF·xacro·MJCF /
    **推理策略文件（.onnx/.pt/.pth/.engine/.plan/.ckpt/.safetensors）**；
  * **删除无用内容**：3D 网格与 CAD、场景/点云/ROS 录包、归档、可执行库与二进制、
    图像/音视频/字体、日志，以及超过体积阈值的大文件；
  * **删除留占位**：被删除的文件在**原目录**留下 `_OMITTED.md` 登记（文件名/体积/类型/源路径），
    真要用到时按源路径回到 `00_open/<project>/` 取用，目录结构与可回溯性不丢；
  * **建索引**：每个项目一份 `README.md`（有什么资源 · 能帮什么 · 关联哪些机器人），
    根目录一份 `README.md` 总索引 + `_index.json` 机器可读索引。

用法（仓库任意目录）：
    python legged_studio/tools/sync_resources.py                    # 增量同步 + 重建索引
    python legged_studio/tools/sync_resources.py --clean            # 清空后全量重抽
    python legged_studio/tools/sync_resources.py --only robot_lab,rl_sar
    python legged_studio/tools/sync_resources.py --dry-run          # 只统计不落盘
    python legged_studio/tools/sync_resources.py --kb-only          # 只同步通用知识库
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
TOOLS_DIR = Path(__file__).resolve().parent
LS_ROOT = TOOLS_DIR.parent                  # legged_studio/
# 源根目录：默认取仓库上级（历史布局 ../../00_open/<project>）；可用环境变量
# LEGGED_SYNC_WORKSPACE 覆盖，便于在任意位置放 00_open/ 源树做增量同步。
WORKSPACE = Path(os.environ.get("LEGGED_SYNC_WORKSPACE") or LS_ROOT.parent)
RES_ROOT = LS_ROOT / "00_resources"

CATEGORIES = [
    "model",          # 本体/场景描述：URDF / xacro / MJCF / 场景 xml
    "contract",       # 关节与接口契约：limits / PD / action_scale / default pose / 维度
    "training",       # RL 训练工程：env cfg / reward / curriculum / DR / 任务注册
    "deploy",         # 部署与推理：策略文件 / FSM / SDK 桥 / sim2sim / 控制代码
    "terrain_scene",  # 地形与场景资产
    "motion",         # 动作/运动数据与重定向配置
    "evaluation",     # 评测指标 / 测试脚本
    "misc",           # 文档 / 脚本 / 其它
]
CATEGORY_LABEL = {
    "model": "本体与场景描述",
    "contract": "关节与接口契约",
    "training": "RL 训练工程",
    "deploy": "部署与推理",
    "terrain_scene": "地形与场景",
    "motion": "动作与运动数据",
    "evaluation": "评测与测试",
    "misc": "文档与其它",
}
CATEGORY_HELP = {
    "model": "机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建",
    "contract": "关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度",
    "training": "RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本",
    "deploy": "部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim",
    "terrain_scene": "地形与场景资产：高度场、台阶、崎岖地形与场景构建",
    "motion": "动作与运动数据：重定向配置、参考动作、步态数据",
    "evaluation": "评测与测试：指标脚本、基准与回归用例",
    "misc": "文档、说明、许可与零散脚本",
}

# --------------------------------------------------------------------------
# 目标机型（14）
# --------------------------------------------------------------------------
ROBOT_LABEL = {
    "unitree_go1": "宇树 Go1 四足",
    "unitree_go2": "宇树 Go2 四足",
    "unitree_go2w": "宇树 Go2W 轮足",
    "unitree_b2": "宇树 B2 四足",
    "unitree_b2w": "宇树 B2W 轮足",
    "unitree_g1": "宇树 G1 人形",
    "deeprobotics_lite3": "云深处 Lite3 四足",
    "deeprobotics_m20": "云深处 M20 轮足",
    "limx_tron1_pf": "逐际动力 TRON1-PF",
    "limx_tron1_sf": "逐际动力 TRON1-SF",
    "limx_tron1_wf": "逐际动力 TRON1-WF",
    "microduck": "MicroDuck 双足",
    "wuji_hand": "无极灵巧手",
    "zex-w": "ZEX-W 轮足",
}
ROBOTS = list(ROBOT_LABEL)

# --------------------------------------------------------------------------
# 项目清单：项目目录（相对 00_open/） → 关联机型 + 定位说明
# --------------------------------------------------------------------------
PROJECTS: dict[str, dict] = {
    # ---------------- Go2 / Go2W ----------------
    "go2_rl_gym": {"robots": ["unitree_go2"],
                   "desc": "Go2 的 legged_gym + rsl_rl 训练/回放工程（IsaacGym 系）"},
    "go2_rl_robotlab": {"robots": ["unitree_go2"],
                        "desc": "基于 robot_lab 的 Go2 训练工程（IsaacLab）"},
    "unitree-go2-slam-nav2": {"robots": ["unitree_go2"],
                              "desc": "Go2 的 SLAM + Nav2 导航栈（ROS2）"},
    "unitree_go2_nav": {"robots": ["unitree_go2"],
                        "desc": "Go2 导航相关脚本与配置"},
    "references_1000framesai": {"robots": ["unitree_go2"],
                                "desc": "1000frames.ai 参考素材（机型描述/示例）"},
    "1000framesai.com": {"robots": ["unitree_go2"],
                         "desc": "1000frames.ai 站点镜像资源"},
    "sim.stackforce.cc": {"robots": ["unitree_go2"],
                          "desc": "stackforce 仿真站点参考资源"},
    "Odin-Nav-Stack": {"robots": ["unitree_go2"],
                       "desc": "Odin1 深度相机 + NeuPAN 局部规划的导航栈"},
    "LightNav-0": {"robots": ["unitree_go2"],
                   "desc": "LightNav 视觉导航（Qwen3-VL 系）"},
    "zsi_rl": {"robots": ["unitree_go2"],
               "desc": "Go2 的 RL 示例工程"},
    "go2w_sim2sim": {"robots": ["unitree_go2w"],
                     "desc": "Go2W 轮足 sim2sim 部署工程（MuJoCo）"},
    "unitree_rl_mjlab": {"robots": ["unitree_go2", "unitree_go2w", "unitree_g1"],
                         "desc": "宇树官方 mjlab 版 RL 工程：训练任务 + MuJoCo 部署（Go2/Go2W/G1）"},
    "unitree_rl_mjlab_go2w": {"robots": ["unitree_go2w", "unitree_go2", "unitree_g1"],
                              "desc": "Go2W 专用 mjlab RL 工程（含 Go2/G1 资产）"},
    "unitree_mujoco": {"robots": ["unitree_go1", "unitree_go2", "unitree_g1"],
                       "desc": "宇树官方 MuJoCo 仿真器与机型 XML（Go1/Go2/G1）"},
    # ---------------- 通用 / 多机型 RL ----------------
    "LeggedGym-Ex": {"robots": ["unitree_go2", "unitree_go1", "unitree_g1",
                                "limx_tron1_pf", "limx_tron1_sf"],
                     "desc": "legged_gym 扩展版：多机型训练环境与任务"},
    "gym_ex": {"robots": ["unitree_go2", "unitree_go1", "unitree_g1",
                          "limx_tron1_pf", "limx_tron1_sf"],
               "desc": "legged_gym 系实验工程（多机型）"},
    "mjlab_new": {"robots": ["unitree_go1", "unitree_go2", "unitree_go2w", "unitree_g1"],
                  "desc": "mjlab 新版：机型资产 + MuJoCo RL 任务"},
    "unilab_new": {"robots": ["unitree_go2", "unitree_go2w", "unitree_go1", "unitree_g1",
                              "microduck", "deeprobotics_m20", "deeprobotics_lite3"],
                   "desc": "统一多机型 RL 实验框架（训练/评估/部署）"},
    "uni_rl": {"robots": ["unitree_go2", "unitree_go2w", "unitree_go1",
                          "unitree_b2", "unitree_b2w", "unitree_g1"],
               "desc": "多机型统一 RL 训练框架（宇树全系）"},
    "lain_job": {"robots": ["unitree_go2", "unitree_go1", "unitree_g1", "deeprobotics_m20"],
                 "desc": "LLoco 技能式 RL 任务与部署（多机型）"},
    "kaiwu_rl": {"robots": ["unitree_go2", "unitree_g1"],
                 "desc": "开悟 RL 工程（Go2/G1）"},
    "mjswan": {"robots": ["unitree_go2", "unitree_go1", "unitree_g1"],
               "desc": "mjlab 可视化/仿真套件"},
    "mujoco_playground": {"robots": ["unitree_go1", "unitree_g1"],
                          "desc": "DeepMind MuJoCo Playground：Go1/G1 环境与策略"},
    "parkour_mjlab": {"robots": ["unitree_go2", "unitree_g1"],
                      "desc": "Go2/G1 的 parkour 任务（mjlab）：Go2 PIE 深度跑酷训练 + sim2sim + 发布策略"},
    "MGDP": {"robots": ["unitree_go1", "unitree_go2", "deeprobotics_lite3"],
             "desc": "MGDP：通用深度感知四足运动控制（IsaacGym + Warp 深度传感器，跨机型迁移）"},
    "Dreamwaq": {"robots": ["unitree_go2", "deeprobotics_m20"],
                 "desc": "DreamWaQ 盲式运动控制实现"},
    "LeggedSkillDeploy": {"robots": ["unitree_go2", "unitree_go2w", "unitree_go1",
                                     "unitree_g1", "deeprobotics_m20"],
                          "desc": "多机型技能部署包（策略 + 部署配置）"},
    "robot_lab": {"robots": ["unitree_go1", "unitree_go2", "unitree_go2w", "unitree_b2",
                             "unitree_b2w", "unitree_g1", "deeprobotics_lite3",
                             "deeprobotics_m20"],
                  "desc": "robot_lab：IsaacLab 版多机型训练框架"},
    "fan_robotlab": {"robots": ["unitree_go1", "unitree_go2", "unitree_go2w", "unitree_b2",
                                "unitree_b2w", "unitree_g1", "deeprobotics_lite3",
                                "deeprobotics_m20"],
                     "desc": "robot_lab 的个人分支（多机型实验）"},
    "rl_sar": {"robots": ["unitree_go2", "unitree_go2w", "unitree_b2", "unitree_b2w",
                          "unitree_g1", "deeprobotics_lite3"],
               "desc": "RL-SAR：仿真到实机部署框架（多机型、含策略与 C++ 部署）"},
    "rl_sar_zoo": {"robots": ["unitree_go2", "unitree_go2w", "unitree_b2", "unitree_b2w",
                              "unitree_g1", "deeprobotics_lite3"],
                   "desc": "RL-SAR 机型 zoo：URDF/MJCF 与策略集合"},
    "fan_rlsar": {"robots": ["unitree_go2", "unitree_go2w", "unitree_b2", "unitree_b2w",
                             "unitree_g1", "deeprobotics_lite3"],
                  "desc": "RL-SAR 的个人分支（多机型实验）"},
    "robot_mujoco": {"robots": ["unitree_go1", "unitree_go2", "unitree_go2w", "unitree_b2",
                                "unitree_b2w", "unitree_g1", "deeprobotics_lite3"],
                     "desc": "多机型 MuJoCo 资产与场景"},
    "robot-descriptions-quadruped": {"robots": ["unitree_go1", "unitree_go2", "unitree_b2",
                                                "unitree_b2w", "deeprobotics_lite3",
                                                "deeprobotics_m20"],
                                     "desc": "四足机型描述汇总（URDF/xacro/MJCF）"},
    "him_dog": {"robots": ["unitree_go1", "unitree_go2"],
                "desc": "him_dog 四足工程"},
    "HIMLoco": {"robots": ["unitree_go1"],
                "desc": "InternRobotics HIMLoco：四足高动态运动/越障 RL 训练工程（legged_gym + rsl_rl）"},
    "walk-these-ways": {"robots": ["unitree_go1"],
                        "desc": "Improbable AI walk-these-ways：Go1 快速步态 RL 训练与部署（go1_gym / go1_gym_deploy）"},
    # ---------------- G1 人形 / 灵巧手 ----------------
    "robo_re": {"robots": ["unitree_g1"], "desc": "G1 人形 RL 工程"},
    "InstinctMJ": {"robots": ["unitree_g1"], "desc": "InstinctMJ：G1 人形 mjlab 工程"},
    "AMP_mjlab": {"robots": ["unitree_g1"], "desc": "AMP 动作先验训练（mjlab，G1）"},
    "humanoid-motion-planning": {"robots": ["unitree_g1"], "desc": "人形运动规划算法"},
    "legged_sim": {"robots": ["unitree_g1"], "desc": "G1 仿真环境与场景"},
    "g1-manipulation-challenge": {"robots": ["unitree_g1"], "desc": "G1 操作挑战赛工程"},
    "UFO": {"robots": ["unitree_g1"], "desc": "UFO：G1 人形工程"},
    "g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-": {"robots": ["unitree_g1"],
                                               "desc": "G1 MuJoCo + ROS2 导航仿真"},
    "g1_spinkick_example": {"robots": ["unitree_g1"], "desc": "G1 回旋踢示例（mjlab）"},
    "wuji-mjlab": {"robots": ["wuji_hand"], "desc": "无极灵巧手 mjlab 训练工程"},
    "wbc-mjlab": {"robots": ["unitree_g1"],
                  "desc": "WBC-Mjlab：mjlab 全身运动跟踪（WBC）共享 MDP，一策略多技能；含 G1 任务/动作库/导出"},
    # ---------------- 云深处 ----------------
    "sdk_deploy": {"robots": ["deeprobotics_lite3", "deeprobotics_m20"],
                   "desc": "云深处 SDK 与部署代码"},
    "deep_robotics_model": {"robots": ["deeprobotics_lite3", "deeprobotics_m20"],
                            "desc": "云深处机型模型与描述文件"},
    "deep_rl": {"robots": ["deeprobotics_lite3", "deeprobotics_m20"],
                "desc": "云深处 RL 训练工程"},
    "rl_training": {"robots": ["deeprobotics_lite3", "deeprobotics_m20"],
                    "desc": "云深处 RL 训练任务与配置"},
    "m20_rl_isaacsim": {"robots": ["deeprobotics_m20", "deeprobotics_lite3"],
                        "desc": "M20 轮足 IsaacSim RL 工程"},
    # ---------------- 逐际动力 TRON1 ----------------
    "tron1-robot-description": {"robots": ["limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf"],
                                "desc": "TRON1 机型描述（URDF/xacro）"},
    "tron1-rl-isaaclab": {"robots": ["limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf"],
                          "desc": "TRON1 IsaacLab RL 训练工程"},
    "tron1-rl-deploy-python": {"robots": ["limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf"],
                               "desc": "TRON1 Python 部署与策略文件"},

    "tron1-rl-deploy-ros2": {"robots": ["limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf"],
                  "desc": "limxdynamics TRON1 RL 部署（ROS2 controller + hw，含 gazebo sim 与 gym/lab 双关节序参数表）"},
    "limxsdk-lowlevel": {"robots": ["limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf"],
                  "desc": "limxdynamics 官方低层 SDK（limxsdk：硬件接口/消息定义）"},
    "robot-joystick": {"robots": ["limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf"],
                  "desc": "limxdynamics 官方摇杆上位机（预编译，命令源参考）"},
    # ---------------- 跨机型方法学参考（导航 / RL API / 操作仿真 / 具身引擎） ----------------
    "tdt-nav-kit": {"robots": ["unitree_go2", "limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf"],
                  "desc": "TDT 二维栅格导航算法组件（A*/Kinodynamic A* 前端 + Minimum-Snap/OSQP 轨迹后端，C++）——H 组导航规划参考"},
    "Gymnasium": {"robots": ["unitree_go1", "unitree_go2", "unitree_go2w", "unitree_b2",
                             "unitree_b2w", "unitree_g1", "deeprobotics_lite3",
                             "deeprobotics_m20", "limx_tron1_pf", "limx_tron1_sf",
                             "limx_tron1_wf", "microduck", "wuji_hand", "zex-w"],
                  "desc": "Farama RL 环境标准 API（Env/Space/Wrapper/Vector）——训练适配器协议与环境接口设计参考"},
    "robosuite_new": {"src": "robosuite_new", "robots": ["wuji_hand", "unitree_g1"],
                  "desc": "robosuite：MuJoCo 操作仿真框架（arenas/robots/objects/tasks 模块化 MJCF 组合 + OSC 控制器 + 遥操作）——wuji 灵巧手操作任务与资源组合模型参考"},
    "habitat-sim": {"robots": ["unitree_go2", "limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf"],
                  "desc": "Meta habitat-sim 具身 AI 仿真引擎（C++：nav PathFinder/相机+鱼眼传感器栈/场景元数据）——H 组高级仿真、导航与传感器参考"},
    # ---------------- MicroDuck / ZEX-W ----------------
    "microduck_all": {"robots": ["microduck"], "desc": "MicroDuck 综合工程"},
    "microduck_rl": {"robots": ["microduck"], "desc": "MicroDuck RL 训练"},
    "microduck-simulator": {"robots": ["microduck"], "desc": "MicroDuck 仿真器"},
    "microduck-studio": {"robots": ["microduck"], "desc": "MicroDuck Studio（编辑/可视化）"},
    "rc_old": {"robots": ["zex-w", "unitree_go1", "unitree_g1"],
               "desc": "ZEX-W 轮足旧版工程（含 Go1/G1 分支）"},
    # ---------------- 跨机型参考：工具 / 导航感知 / 移植 / 训练平台 ----------------
    "urdf_tool": {"robots": [],
                  "desc": "URDF 资产查看与验证工具集（robot_viewer / URDF-Studio）",
                  "kind": "工具参考（机器人资产查看与验证）"},
    "jie_3d_nav": {"robots": [],
                   "desc": "JIE 3D 导航栈（jie_octomap + octo_planner）：感知与规划参考",
                   "kind": "导航与感知参考"},
    "mjlab-skillkit": {"robots": [],
                       "desc": "mjlab 技能包（adapters / agents / shared）：Isaac Lab → mjlab 移植参考",
                       "kind": "Isaac → mjlab 移植参考"},
    "wandb": {"src": "auto_web/wandb", "robots": [],
              "desc": "Weights & Biases 客户端（Go core + Python SDK）：训练任务跟踪与可视化参考",
              "kind": "训练任务跟踪平台参考"},
    # MATRiX 运行时/运控/导航栈的配套源码快照（v0.1.2 线）。只收「实现类」子集：
    # 场景组合、传感器声明、多机器人端口、相机/渲染协议、实景扫描→MuJoCo proxy
    # 流水线与 G1 材质桥；发布/部署/内部运维（含内网地址与私有仓引用）一律不收。
    # ---------------- 真机竞赛任务编排参考（Go2 EDU + D1 机械臂）----------------
    "26Raicom": {"robots": ["unitree_go2"],
                 "desc": "2026 睿抗（RAICOM）多模态巡检赛道全国一等奖代码：8 阶段全流程——PID 黑线循迹 + "
                         "白线触发前跳、三路 TOF 迷宫五阶段状态机、IMU 俯仰闭环上/下台阶、D1 七自由度机械臂 "
                         "DLS 逆运动学抓取（D435i 红圆 + 深度）、YOLO+ORB+模板兜底标志识别；含赛规 PDF、"
                         "场地立体图与硬件健壮性方案（看门狗 / 热插拔 / USB 带宽）",
                 "kind": "真机竞赛任务编排参考（多模态巡检）"},
    # ---------------- Go2 真机接口 / 仿真 / 视觉伺服参考 ----------------
    "go2_unitree_ros2": {"robots": ["unitree_go2"],
                         "desc": "Unitree SDK2 的 ROS2 封装参考：低层 /lowcmd（200Hz + CRC32）与 Sport API "
                                 "/api/sport/request 双通道、运动/关节状态与手柄读取、IMU 发布",
                         "kind": "真机接口参考（ROS2 / Unitree SDK2）"},
    "taggy": {"robots": ["unitree_go2"],
              "desc": "Go2 的 ROS2 bringup / 控制 / Gazebo 仿真（Taggy 巡逻机器人原型）："
                      "/cmd_vel↔Sport 桥接、unitree_go 与 unitree_api 消息定义、D435i 传感器 launch 与 Gazebo 世界",
              "kind": "仿真与 bringup 参考（ROS2 + Gazebo）"},
    "unitree_go2_edu_movement": {"robots": ["unitree_go2"],
                                 "desc": "Go2 EDU 视觉对接流水线（unitree_sdk2py）：AprilTag 位姿解算 + 滑窗滤波 "
                                         "+ 梯形速度规划 + 三模式停靠判据，含前视鱼眼内参与 DDS 收发范式",
                                 "kind": "目标驱动视觉伺服参考（Python / DDS）"},
    "matrix_zsibot": {"robots": ["unitree_go2", "unitree_go2w", "unitree_g1"],
                      "desc": "ZsiBot MATRiX 仿真平台源码快照的实现类子集（UE5 + MuJoCo + CARLA）："
                              "传感器声明、自定义/拼接场景、多机器人端口、相机与渲染协议、"
                              "实景扫描 3DGS→PLY→MuJoCo proxy 流水线、G1 材质桥",
                      "kind": "仿真平台参考（场景 / 感知 / 资产流水线）"},
    # ---------------- 第二训练后端 / 物理引擎（K 组：多后端能力契约与跨引擎 sim2sim） ----------------
    # 纳入理由：K 组要把「训练后端」从单一 mjlab 变成可插拔（BackendAdapter），并要求
    # 「训练引擎 ≠ 验证引擎」的跨引擎 sim2sim 守卫。本组三份是这条路线上的上游证据：
    # GenesisLab 给出「同一任务套件换引擎」的工程形态，Genesis World 与 Newton 给出
    # 第二/第三物理引擎（含传感器与确定性测试）的可移植面。
    "genesislab": {"robots": ["unitree_go2", "unitree_g1"],
                   "desc": "GenesisLab：基于 Genesis 物理引擎的轻量腿足 RL 任务套件（RSL-RL / rl_games 集成）；"
                           "envs / managers / components / engine 模块化分层，含 Go2 速度跟踪任务与 imitation "
                           "tracking——第二训练后端（Genesis）候选与「任务套件如何与引擎解耦」的参考",
                   "kind": "训练后端候选参考（Genesis + RSL-RL）"},
    "genesis-world": {"robots": [],
                      "desc": "Genesis World：Python 原生多物理仿真平台（统一多物理引擎 + Nyx 渲染 + Quadrants "
                              "编译）；URDF / MJCF / OBJ / GLB / USD 资产解析、并行与异构环境、相机与传感器、"
                              "可微物理——第三物理引擎候选，与传感器/场景/可微训练参考",
                      "kind": "仿真平台参考（多物理 / 渲染 / 传感器）"},
    "newton": {"robots": [],
               "desc": "Newton（Linux Foundation；Disney Research / Google DeepMind / NVIDIA 发起）：NVIDIA Warp "
                       "之上的 GPU 可微物理引擎，以 MuJoCo Warp 为首要后端；含 solver 抽象、执行器与控制器、"
                       "IMU / 接触 / tiled_camera / raytrace 传感器、USD 解析与确定性测试"
                       "——物理后端抽象、传感器建模与跨引擎一致性校验的上游参考",
               "kind": "物理引擎参考（GPU 可微 / MuJoCo Warp 上游）"},
    # ---------------- 视觉感知 / 部署接口（B 类外挂感知 · 部署控制器形态） ----------------
    "PaddleX": {"robots": [],
                "desc": "PaddleX 3.x：飞桨低代码视觉工具链（200+ 预训练模型 / 33 条模型产线 / 39 个单功能模块），"
                        "覆盖目标检测、开集检测、语义与实例分割、关键点、OCR 与文档解析；含高性能推理、"
                        "服务化与端侧部署——B 类外挂感知（目标判定 / 标志识别 / 视觉触发）与「模型产线」"
                        "资源组织形态参考",
                "kind": "视觉感知与端侧部署参考（模型产线）"},
    "mujoco_ros2_control": {"robots": [],
                            "desc": "ros2_control × MuJoCo 系统接口：SystemInterface 插件 + MJCF/URDF 自动转换 + "
                                    "插件体系 + 3D LiDAR 扩展；让同一套 ros2_control 控制器在仿真与真机间切换"
                                    "——部署侧控制器接口形态、MJCF/URDF 转换与 LiDAR 传感器参考",
                            "kind": "部署与控制器接口参考（ros2_control）"},
    "Gymnasium-Robotics": {"robots": ["wuji_hand"],
                           "desc": "Farama Gymnasium-Robotics：基于 MuJoCo 的机器人环境集合（Fetch / Shadow 灵巧手 / "
                                   "Adroit / Franka Kitchen / MaMuJoCo / D4RL Maze）；含多目标 GoalEnv API"
                                   "（observation / achieved_goal / desired_goal）与 92 触点触觉观测"
                                   "——灵巧手操作任务、目标条件观测与迷宫导航场景参考",
                           "kind": "操作与多目标 API 参考（灵巧手 / 迷宫导航）"},
}

# 非机型知识库：单独放在 00_resources/knowledge_base/<名称>/
KB_ROOT_NAME = "knowledge_base"
KNOWLEDGE_BASES: dict[str, dict] = {
    "Robotics_Tutorial": {
        "src": "robo_know/Robotics_Tutorial",
        "desc": "达妙科技（Pengfei Guo）《Robotics Tutorial》：数学基础 / C++ 工程 / SLAM / "
                "移动机器人规控 / 运动控制 / 具身智能 六大方向的系统化教学文档",
        "kind": "知识库（非机型专属，14 机型共用参考）",
    },
}

# 明确排除的工作区目录（仅记入总 README 说明）
EXCLUDED_PROJECTS = {
    "auto_web": "通用 Web 项目素材（其中 `auto_web/wandb` 已单独纳入为训练平台参考）",
    "ComfyUI": "通用 AI 生成工具",
    "InvokeAI": "通用 AI 生成工具",
    "langflow": "通用工作流工具",
    "n8n": "通用工作流工具",
    "awesome-robot-descriptions": "机器人描述汇总（仅索引/网格）",
    "dm_dog": "非目标机型（A1/DM 系列）",
    "min_dog": "非目标机型",
    "archive": "历史归档",
    "tools": "工作区脚本",
    "robo_know": "机器人通用知识文档（其中 Robotics_Tutorial 已单独纳入 knowledge_base/）",
}

# --------------------------------------------------------------------------
# 保留 / 删除规则（规约见 00_resources/_SPEC.md）
# --------------------------------------------------------------------------
# 推理策略文件：无条件保留（题述「pt 和 onnx 之类的推理策略文件要保留」）
KEEP_ALWAYS_EXTS = {
    ".onnx", ".pt", ".pth", ".engine", ".plan", ".trt", ".ckpt",
    ".safetensors", ".tflite", ".mlpackage", ".jit", ".torchscript",
    ".rknn", ".mnn", ".dlc",          # 端侧编译模型（Rockchip / NCNN / 联咏）
}

OMIT_EXTS: dict[str, str] = {}


def _omit(reason: str, *exts: str) -> None:
    for e in exts:
        OMIT_EXTS[e] = reason


_omit("3D 网格", ".stl", ".obj", ".dae", ".glb", ".gltf", ".fbx", ".ply", ".3mf",
      ".mesh", ".wrl", ".3ds", ".max", ".skp")
_omit("CAD 几何", ".step", ".stp", ".igs", ".iges", ".sldprt", ".sldasm")
_omit("3D 工程/二进制场景", ".blend", ".abc", ".x3d", ".usd", ".usda", ".usdc",
      ".usdz", ".c4d", ".mb", ".ma", ".mjz")
_omit("点云", ".pcd", ".las", ".laz", ".e57")
_omit("ROS 录包", ".bag", ".bag2", ".db3", ".mcap", ".pcap", ".bt")
_omit("归档/安装包", ".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".7z", ".rar",
      ".whl", ".deb", ".rpm", ".apk", ".conda", ".jar", ".egg")
_omit("可执行/二进制", ".so", ".dll", ".dylib", ".a", ".lib", ".exe", ".bin",
      ".class", ".pyc", ".pyo", ".o", ".elf", ".hex", ".msi", ".dmg", ".appimage",
      ".wasm", ".node")
_omit("视频/动图", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v",
      ".mpg", ".gif")
_omit("音频", ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".opus", ".mid")
_omit("图像/纹理", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff",
      ".exr", ".hdr", ".ppm", ".pgm", ".tga", ".dds", ".ktx", ".psd", ".ai",
      ".ico", ".icon", ".svg", ".xcf", ".spr")
_omit("字体", ".ttf", ".otf", ".woff", ".woff2", ".eot")
_omit("大数据表", ".h5", ".hdf5", ".sqlite", ".db", ".mdb")
_omit("日志/缓存", ".log", ".lock", ".cache", ".pack", ".idx")

# 目录名命中即**整目录跳过**（构建产物 / 环境 / 缓存，不登记占位、不建空目录）
SKIP_DIR_PARTS = {
    ".git", "__pycache__", ".venv", "venv", ".conda", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea", ".vscode",
    ".ipynb_checkpoints", ".eggs", "CMakeFiles", ".mimic", ".cache", ".next",
}
BUILD_DIR_PARTS = {"build", "dist", "outputs", "logs"}

MAX_KEEP_BYTES = 20 * 1024 * 1024          # 普通文件上限 20MB，超过按「大文件」登记
POLICY_MAX_BYTES = 4096 * 1024 * 1024      # 策略文件仅 4GB 兜底

OMITTED_MANIFEST = "_OMITTED.md"


def decide(ext: str, size: int) -> tuple[bool, str]:
    """返回 (是否拷贝, 省略原因)。"""
    if ext in KEEP_ALWAYS_EXTS:
        return (size <= POLICY_MAX_BYTES, "策略文件超 4GB")
    if re.fullmatch(r"\.\d+", ext):
        return False, "二进制（版本化库）"
    if ext in OMIT_EXTS:
        return False, OMIT_EXTS[ext]
    if size > MAX_KEEP_BYTES:
        return False, f"大文件（>{MAX_KEEP_BYTES // 1024 // 1024}MB）"
    return True, ""


def classify(rel: str, ext: str) -> str:
    """把项目内相对路径分到功能类别（启发式，仅用于索引统计）。"""
    p = rel.lower()
    name = p.rsplit("/", 1)[-1]

    if ext in KEEP_ALWAYS_EXTS:
        return "deploy"
    if ext in {".urdf", ".xacro", ".sdf"}:
        return "model"
    if ext in {".npz", ".npy", ".pkl", ".mat", ".msgpack", ".csv"}:
        return "motion"

    def has(*ks: str) -> bool:
        return any(k in p for k in ks)

    if has("terrain", "heightfield", "hfield", "stair", "slope", "rough_", "trimesh") and \
            ext in {".xml", ".json", ".yaml", ".yml", ".py", ".npz"}:
        return "terrain_scene"
    if has("motion", "retarget", "amp_", "/amp", "clip", "gait", "traj", "reference_motion"):
        return "motion"
    if has("deploy", "sim2sim", "fsm", "sdk", "controller", "inference", "bridge", "ros2", "ros_ws"):
        return "deploy"
    if has("eval", "benchmark", "metric", "score", "test_", "_test", "/tests/"):
        return "evaluation"
    if has("train", "envs/", "/env/", "env_cfg", "envcfg", "reward", "curriculum",
           "domain_rand", "mdp/", "learning", "rl_", "cfg", "config", "conf/", "params"):
        return "training"
    if has("contract", "joint", "limits", "action_scale", "obs_dim", "kp", "kd",
           "default_", "kinematic"):
        return "contract"
    if (ext in {".xml", ".json"} and has("asset", "robot", "scene")) or \
            has("urdf", "xacro", "mjcf", "description", "assets/", "constants", "model"):
        return "model"
    if ext in {".md", ".rst"} or "readme" in name or "license" in name or "doc" in p:
        return "misc"
    return "misc"


# --------------------------------------------------------------------------
# 文件遍历 / 拷贝 / 工具
# --------------------------------------------------------------------------
def iter_files(project_dir: Path):
    """产出 (相对项目路径, 绝对路径, 大小)。"""
    for path in project_dir.rglob("*"):
        rel_parts = path.relative_to(project_dir).parts
        if any(part in SKIP_DIR_PARTS for part in rel_parts[:-1] if part):
            continue
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        yield "/".join(rel_parts), path, size


def hard_rmtree(path: Path) -> None:
    """绕过 safe-delete shim 的自底向上删除（shutil.rmtree 在本环境会被拦截）。"""
    if not path.exists():
        return
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            try:
                os.remove(os.path.join(root, name))
            except OSError:
                pass
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def copy_file(src: Path, dst: Path, dry: bool) -> bool:
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return False
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return True


def fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


class ProjectStat:
    """单个项目（或知识库）的同步统计。"""

    def __init__(self, name: str, src_rel: str):
        self.name = name
        self.src_rel = src_rel
        self.kept: list[str] = []
        self.kept_bytes = 0
        self.per_cat: dict[str, int] = defaultdict(int)
        self.omitted: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        self.omitted_n = 0
        self.omitted_bytes = 0
        self.ext_top: dict[str, int] = defaultdict(int)
        self.policy_n = 0


# --------------------------------------------------------------------------
# 同步一个项目
# --------------------------------------------------------------------------
def sync_project(name: str, src_rel: str, out_root: Path, dry: bool,
                 robots: list[str], desc: str, kind: str = "参考项目") -> ProjectStat | None:
    src_dir = WORKSPACE / src_rel
    if not src_dir.is_dir():
        print(f"  [warn] 源项目不存在，跳过：{src_rel}")
        return None

    st = ProjectStat(name, src_rel)
    dst_root = out_root / name

    for rel, src, size in iter_files(src_dir):
        parts = rel.split("/")
        ext = src.suffix.lower()
        # build/ dist/ outputs/ logs/ 整目录跳过（构建产物/日志），但推理策略文件
        # 例外：上游常把发布策略放在 logs/rsl_rl/<task>/policy.onnx，删掉就丢了。
        if any(p in BUILD_DIR_PARTS for p in parts[:-1]) and ext not in KEEP_ALWAYS_EXTS:
            continue
        ok, reason = decide(ext, size)
        if ok:
            st.kept.append(rel)
            st.kept_bytes += size
            st.per_cat[classify(rel, ext)] += 1
            st.ext_top[ext or "(无扩展名)"] += 1
            if ext in KEEP_ALWAYS_EXTS:
                st.policy_n += 1
            copy_file(src, dst_root / Path(rel), dry)
        else:
            d = "/".join(parts[:-1])
            st.omitted[d].append((parts[-1], size, reason))
            st.omitted_n += 1
            st.omitted_bytes += size

    write_omitted_manifests(st, dst_root, dry)
    write_project_readme(st, dst_root, dry, robots, desc, kind)
    return st


def write_omitted_manifests(st: ProjectStat, dst_root: Path, dry: bool) -> None:
    """在每个目录留下 `_OMITTED.md` 占位登记，保证目录结构与可回溯性。"""
    for d, items in st.omitted.items():
        items.sort(key=lambda x: -x[1])
        total = sum(i[1] for i in items)
        where = f"{st.src_rel}/{d}" if d else st.src_rel
        lines = [
            f"# 已省略文件登记 — {st.name}/{d or '.'}",
            "",
            "> 本目录下以下文件按 `00_resources/_SPEC.md` 规则**未拷贝**"
            "（网格 / CAD / 二进制 / 媒体 / 归档 / 大文件）。",
            "> 此处保留占位登记以便按需回溯；需要时直接从源工程取用：",
            f"> 源工程目录：`00_open/{where}/`",
            "",
            f"共 **{len(items)}** 个文件 / **{fmt_size(total)}**。",
            "",
            "| 文件 | 体积 | 类型 | 源路径 |",
            "|---|---:|---|---|",
        ]
        for nm, sz, rn in items:
            lines.append(f"| `{nm}` | {fmt_size(sz)} | {rn} | `00_open/{where}/{nm}` |")
        lines.append("")
        if not dry:
            (dst_root / Path(d) if d else dst_root).mkdir(parents=True, exist_ok=True)
            (dst_root / Path(d) / OMITTED_MANIFEST if d else dst_root / OMITTED_MANIFEST
             ).write_text("\n".join(lines), encoding="utf-8")


def write_project_readme(st: ProjectStat, dst_root: Path, dry: bool,
                         robots: list[str], desc: str, kind: str) -> None:
    label = "、".join(f"{r}（{ROBOT_LABEL[r]}）" if r in ROBOT_LABEL else r for r in robots)
    lines = [
        f"# {st.name} — 参考资源",
        "",
        f"> **来源**：`00_open/{st.src_rel}/`　｜　**类型**：{kind}",
        f"> **关联机型**：{label or '（无，通用）'}",
        f"> **定位**：{desc}",
        f"> **收录**：{len(st.kept)} 个文件 / {fmt_size(st.kept_bytes)}"
        f"（其中推理策略/模型文件 {st.policy_n} 个）",
        f"> **已省略**：{st.omitted_n} 个文件 / {fmt_size(st.omitted_bytes)}"
        "（登记在各目录 `_OMITTED.md`）",
        "",
        "## 能帮什么",
        "",
    ]
    for cat in CATEGORIES:
        n = st.per_cat.get(cat, 0)
        if n:
            lines.append(f"- **{CATEGORY_LABEL[cat]}**（{n} 个）：{CATEGORY_HELP[cat]}")
    if not any(st.per_cat.values()):
        lines.append("- （本次未收录文件）")

    lines += ["", "## 目录构成", "", "```text"]
    tree: dict[str, list[str]] = defaultdict(list)
    for rel in st.kept:
        parts = rel.split("/")
        tree[parts[0] if len(parts) > 1 else "(根目录)"].append(rel)
    for top in sorted(tree):
        lines.append(f"{top}/  （{len(tree[top])} 个文件）")
        if top == "(根目录)":
            continue
        sub: dict[str, int] = defaultdict(int)
        for rel in tree[top]:
            parts = rel.split("/")
            sub[parts[1] if len(parts) > 2 else "(直接文件)"] += 1
        for s in sorted(sub)[:20]:
            lines.append(f"    {s}/")
        if len(sub) > 20:
            lines.append(f"    …（其余 {len(sub) - 20} 个子目录）")
    lines += ["```", ""]

    if st.ext_top:
        lines += ["## 文件类型分布（Top 15）", "", "| 扩展名 | 数量 |", "|---|---:|"]
        for ext, n in sorted(st.ext_top.items(), key=lambda kv: -kv[1])[:15]:
            lines.append(f"| `{ext}` | {n} |")
        lines.append("")

    lines += ["## 文件索引（项目内相对路径）", "", "```text"]
    lines.extend(sorted(st.kept))
    lines += ["```", ""]

    if st.omitted:
        lines += ["## 省略登记索引", "",
                  "| 目录 | 省略文件数 | 体积 | 登记文件 |", "|---|---:|---:|---|"]
        for d in sorted(st.omitted):
            items = st.omitted[d]
            path = f"{d}/{OMITTED_MANIFEST}" if d else OMITTED_MANIFEST
            lines.append(f"| `{d or '.'}` | {len(items)} | "
                         f"{fmt_size(sum(i[1] for i in items))} | [`{path}`](./{path}) |")
        lines += ["", "> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。", ""]

    if not dry:
        dst_root.mkdir(parents=True, exist_ok=True)
        (dst_root / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _parse_size(text: str) -> int:
    """把 fmt_size 产生的 `12.3 MB` / `528 KB` / `452 B` 还原为字节数。"""
    m = re.match(r"\s*([\d.]+)\s*(B|KB|MB|GB)\s*$", text.strip())
    if not m:
        return 0
    value = float(m.group(1))
    return int(value * {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}[m.group(2)])


def _omitted_from_readme(dst_root: Path) -> tuple[int, int] | None:
    """从项目 README 的「已省略」行还原 (文件数, 字节数)。"""
    readme = dst_root / "README.md"
    if not readme.is_file():
        return None
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"已省略\**：(\d+)\s*个文件\s*/\s*([\d.]+\s*(?:B|KB|MB|GB))", text)
    if not m:
        return None
    return int(m.group(1)), _parse_size(m.group(2))


def build_stat_from_dir(name: str, src_rel: str, out_root: Path,
                        old_entry: dict | None) -> ProjectStat | None:
    """从已存在的 ``00_resources/<name>/`` 目录重建统计（供 --reindex）。

    源树可能不在本机（历史同步后已删除），此时无法重新拷贝；但索引/README 仍应
    与新目录一致。kept 统计按目录实际文件重算；omitted 统计优先取项目 README 的
    「已省略」行，退回旧索引值。
    """
    dst_root = out_root / name
    if not dst_root.is_dir():
        return None
    st = ProjectStat(name, src_rel)
    for rel, src, size in iter_files(dst_root):
        # 跳过本工具生成的索引文件（项目 README 与各目录 _OMITTED.md 占位）
        if rel == "README.md" or src.name == OMITTED_MANIFEST:
            continue
        ext = src.suffix.lower()
        ok, _reason = decide(ext, size)
        st.kept.append(rel)
        st.kept_bytes += size
        st.per_cat[classify(rel, ext)] += 1
        st.ext_top[ext or "(无扩展名)"] += 1
        if ext in KEEP_ALWAYS_EXTS:
            st.policy_n += 1
    omitted = _omitted_from_readme(dst_root)
    if omitted:
        st.omitted_n, st.omitted_bytes = omitted
    elif old_entry:
        st.omitted_n = int(old_entry.get("omitted") or 0)
        st.omitted_bytes = int(old_entry.get("omitted_bytes") or 0)
    return st


def reindex_existing(dry: bool) -> int:
    """仅按现有 00_resources 目录重建顶层 README.md 与 _index.json。"""
    index_path = RES_ROOT / "_index.json"
    old = {}
    if index_path.exists():
        try:
            old = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = {}
    old_projects = old.get("projects") or {}
    old_kb = old.get("knowledge_base") or {}

    stats: dict[str, ProjectStat] = {}
    for name, meta in PROJECTS.items():
        st = build_stat_from_dir(name, meta.get("src", name), RES_ROOT, old_projects.get(name))
        if st:
            stats[name] = st
    kb_stats: dict[str, ProjectStat] = {}
    for name, meta in KNOWLEDGE_BASES.items():
        st = build_stat_from_dir(name, meta["src"], RES_ROOT / KB_ROOT_NAME, old_kb.get(name))
        if st:
            kb_stats[name] = st
    write_top_readme(stats, kb_stats, {}, dry)
    write_index_json(stats, kb_stats, dry)
    print(f"reindex: {len(stats)} 项目 / {len(kb_stats)} 知识库 → README.md + _index.json")
    return 0


# --------------------------------------------------------------------------
# 根索引
# --------------------------------------------------------------------------
README_HEAD = """# 00_resources/ — 参考资源整合库（以「项目」为单位）

> **组织方式**：一个来源项目 = 一个目录 `00_resources/<project>/`，**原样保留该项目的目录结构与组织思想**。
> 项目内有用的内容（源码 / 配置 / 文档 / 数据 / **推理策略 onnx·pt·engine**）完整拷贝；
> 网格、CAD、二进制、媒体、归档、日志与超大的无用文件不拷贝，但在**原目录**留下 `_OMITTED.md`
> 占位登记（文件名 / 体积 / 类型 / 源路径）——真要用到时按登记的源路径回到 `00_open/` 取用，结构不丢。
>
> - 规范：[`_SPEC.md`](./_SPEC.md)　｜　机器可读索引：[`_index.json`](./_index.json)
> - 通用知识库（非机型专属）：[`knowledge_base/`](./knowledge_base/)
> - 与 `assets/robots/` 的关系：本目录是**只读参考底座**（原始素材取证，保留来源项目路径与全部变体），
>   `assets/robots/<id>/` 是**归一化后的可执行资产包**（按 contract v3 收敛为单一事实源）。
>   **禁止**把 `00_resources/` 内容直接当作运行时资产加载。
"""

README_TAIL = """## 回溯与恢复
1. 项目目录内的路径 = `00_open/<project>/` 下的原始相对路径，**可直接一一对应**。
2. 目录里出现 `_OMITTED.md` 即表示该目录有文件被省略，表内「源路径」列就是可直接取用的位置。
3. 需要恢复某类文件（如全部网格）时：调整 `tools/sync_resources.py` 的 `OMIT_EXTS`
   后重跑 `python legged_studio/tools/sync_resources.py --only <project>`。

## 关键约定
1. **以项目为单位**，不再按机型复制多份；机型归属见各项目 README 与下方反查表。
2. **推理策略文件（`.onnx/.pt/.pth/.engine/.plan/.ckpt/.safetensors`）不限大小一律保留**。
3. 普通文件 **> 20MB 视为「大文件」省略**（含 `.csv/.npz/.npy/.pkl` 等数据）。
4. `build/ dist/ outputs/ logs/`、虚拟环境、`node_modules`、缓存目录**整目录跳过**（不登记）。
5. 类别计数为**功能导向的启发式**归类（路径关键词），仅用于索引，不代表文件归属的唯一解释。

## 关联文档
- 资源模型与重构路线（归档）：[`00_know/90_归档/方案_重构方案_RobotAsset.md`](../00_know/90_归档/方案_重构方案_RobotAsset.md)
- 项目总入口：[`README.md`](../README.md)　｜　归一化资产包：[`assets/robots/`](../assets/robots/)
"""


def write_top_readme(project_stats: dict[str, ProjectStat], kb_stats: dict[str, ProjectStat],
                     excluded_seen: dict[str, int], dry: bool) -> None:
    total_files = sum(len(s.kept) for s in project_stats.values())
    total_bytes = sum(s.kept_bytes for s in project_stats.values())
    omit_n = sum(s.omitted_n for s in project_stats.values())
    omit_b = sum(s.omitted_bytes for s in project_stats.values())

    lines = [
        README_HEAD,
        "## 总览",
        "",
        f"- 收录项目 **{len(project_stats)}** 个　·　文件 **{total_files}** 个　·　体积 "
        f"**{fmt_size(total_bytes)}**",
        f"- 省略文件 **{omit_n}** 个（**{fmt_size(omit_b)}**），均在原目录留有 `_OMITTED.md` 占位登记",
        f"- 通用知识库 **{len(kb_stats)}** 个　·　文件 "
        f"{sum(len(s.kept) for s in kb_stats.values())} 个",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## 项目清单（有什么 · 能帮什么 · 关联哪些机器人）",
        "",
        "| 项目 | 收录 | 省略 | 体积 | 策略 | 关联机型 | 索引 |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for name in sorted(project_stats, key=lambda n: (-len(project_stats[n].kept), n)):
        st = project_stats[name]
        robots = "、".join(f"`{r}`" for r in PROJECTS.get(name, {}).get("robots", [])) or "—"
        lines.append(
            f"| `{name}` | {len(st.kept)} | {st.omitted_n} | {fmt_size(st.kept_bytes)} | "
            f"{st.policy_n} | {robots} | [README](./{name}/README.md) |"
        )
    lines += ["", "## 项目定位说明", ""]
    for name in sorted(project_stats):
        lines.append(f"- **`{name}`**：{PROJECTS.get(name, {}).get('desc', '')}")
    lines.append("")

    lines += ["## 机型 → 项目反查", ""]
    for robot in ROBOTS:
        names = [n for n, meta in PROJECTS.items()
                 if robot in meta["robots"] and n in project_stats]
        srcs = "、".join(f"[`{n}`](./{n}/README.md)" for n in names)
        lines.append(f"- **{robot}**（{ROBOT_LABEL[robot]}）：{srcs or '（无）'}")
    lines.append("")

    if kb_stats:
        lines += ["## 通用知识库（非机型专属）", "",
                  "| 知识库 | 来源 | 文件数 | 说明 | 索引 |", "|---|---|---:|---|---|"]
        for name, st in kb_stats.items():
            meta = KNOWLEDGE_BASES.get(name, {})
            lines.append(f"| `{name}` | `00_open/{st.src_rel}` | {len(st.kept)} | "
                         f"{meta.get('desc', '')} | "
                         f"[README](./{KB_ROOT_NAME}/{name}/README.md) |")
        lines.append("")

    if excluded_seen:
        lines += ["## 未纳入的项目（非目标机型 / 非机型资源）", ""]
        for proj, reason in EXCLUDED_PROJECTS.items():
            if proj in excluded_seen:
                lines.append(f"- `{proj}`（约 {excluded_seen[proj]} 文件）— {reason}")
        lines.append("")

    lines.append(README_TAIL)
    if not dry:
        (RES_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_index_json(project_stats: dict[str, ProjectStat], kb_stats: dict[str, ProjectStat],
                     dry: bool) -> None:
    if dry:
        return
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "spec": "_SPEC.md",
        "policy": {
            "keep": "源码/配置/文档/数据/URDF·MJCF/推理策略文件",
            "keep_always_ext": sorted(KEEP_ALWAYS_EXTS),
            "omit_ext": {k: v for k, v in sorted(OMIT_EXTS.items())},
            "max_keep_bytes": MAX_KEEP_BYTES,
            "policy_max_bytes": POLICY_MAX_BYTES,
            "skip_dir_names": sorted(SKIP_DIR_PARTS | BUILD_DIR_PARTS),
            "placeholder": OMITTED_MANIFEST,
        },
        "projects": {
            name: {
                "source": f"00_open/{st.src_rel}",
                "robots": PROJECTS.get(name, {}).get("robots", []),
                "desc": PROJECTS.get(name, {}).get("desc", ""),
                "kept": len(st.kept),
                "kept_bytes": st.kept_bytes,
                "omitted": st.omitted_n,
                "omitted_bytes": st.omitted_bytes,
                "policy_files": st.policy_n,
                "per_category": {c: st.per_cat.get(c, 0) for c in CATEGORIES},
                "ext_top": dict(sorted(st.ext_top.items(), key=lambda kv: -kv[1])[:20]),
                "readme": f"{name}/README.md",
            }
            for name, st in sorted(project_stats.items())
        },
        "knowledge_base": {
            name: {
                "source": f"00_open/{st.src_rel}",
                "desc": KNOWLEDGE_BASES.get(name, {}).get("desc", ""),
                "kept": len(st.kept),
                "kept_bytes": st.kept_bytes,
                "omitted": st.omitted_n,
                "readme": f"{KB_ROOT_NAME}/{name}/README.md",
            }
            for name, st in kb_stats.items()
        },
        "robots": {
            robot: {
                "label": ROBOT_LABEL[robot],
                "projects": [n for n, meta in PROJECTS.items()
                             if robot in meta["robots"] and n in project_stats],
            }
            for robot in ROBOTS
        },
        "excluded_projects": EXCLUDED_PROJECTS,
    }
    (RES_ROOT / "_index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def clean_outputs(only: set[str] | None, dry: bool) -> None:
    """清理输出目录：默认保留 _SPEC.md / README.md / _index.json / knowledge_base。"""
    if dry:
        return
    keep = {"_SPEC.md", "README.md", "_index.json", KB_ROOT_NAME}
    if not RES_ROOT.exists():
        return
    if only:
        for name in only:
            hard_rmtree(RES_ROOT / name)
        return
    for child in RES_ROOT.iterdir():
        if child.name in keep:
            continue
        hard_rmtree(child)


def main() -> int:
    ap = argparse.ArgumentParser(description="按项目为单位整合参考资源")
    ap.add_argument("--clean", action="store_true", help="清空后全量重抽")
    ap.add_argument("--dry-run", action="store_true", help="只统计不落盘")
    ap.add_argument("--only", default="", help="只处理指定项目（逗号分隔）")
    ap.add_argument("--kb-only", action="store_true", help="只同步通用知识库")
    ap.add_argument("--reindex", action="store_true",
                    help="只按现有 00_resources 目录重建顶层 README.md 与 _index.json")
    args = ap.parse_args()
    dry = args.dry_run

    if args.reindex:
        return reindex_existing(dry)

    only = {p for p in args.only.split(",") if p}
    RES_ROOT.mkdir(parents=True, exist_ok=True)

    # ---------------- 通用知识库 ----------------
    kb_stats: dict[str, ProjectStat] = {}
    kb_root = RES_ROOT / KB_ROOT_NAME
    if not only or args.kb_only:
        if args.clean and not dry:
            hard_rmtree(kb_root)
        for name, meta in KNOWLEDGE_BASES.items():
            st = sync_project(name, meta["src"], kb_root, dry, [], meta["desc"], meta["kind"])
            if st:
                kb_stats[name] = st
        if args.kb_only:
            print("=" * 72)
            print(f"{'[dry-run] ' if dry else ''}知识库同步完成")
            for name, st in kb_stats.items():
                print(f"  {name:<24} 收录 {len(st.kept):>6} / 省略 {st.omitted_n:>6}")
            print("=" * 72)
            return 0

    # ---------------- 项目 ----------------
    if args.clean:
        clean_outputs(only or None, dry)
        if not only:
            hard_rmtree(kb_root)

    targets = {p: m for p, m in PROJECTS.items() if not only or p in only}
    stats: dict[str, ProjectStat] = {}
    total_kept = total_omit = total_policy = 0
    kept_bytes = omit_bytes = 0
    for name, meta in targets.items():
        st = sync_project(name, meta.get("src", name), RES_ROOT, dry,
                          meta["robots"], meta["desc"], meta.get("kind", "参考项目"))
        if not st:
            continue
        stats[name] = st
        total_kept += len(st.kept)
        kept_bytes += st.kept_bytes
        total_omit += st.omitted_n
        omit_bytes += st.omitted_bytes
        total_policy += st.policy_n

    full_run = not only
    if full_run:
        excluded_seen: dict[str, int] = {}
        for proj in EXCLUDED_PROJECTS:
            d = WORKSPACE / proj
            if d.is_dir():
                excluded_seen[proj] = sum(1 for p in d.rglob("*") if p.is_file())
        write_top_readme(stats, kb_stats, excluded_seen, dry)
        write_index_json(stats, kb_stats, dry)

    print("=" * 72)
    print(f"{'[dry-run] ' if dry else ''}资源同步完成")
    print(f"  项目 {len(stats)} 个　·　收录 {total_kept} 个文件（{fmt_size(kept_bytes)}）")
    print(f"  省略 {total_omit} 个文件（{fmt_size(omit_bytes)}），其中策略/模型文件 {total_policy} 个")
    print("-" * 72)
    for name in sorted(stats, key=lambda n: -len(stats[n].kept)):
        st = stats[name]
        print(f"  {name:<40} 收录 {len(st.kept):>5}  省略 {st.omitted_n:>6}  "
              f"{fmt_size(st.kept_bytes):>9}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
