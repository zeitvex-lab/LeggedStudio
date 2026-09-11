from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from isaaclab.app import AppLauncher

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import cli_args  # noqa: E402

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Play an ONNX policy with ROS2-published sensors.")
parser.add_argument("--video", action="store_true", default=False)
parser.add_argument("--video_length", type=int, default=200)
parser.add_argument("--disable_fabric", action="store_true", default=False)
parser.add_argument("--num_envs", type=int, default=None)
parser.add_argument("--task", type=str, default=None)
parser.add_argument("--agent", type=str, default="rsl_rl_cfg_entry_point")
parser.add_argument("--seed", type=int, default=None)
parser.add_argument("--real-time", action="store_true", default=False)
parser.add_argument("--keyboard", action="store_true", default=False,
                    help="Pure keyboard teleop (建图阶段使用).")
# ---------------------------------------------------------------------------
# ★ nav mode: now uses hybrid A* planner + keyboard (replaces /cmd_vel bridge)
# ---------------------------------------------------------------------------
parser.add_argument("--nav", action="store_true", default=False,
                    help="Hybrid autonomous mode: A* planner from YAML map + keyboard override. "
                         "Keys: K=plan+start, G=plan only, C/Space=cancel, Arrow/N/M=manual.")
parser.add_argument("--map_yaml", type=str,
                    default="/home/user/rl_training/scripts/reinforcement_learning/rsl_rl/map/yq_1_mesh_vis.yaml",
                    help="ROS occupancy-map YAML for A* planning.")
parser.add_argument("--goal_x", type=float, default=0.0,
                    help="Nav goal X coordinate in world frame (m).")
parser.add_argument("--goal_y", type=float, default=0.0,
                    help="Nav goal Y coordinate in world frame (m).")
parser.add_argument("--inflation_radius", type=float, default=0.6,
                    help="Soft inflation radius for A* clearance cost (m). 路径代价惩罚层。")
parser.add_argument("--hard_inflation_radius", type=float, default=0.35,
                    help="Hard inflation radius = robot physical radius (m). A*完全不能通过的硬障碍层。")
# ---------------------------------------------------------------------------
# ★ multi-path mode: random perturbed paths
# ---------------------------------------------------------------------------
parser.add_argument("--multi_paths", type=int, default=5,
                    help="Number of random-perturbed A* paths for T key multi-path mode.")
parser.add_argument("--multi_perturb_m", type=float, default=3.0,
                    help="Max goal perturbation radius (m) for multi-path mode.")
# ---------------------------------------------------------------------------
# ★ cmd_vel mode: subscribe to /cmd_vel and inject into policy command manager
# ---------------------------------------------------------------------------
parser.add_argument("--cmd_vel", action="store_true", default=False,
                    help="通过 ROS2 /cmd_vel topic 控制机器人速度（速度响应测试 / 外部导航栈接入）。"
                         "与 --keyboard / --nav 互斥。")
parser.add_argument("--cmd_vel_topic", type=str, default="/cmd_vel",
                    help="cmd_vel 订阅的 topic 名称（默认 /cmd_vel）。")
# ---------------------------------------------------------------------------
# Velocity limits (shared by keyboard, auto follower, and cmd_vel bridge)
parser.add_argument("--max_lin_x", type=float, default=2.0)
parser.add_argument("--max_lin_y", type=float, default=1.0)
parser.add_argument("--max_ang_z", type=float, default=1.5)
# Existing args
parser.add_argument("--onnx", type=str, default=None)
parser.add_argument("--onnx_cpu", action="store_true", default=False)
parser.add_argument("--enable_ros2_bridge", action="store_true", default=True)
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()

# ---------------------------------------------------------------------------
# 模式互斥检查
# ---------------------------------------------------------------------------
if args_cli.keyboard and args_cli.nav:
    raise SystemExit("--keyboard 和 --nav 互斥，只能选一个。")
if args_cli.cmd_vel and args_cli.nav:
    raise SystemExit("--cmd_vel 和 --nav 互斥，只能选一个。")
if args_cli.cmd_vel and args_cli.keyboard:
    raise SystemExit("--cmd_vel 和 --keyboard 互斥，只能选一个。")

args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ---------------------------------------------------------------------------
# Imports after AppLauncher
# ---------------------------------------------------------------------------
import heapq
import threading
import time
from typing import Optional

import carb
import carb.input
import gymnasium as gym
import numpy as np
import omni.appwindow
import onnxruntime as ort
import torch
import yaml
import select
import termios
import tty
from deeprobotics.rsl_rl.modules import HIMActorCritic
from carb.input import KeyboardEventType, KeyboardInput
from PIL import Image

try:
    import matplotlib
    matplotlib.use("Agg")   # 无头环境，不弹窗
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    _MPL_AVAILABLE = True
except Exception:
    _MPL_AVAILABLE = False
    print("[NavMap] matplotlib not found – PNG export will use PIL fallback.")

# Suppress noisy warnings
carb.logging.acquire_logging().set_level_threshold_for_source(
    "isaacsim.core.simulation_manager.plugin",
    carb.logging.LogSettingBehavior.OVERRIDE, carb.logging.LEVEL_ERROR,
)
carb.logging.acquire_logging().set_level_threshold_for_source(
    "omni.timeline.plugin",
    carb.logging.LogSettingBehavior.OVERRIDE, carb.logging.LEVEL_ERROR,
)

from isaaclab.devices import Se2Keyboard, Se2KeyboardCfg  # noqa: E402
from isaaclab.envs import (  # noqa: E402
    DirectMARLEnv, DirectMARLEnvCfg, DirectRLEnvCfg,
    ManagerBasedRLEnvCfg, multi_agent_to_single_agent,
)
from isaaclab.managers import ObservationTermCfg as ObsTerm  # noqa: E402
from isaaclab.utils.assets import retrieve_file_path  # noqa: E402
from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlVecEnvWrapper  # noqa: E402
from isaaclab_tasks.utils import get_checkpoint_path  # noqa: E402
from isaaclab_tasks.utils.hydra import hydra_task_config  # noqa: E402

import rl_training.tasks  # noqa: F401, E402
from rl_utils import camera_follow  # noqa: E402
from ros2_bridge_graph_m20 import Ros2M20BridgeCfg, build_ros2_bridge_graph  # noqa: E402
from ros2_cmd_vel_bridge import CmdVelBridge
import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics
# GPU (CuPy) detection – used by GridMap2D.inflate / distance_transform
try:
    import cupy as _cp
    import cupyx.scipy.ndimage as _cupy_ndimage
    _GPU_AVAILABLE = True
    print(f"[GPU] CuPy detected: {_cp.__version__}")
except Exception:
    _cp = None
    _cupy_ndimage = None
    _GPU_AVAILABLE = False

try:
    from scipy import ndimage as _scipy_ndimage
except Exception:
    _scipy_ndimage = None


# ===========================================================================
# Path-planning constants  (mirrors slam_nav_multi_road.py CONFIG section)
# ===========================================================================
# 初始化目标速度
target_vx, target_vy, target_wz = 0.0, 0.0, 0.0
lookahead_dist = 0.5  # 前瞻距离，根据 M20 步速调整
# WaypointFollower behaviour
AUTO_REACH_TOL             = 0.40
AUTO_SLOWDOWN_RADIUS       = 0.80
AUTO_MAX_VX                = 2.00
AUTO_MAX_VY                = 1.00
AUTO_MAX_WZ                = 1.50
AUTO_KP_FWD                = 1.000
AUTO_KP_LAT                = 1.00
AUTO_KP_YAW                = 1.20
AUTO_ROTATE_IN_PLACE_YAW   = 0.60
AUTO_ALLOW_FWD_YAW         = 0.25
AUTO_MIN_FWD_DIST          = 0.08
AUTO_MIN_CRUISE_VX         = 0.80
AUTO_STUCK_DIST            = 0.30
AUTO_STUCK_STEPS           = 180
AUTO_STUCK_PROGRESS_EPS    = 0.005
AUTO_DEBUG_PRINT_EVERY_STEPS = 250
AUTO_CORNER_REACH_TOL      = 0.40
AUTO_CORNER_SLOWDOWN_DIST  = 1.20
AUTO_CORNER_SLOWDOWN_SCALE = 0.75
AUTO_CORNER_ANGLE_DEG      = 35.0
AUTO_SEGMENT_LOOKAHEAD     = 0.35
AUTO_CTE_GAIN              = 2.0
AUTO_SEGMENT_END_SWITCH_DIST = 0.22
AUTO_CORNER_TURN_ONLY_YAW  = 0.4
AUTO_CORNER_APPROACH_VX    = 0.45

# A* planner
ASTAR_ALLOW_DIAGONAL          = True
ASTAR_USE_CLEARANCE_COST      = True
ASTAR_CLEARANCE_SAFE_DIST     = 0.5
ASTAR_CLEARANCE_COST_WEIGHT   = 6.0
ASTAR_CLEARANCE_POWER         = 2.0
ASTAR_MIN_WAYPOINT_SPACING    = 4.0
ASTAR_WAYPOINT_DENSIFY_SPACING= 4.0
ASTAR_CORNER_ANGLE_DEG        = 35.0
ASTAR_CORNER_INSERT_SPACING   = 0.25
ASTAR_SIMPLIFY_PATH           = True
OCC_MAP_TREAT_UNKNOWN_AS_OCCUPIED = True
GRID_RESOLUTION               = None   # None → use YAML resolution

# Keyboard linear/yaw speed for manual teleop in nav mode
KB_LINEAR_SPEED = 2.0
KB_YAW_SPEED    = 1.2


# ===========================================================================
# 3DGS 碰撞体初始化
# ===========================================================================
def apply_collision_to_3dgs(prim_path: str, approximation: str = "none") -> int:
    """遍历 3DGS prim 下所有 UsdGeom.Mesh，手动添加 PhysicsCollisionAPI。

    RTX lidar 的光线追踪需要 PhysicsCollisionAPI 才能命中 mesh。
    3DGS 导出的 USDZ 通常不自带碰撞体，必须在加载后显式遍历添加。

    Args:
        prim_path:     3DGS 根 prim 路径，例如 '/World/envs/env_0/gauss'
        approximation: 碰撞近似方式
                       'none'               → 直接三角网格（最精确，推荐用于 lidar）
                       'convexDecomposition'→ 凸分解（性能好，适合大场景）
                       'convexHull'         → 凸包（最快，精度低）
    Returns:
        添加碰撞的 mesh 数量
    """
    stage = omni.usd.get_context().get_stage()
    root_prim = stage.GetPrimAtPath(prim_path)
    if not root_prim or not root_prim.IsValid():
        print(f"[Collision] Prim not found at: {prim_path}, skipping collision setup.")
        return 0

    count = 0
    for prim in Usd.PrimRange(root_prim):
        if prim.IsA(UsdGeom.Mesh):
            UsdPhysics.CollisionAPI.Apply(prim)
            mesh_api = UsdPhysics.MeshCollisionAPI.Apply(prim)
            mesh_api.CreateApproximationAttr().Set(approximation)
            col_api = UsdPhysics.CollisionAPI.Get(prim.GetStage(), prim.GetPath())
            col_api.CreateCollisionEnabledAttr(True)
            count += 1

    print(f"[Collision] Applied '{approximation}' collision to {count} mesh(es) under {prim_path}")
    return count


# ===========================================================================
# GridMap2D  (ported from slam_nav_multi_road.py)
# ===========================================================================
class GridMap2D:
    def __init__(self, origin_xy, resolution: float,
                 width_m=None, height_m=None, yaw: float = 0.0, grid=None):
        self.origin_xy  = (float(origin_xy[0]), float(origin_xy[1]))
        self.resolution = float(resolution)
        self.yaw        = float(yaw)
        if grid is not None:
            self.grid = np.array(grid, dtype=np.uint8)
            if self.grid.ndim != 2:
                raise ValueError("GridMap2D grid must be 2-D.")
            self.height, self.width = self.grid.shape
        else:
            self.width  = int(np.ceil(float(width_m)  / self.resolution))
            self.height = int(np.ceil(float(height_m) / self.resolution))
            self.grid   = np.zeros((self.height, self.width), dtype=np.uint8)
        self._obstacle_distance_map_m = None

    @property
    def shape(self):
        return self.grid.shape

    @property
    def width_m(self):
        return float(self.width) * self.resolution

    @property
    def height_m(self):
        return float(self.height) * self.resolution

    def _world_to_local(self, x, y):
        dx = float(x) - self.origin_xy[0]
        dy = float(y) - self.origin_xy[1]
        c, s = np.cos(self.yaw), np.sin(self.yaw)
        return c * dx + s * dy, -s * dx + c * dy

    def _local_to_world(self, lx, ly):
        c, s = np.cos(self.yaw), np.sin(self.yaw)
        return (self.origin_xy[0] + c * lx - s * ly,
                self.origin_xy[1] + s * lx + c * ly)

    def world_to_grid(self, x, y):
        lx, ly = self._world_to_local(x, y)
        return int(np.floor(ly / self.resolution)), int(np.floor(lx / self.resolution))

    def grid_to_world(self, i, j):
        lx = (float(j) + 0.5) * self.resolution
        ly = (float(i) + 0.5) * self.resolution
        return self._local_to_world(lx, ly)

    def in_bounds(self, i, j):
        return 0 <= i < self.height and 0 <= j < self.width

    def is_free(self, i, j):
        return self.in_bounds(i, j) and self.grid[i, j] == 0

    def nearest_free_cell(self, i: int, j: int, max_r: int = 30):
        if self.is_free(i, j):
            return i, j
        for r in range(1, max_r + 1):
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    if self.is_free(i + di, j + dj):
                        return i + di, j + dj
        return None

    def inflate(self, radius_m: float):
        radius_cells = int(np.ceil(float(radius_m) / self.resolution))
        if radius_cells <= 0 or np.all(self.grid == 0):
            return
        if _GPU_AVAILABLE:
            try:
                ys, xs = _cp.ogrid[-radius_cells:radius_cells+1,
                                   -radius_cells:radius_cells+1]
                struct = ((xs*xs + ys*ys) <= radius_cells*radius_cells).astype(_cp.uint8)
                g = _cp.asarray((self.grid > 0).astype(np.uint8))
                inflated = _cupy_ndimage.binary_dilation(g, structure=struct)
                self.grid = _cp.asnumpy(inflated).astype(np.uint8)
                self._obstacle_distance_map_m = None
                return
            except Exception:
                pass
        if _scipy_ndimage is not None:
            ys, xs = np.ogrid[-radius_cells:radius_cells+1,
                              -radius_cells:radius_cells+1]
            struct   = (xs*xs + ys*ys) <= radius_cells*radius_cells
            from scipy.ndimage import binary_dilation
            self.grid = binary_dilation(self.grid > 0, structure=struct).astype(np.uint8)
            self._obstacle_distance_map_m = None
            return
        # Pure-Python fallback
        occ = np.argwhere(self.grid > 0)
        inflated = self.grid.copy()
        offsets = [(di, dj)
                   for di in range(-radius_cells, radius_cells + 1)
                   for dj in range(-radius_cells, radius_cells + 1)
                   if di*di + dj*dj <= radius_cells*radius_cells]
        for i_o, j_o in occ:
            for di, dj in offsets:
                ni, nj = i_o + di, j_o + dj
                if 0 <= ni < self.height and 0 <= nj < self.width:
                    inflated[ni, nj] = 1
        self.grid = inflated
        self._obstacle_distance_map_m = None

    def compute_obstacle_distance_map_m(self):
        if self._obstacle_distance_map_m is not None:
            return self._obstacle_distance_map_m
        free_mask = (self.grid == 0).astype(np.uint8)
        if _GPU_AVAILABLE:
            try:
                dist = _cupy_ndimage.distance_transform_edt(_cp.asarray(free_mask))
                self._obstacle_distance_map_m = (
                    _cp.asnumpy(dist).astype(np.float32) * float(self.resolution))
                return self._obstacle_distance_map_m
            except Exception:
                pass
        if _scipy_ndimage is not None:
            dist = _scipy_ndimage.distance_transform_edt(free_mask)
            self._obstacle_distance_map_m = dist.astype(np.float32) * float(self.resolution)
            return self._obstacle_distance_map_m
        # Dijkstra fallback
        dist_arr = np.full((self.height, self.width), np.inf, dtype=np.float32)
        heap = []
        for i in range(self.height):
            for j in range(self.width):
                if self.grid[i, j] > 0:
                    dist_arr[i, j] = 0.0
                    heapq.heappush(heap, (0.0, i, j))
        while heap:
            d, i, j = heapq.heappop(heap)
            if d > dist_arr[i, j]:
                continue
            for di, dj in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                ni, nj = i+di, j+dj
                if not (0 <= ni < self.height and 0 <= nj < self.width):
                    continue
                nd = d + float(np.hypot(di, dj)) * self.resolution
                if nd < dist_arr[ni, nj]:
                    dist_arr[ni, nj] = nd
                    heapq.heappush(heap, (nd, ni, nj))
        self._obstacle_distance_map_m = dist_arr
        return dist_arr


# ===========================================================================
# load_ros_occupancy_map  (ported from slam_nav_multi_road.py)
# ===========================================================================
def load_ros_occupancy_map(yaml_path: str, image_override: str = "",
                           treat_unknown_as_occupied: bool = True):
    yaml_path = os.path.expanduser(str(yaml_path))
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"Occupancy map YAML not found: {yaml_path}")
    with open(yaml_path, "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    if not isinstance(meta, dict):
        raise RuntimeError(f"Invalid occupancy map YAML: {yaml_path}")

    image_path = str(image_override or meta.get("image", "")).strip()
    if not image_path:
        raise RuntimeError(f"Occupancy map YAML has no image field: {yaml_path}")
    if not os.path.isabs(image_path):
        image_path = os.path.join(os.path.dirname(yaml_path), image_path)
    image_path = os.path.expanduser(image_path)
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Occupancy map image not found: {image_path}")

    resolution      = float(meta.get("resolution"))
    origin          = meta.get("origin", [0.0, 0.0, 0.0])
    origin_x        = float(origin[0])
    origin_y        = float(origin[1])
    origin_yaw      = float(origin[2]) if len(origin) >= 3 else 0.0
    negate          = int(meta.get("negate", 0))
    occupied_thresh = float(meta.get("occupied_thresh", meta.get("occupied_threshold", 0.65)))
    free_thresh     = float(meta.get("free_thresh", meta.get("free_threshold", 0.196)))

    gray = np.asarray(Image.open(image_path).convert("L"), dtype=np.float32)
    occ_prob = gray / 255.0 if negate else (255.0 - gray) / 255.0
    occupied = occ_prob > occupied_thresh
    free     = occ_prob < free_thresh
    unknown  = ~(occupied | free)

    grid_top = np.zeros_like(gray, dtype=np.uint8)
    grid_top[occupied] = 1
    if treat_unknown_as_occupied:
        grid_top[unknown] = 1
    grid = np.flipud(grid_top)   # row=0 → bottom (ROS convention)

    grid_map = GridMap2D(
        origin_xy=(origin_x, origin_y),
        resolution=resolution,
        yaw=origin_yaw,
        grid=grid,
    )
    return grid_map, {
        "yaml_path": yaml_path,
        "image_path": image_path,
        "resolution": resolution,
        "origin": (origin_x, origin_y, origin_yaw),
        "negate": negate,
        "occupied_thresh": occupied_thresh,
        "free_thresh": free_thresh,
    }


# ===========================================================================
# save_nav_map_png  –  把膨胀后地图 + 规划路径保存为 PNG
# ===========================================================================
def save_nav_map_png(
    grid_map: "GridMap2D",
    path_idx: list,           # A* 原始格子路径 [(i,j), ...]
    waypoints: list,           # 简化后的世界坐标路径 [(x,y), ...]
    start_xy: tuple,          # 起点世界坐标 (x, y)
    goal_xy: tuple,           # 终点世界坐标 (x, y)
    save_path: str = "nav_plan.png",
    dpi: int = 100,            # 建议使用 100 或 150，确保与 W/dpi 匹配
):
    """
    修正版：保存膨胀地图与路径。
    解决了图片尺寸翻倍和路径位置偏移的问题。
    """
    save_path = os.path.expanduser(str(save_path))
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

    # ---------- 1. 地图底图获取 ----------
    # 直接使用原始 grid，因为 load 时已经确保 row=0 是底部 (ROS 惯例)
    raw_grid = grid_map.grid 
    H, W = raw_grid.shape

    # ---------- 2. 坐标转换函数 ----------
    def grid_to_disp(i, j):
        """(row, col) -> (x, y) 用于 matplotlib 绘图"""
        # 使用 origin="lower" 后，y 直接对应行索引 i，x 对应列索引 j
        return float(j), float(i)

    def world_to_disp(wx, wy):
        """世界坐标 (m) -> 显示像素坐标"""
        i, j = grid_map.world_to_grid(wx, wy)
        return grid_to_disp(i, j)

    if _MPL_AVAILABLE:
        # ---- 修正 1: 移除 * 2，确保尺寸 1:1 ----
        fig_w, fig_h = W / dpi, H / dpi
        # 增加极小边距或不使用 tight_layout 以保证像素精确对齐
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)

        # ---- 修正 2: 使用 origin="lower" 匹配 ROS 坐标系 ----
        ax.imshow(raw_grid, cmap="gray_r", origin="lower",
                  extent=[0, W, 0, H], interpolation="nearest", vmin=0, vmax=1)

        # 绘制 A* 原始路径（蓝色细线）
        if path_idx:
            px = [grid_to_disp(i, j)[0] for i, j in path_idx]
            py = [grid_to_disp(i, j)[1] for i, j in path_idx]
            ax.plot(px, py, color="#3399FF", linewidth=1.0, alpha=0.8, label="A* raw path", zorder=2)

        # 绘制 Waypoints（橙色粗线 + 点）
        if waypoints:
            wx_list = [world_to_disp(x, y)[0] for x, y in waypoints]
            wy_list = [world_to_disp(x, y)[1] for x, y in waypoints]
            ax.plot(wx_list, wy_list, color="#FF7700", linewidth=2.5,
                    marker="o", markersize=4, label="Waypoints", zorder=3)

        # 起点 (绿色) 和 终点 (红色)
        sx, sy = world_to_disp(*start_xy)
        ax.plot(sx, sy, "o", color="#00CC44", markersize=10, markeredgecolor="white", label="Start", zorder=5)
        
        gx, gy = world_to_disp(*goal_xy)
        ax.plot(gx, gy, "*", color="#EE2222", markersize=14, markeredgecolor="white", label="Goal", zorder=5)

        # ---- 修正 3: 精确的世界坐标刻度映射 ----
        res = grid_map.resolution
        ox, oy = grid_map.origin_xy
        
        # X 轴刻度
        x_ticks = np.linspace(0, W, 10)
        ax.set_xticks(x_ticks)
        ax.set_xticklabels([f"{ox + t * res:.1f}" for t in x_ticks], fontsize=7)
        
        # Y 轴刻度 (因为是 origin="lower"，y_tick 直接对应 i)
        y_ticks = np.linspace(0, H, 10)
        ax.set_yticks(y_ticks)
        ax.set_yticklabels([f"{oy + t * res:.1f}" for t in y_ticks], fontsize=7)

        ax.set_xlabel("World X (m)", fontsize=8)
        ax.set_ylabel("World Y (m)", fontsize=8)
        ax.set_title(f"Nav Plan: {W}x{H} (res={res}m)", fontsize=9)
        ax.legend(loc="upper right", fontsize=7)
        
        # 强制限制显示范围，防止路径溢出导致自动缩放
        ax.set_xlim(0, W)
        ax.set_ylim(0, H)

        # 保存图片，不推荐使用 bbox_inches="tight" 以免微调尺寸，
        # 但如果需要显示标签，可以使用，确保 dpi 一致即可。
        plt.savefig(save_path, dpi=dpi)
        plt.close(fig)

    else:
        # PIL 回退方案 (同样应用 origin 修正)
        img_arr = ((1 - np.flipud(raw_grid)) * 255).astype(np.uint8) # PIL绘图需转回Top-down
        img = Image.fromarray(img_arr, mode="L").convert("RGB")
        # ... (PIL 绘图逻辑同上，需处理 Y 轴翻转)
        img.save(save_path)

    print(f"[NavMap] 修复版地图已保存至: {save_path} (尺寸: {W}x{H})")


# ===========================================================================
# AStarGridPlanner  (ported from slam_nav_multi_road.py)
# ===========================================================================
class AStarGridPlanner:
    def __init__(self, grid_map: GridMap2D, slim_map: GridMap2D = None,
                 allow_diagonal: bool = True, use_clearance_cost: bool = True,
                 clearance_safe_dist_m: float = 0.5, clearance_cost_weight: float = 6.0,
                 clearance_power: float = 2.0):
        self.map       = grid_map
        self.slim_map  = slim_map if slim_map is not None else grid_map
        self.use_clearance_cost    = use_clearance_cost
        self.clearance_safe_dist_m = clearance_safe_dist_m
        self.clearance_cost_weight = clearance_cost_weight
        self.clearance_power       = clearance_power
        self.obstacle_distance_map_m = (
            self.map.compute_obstacle_distance_map_m() if use_clearance_cost else None
        )
        if allow_diagonal:
            self.neighbors = [
                (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                (-1, -1, np.sqrt(2.0)), (-1, 1, np.sqrt(2.0)),
                (1, -1, np.sqrt(2.0)),  (1, 1, np.sqrt(2.0)),
            ]
        else:
            self.neighbors = [(-1,0,1.0),(1,0,1.0),(0,-1,1.0),(0,1,1.0)]

    def _bresenham_free(self, a, b):
        i0, j0 = a; i1, j1 = b
        di, dj = abs(i1-i0), abs(j1-j0)
        si, sj = (1 if i0 < i1 else -1), (1 if j0 < j1 else -1)
        err = di - dj; i, j = i0, j0
        while True:
            if not self.slim_map.is_free(i, j):
                return False
            if i == i1 and j == j1:
                return True
            e2 = 2 * err
            if e2 > -dj: err -= dj; i += si
            if e2 <  di: err += di; j += sj

    def _rdp_simplify(self, path_idx, epsilon_cells=3.0):
        if len(path_idx) <= 2:
            return list(path_idx)
        start = np.array(path_idx[0], dtype=float)
        end   = np.array(path_idx[-1], dtype=float)
        line  = end - start; line_len = np.linalg.norm(line)
        if line_len < 1e-6:
            return [path_idx[0], path_idx[-1]]
        line_unit = line / line_len
        max_dist, max_idx = 0.0, 0
        for k in range(1, len(path_idx)-1):
            pt   = np.array(path_idx[k], dtype=float)
            proj = np.dot(pt - start, line_unit)
            perp = float(np.linalg.norm(pt - (start + proj * line_unit)))
            if perp > max_dist:
                max_dist, max_idx = perp, k
        if max_dist > epsilon_cells:
            left  = self._rdp_simplify(path_idx[:max_idx+1], epsilon_cells)
            right = self._rdp_simplify(path_idx[max_idx:], epsilon_cells)
            return left[:-1] + right
        return [path_idx[0], path_idx[-1]]

    def _simplify_path(self, path_idx):
        if (not ASTAR_SIMPLIFY_PATH) or len(path_idx) <= 2:
            return list(path_idx)
        return self._rdp_simplify(path_idx, epsilon_cells=3.0)

    def _resample_polyline(self, pts_xy, spacing: float):
        if len(pts_xy) <= 1:
            return list(pts_xy)
        out = [pts_xy[0]]
        for k in range(len(pts_xy)-1):
            p0 = np.array(pts_xy[k],   dtype=np.float64)
            p1 = np.array(pts_xy[k+1], dtype=np.float64)
            seg = p1 - p0; seg_len = float(np.linalg.norm(seg))
            if seg_len < 1e-6:
                continue
            n = max(1, int(np.floor(seg_len / max(spacing, 1e-6))))
            for s in range(1, n+1):
                t = min(1.0, s * spacing / seg_len)
                q = p0 + t * seg
                if np.hypot(q[0]-out[-1][0], q[1]-out[-1][1]) >= spacing*0.7 or t >= 0.999:
                    out.append((float(q[0]), float(q[1])))
            if np.hypot(p1[0]-out[-1][0], p1[1]-out[-1][1]) > 1e-6:
                out.append((float(p1[0]), float(p1[1])))
        return out

    def _inject_corner_points(self, pts_xy):
        if len(pts_xy) <= 2:
            return list(pts_xy)
        out = [pts_xy[0]]
        turn_thresh    = np.deg2rad(ASTAR_CORNER_ANGLE_DEG)
        corner_spacing = float(ASTAR_CORNER_INSERT_SPACING)
        for k in range(1, len(pts_xy)-1):
            p_prev = np.array(pts_xy[k-1], dtype=np.float64)
            p      = np.array(pts_xy[k],   dtype=np.float64)
            p_next = np.array(pts_xy[k+1], dtype=np.float64)
            v_in  = p - p_prev; nin  = float(np.linalg.norm(v_in))
            v_out = p_next - p; nout = float(np.linalg.norm(v_out))
            if nin < 1e-6 or nout < 1e-6:
                out.append((float(p[0]), float(p[1]))); continue
            vin  = v_in / nin; vout = v_out / nout
            ang  = float(np.arccos(np.clip(np.dot(vin, vout), -1.0, 1.0)))
            if ang > turn_thresh:
                d_in  = min(corner_spacing, nin  * 0.45)
                d_out = min(corner_spacing, nout * 0.45)
                q1 = p - vin  * d_in
                q2 = p + vout * d_out
                if np.hypot(q1[0]-out[-1][0], q1[1]-out[-1][1]) > 1e-4:
                    out.append((float(q1[0]), float(q1[1])))
                out.append((float(p[0]), float(p[1])))
                if np.hypot(q2[0]-out[-1][0], q2[1]-out[-1][1]) > 1e-4:
                    out.append((float(q2[0]), float(q2[1])))
            else:
                out.append((float(p[0]), float(p[1])))
        if np.hypot(pts_xy[-1][0]-out[-1][0], pts_xy[-1][1]-out[-1][1]) > 1e-4:
            out.append(pts_xy[-1])
        return out

    def _indices_to_waypoints(self, path_idx, exact_goal_xy=None, min_spacing: float = 0.35):
        path_idx = self._simplify_path(path_idx)
        pts_xy   = [self.map.grid_to_world(i, j) for i, j in path_idx]
        pts_xy   = self._inject_corner_points(pts_xy)
        pts_xy   = self._resample_polyline(pts_xy, spacing=float(ASTAR_WAYPOINT_DENSIFY_SPACING))
        waypoints = []; last_xy = None
        for xy in pts_xy:
            if last_xy is None or np.hypot(xy[0]-last_xy[0], xy[1]-last_xy[1]) >= min(
                    min_spacing, ASTAR_WAYPOINT_DENSIFY_SPACING * 0.95):
                waypoints.append((float(xy[0]), float(xy[1]))); last_xy = xy
        if exact_goal_xy is not None:
            if not waypoints or np.hypot(exact_goal_xy[0]-waypoints[-1][0],
                                         exact_goal_xy[1]-waypoints[-1][1]) > 0.03:
                if not waypoints:
                    waypoints.append((float(exact_goal_xy[0]), float(exact_goal_xy[1])))
                else:
                    waypoints[-1] = (float(exact_goal_xy[0]), float(exact_goal_xy[1]))
        return waypoints

    def plan_world(self, start_xy, goal_xy, min_waypoint_spacing: float = 0.35):
        start_ij   = self.map.world_to_grid(start_xy[0], start_xy[1])
        goal_ij    = self.map.world_to_grid(goal_xy[0],  goal_xy[1])
        start_free = self.map.nearest_free_cell(*start_ij)
        goal_free  = self.map.nearest_free_cell(*goal_ij)
        if start_free is None:
            raise RuntimeError(f"Planner start {start_xy} is not near a free cell.")
        if goal_free is None:
            raise RuntimeError(f"Planner goal {goal_xy} is not near a free cell.")

        H, W = self.map.height, self.map.width
        si, sj = start_free
        gi, gj = goal_free
        INF      = np.float32(1e18)
        g_score  = np.full(H * W, INF, dtype=np.float32)
        parent   = np.full(H * W, -1,  dtype=np.int32)
        closed   = np.zeros(H * W, dtype=bool)
        start_idx = si * W + sj
        goal_idx  = gi * W + gj
        g_score[start_idx] = 0.0
        open_heap = [(float(np.hypot(si-gi, sj-gj)), start_idx)]

        if self.use_clearance_cost and self.obstacle_distance_map_m is not None:
            dist_flat = self.obstacle_distance_map_m.ravel()
            cs, cw, cp = self.clearance_safe_dist_m, self.clearance_cost_weight, self.clearance_power
            ratio        = np.clip((cs - dist_flat) / max(cs, 1e-6), 0.0, 1.0)
            penalty_flat = (cw * ratio ** cp).astype(np.float32)
        else:
            penalty_flat = None

        grid_flat        = self.map.grid.ravel()
        neighbor_offsets = [(di * W + dj, np.float32(sc), di, dj)
                            for di, dj, sc in self.neighbors]

        found = False
        while open_heap:
            _, cur_idx = heapq.heappop(open_heap)
            if closed[cur_idx]:
                continue
            if cur_idx == goal_idx:
                found = True; break
            closed[cur_idx] = True
            ci, cj = divmod(int(cur_idx), W)
            g_cur  = g_score[cur_idx]
            for flat_off, step_cost, di, dj in neighbor_offsets:
                ni, nj = ci + di, cj + dj
                if ni < 0 or ni >= H or nj < 0 or nj >= W:
                    continue
                nxt_idx = int(cur_idx) + flat_off
                if grid_flat[nxt_idx] != 0:
                    continue
                if di != 0 and dj != 0:
                    if grid_flat[ci*W+(cj+dj)] != 0 or grid_flat[(ci+di)*W+cj] != 0:
                        continue
                pen       = penalty_flat[nxt_idx] if penalty_flat is not None else 0.0
                tentative = g_cur + step_cost + pen
                if tentative < g_score[nxt_idx]:
                    g_score[nxt_idx] = tentative
                    parent[nxt_idx]  = cur_idx
                    h = float(np.hypot(ni-gi, nj-gj))
                    heapq.heappush(open_heap, (float(tentative)+h, nxt_idx))

        if not found:
            raise RuntimeError("A* failed: no path found on current occupancy grid.")

        path_idx = []
        cur = goal_idx
        while cur != start_idx:
            ci, cj = divmod(int(cur), W)
            path_idx.append((ci, cj))
            cur = int(parent[cur])
            if cur == -1:
                raise RuntimeError("A* path reconstruction failed.")
        path_idx.append((si, sj)); path_idx.reverse()

        waypoints = self._indices_to_waypoints(path_idx, exact_goal_xy=goal_xy,
                                               min_spacing=min_waypoint_spacing)
        return path_idx, waypoints, {
            "start_ij": start_free, "goal_ij": goal_free,
            "expanded": int(np.sum(closed)), "path_cells": len(path_idx),
        }


# ===========================================================================
# WaypointFollower  (ported from slam_nav_multi_road.py)
# ===========================================================================
def wrap_to_pi(angle: float) -> float:
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


class WaypointFollower:
    def __init__(self):
        self.waypoints: list = []
        self.index: int = 0
        self.active: bool = False
        self._step_counter    = 0
        self._last_debug_index= -1
        self.last_debug: dict = {}
        self._stuck_ref_dist  = None
        self._stuck_counter   = 0
        self._frozen_ref_pos  = None
        self._frozen_counter  = 0

    def load_path(self, waypoints):
        self.waypoints = [np.array([float(x), float(y)], dtype=np.float32)
                          for x, y in waypoints]
        self.index = 0
        self.active = len(self.waypoints) > 0
        self._step_counter     = 0
        self._last_debug_index = -1
        self.last_debug        = {}
        self._stuck_ref_dist   = None
        self._stuck_counter    = 0
        self._frozen_ref_pos   = None
        self._frozen_counter   = 0
        if self.active:
            print(f"[AutoDbg] loaded {len(self.waypoints)} waypoints. "
                  f"first=({self.waypoints[0][0]:.3f}, {self.waypoints[0][1]:.3f})")

    def stop(self):
        self.waypoints = []; self.index = 0; self.active = False
        self._step_counter = 0; self._last_debug_index = -1; self.last_debug = {}
        self._stuck_ref_dist = None; self._stuck_counter = 0
        self._frozen_ref_pos = None; self._frozen_counter = 0

    def _corner_angle_deg_at(self, ep_idx: int) -> float:
        if ep_idx <= 0 or ep_idx >= len(self.waypoints)-1:
            return 0.0
        v_in  = self.waypoints[ep_idx]   - self.waypoints[ep_idx-1]
        v_out = self.waypoints[ep_idx+1] - self.waypoints[ep_idx]
        n1, n2 = float(np.linalg.norm(v_in)), float(np.linalg.norm(v_out))
        if n1 < 1e-6 or n2 < 1e-6:
            return 0.0
        return float(np.degrees(np.arccos(np.clip(
            np.dot(v_in/n1, v_out/n2), -1.0, 1.0))))

    def _is_corner_endpoint(self, ep_idx: int) -> bool:
        return self._corner_angle_deg_at(ep_idx) > AUTO_CORNER_ANGLE_DEG

    def _emit_debug(self, force=False):
        self._step_counter += 1
        if not self.last_debug:
            return
        if (not force) and (self._step_counter % AUTO_DEBUG_PRINT_EVERY_STEPS != 0):
            return
        d = self.last_debug
        print(f"[AutoDbg] idx={d['index']+1}/{d['total']} mode={d['mode']} "
              f"pos=({d['x']:.3f},{d['y']:.3f}) yaw={np.degrees(d['yaw']):.1f}° "
              f"goal=({d['goal_x']:.3f},{d['goal_y']:.3f}) dist={d['dist']:.3f} "
              f"cmd=({d['vx']:.3f},{d['vy']:.3f},{d['wz']:.3f}) "
              f"stuck={d['stuck_counter']} corner={d['is_corner']} cte={d['cte']:.3f}")

    def _build_segment_state(self, x: float, y: float):
        endpoint = self.waypoints[self.index]
        p0 = np.array([x, y], dtype=np.float32) if self.index == 0 \
             else self.waypoints[self.index-1]
        p1  = endpoint
        seg = p1 - p0; seg_len = float(np.linalg.norm(seg))
        pos = np.array([x, y], dtype=np.float32)
        if seg_len < 1e-6:
            return dict(p0=p0, p1=p1, seg_len=seg_len,
                        seg_dir=np.array([1.,0.], dtype=np.float32),
                        closest=p1, look_pt=p1,
                        dist_to_end=float(np.linalg.norm(pos-p1)),
                        along_remain=0., cte=0., seg_heading=0.)
        seg_dir = seg / seg_len
        rel     = pos - p0
        s       = float(np.dot(rel, seg_dir))
        s_cl    = float(np.clip(s, 0.0, seg_len))
        closest = p0 + s_cl * seg_dir
        cross   = float(seg_dir[0]*rel[1] - seg_dir[1]*rel[0])
        look_s  = min(seg_len, s_cl + AUTO_SEGMENT_LOOKAHEAD)
        look_pt = p0 + look_s * seg_dir
        return dict(p0=p0, p1=p1, seg_len=seg_len, seg_dir=seg_dir,
                    closest=closest, look_pt=look_pt,
                    dist_to_end=float(np.linalg.norm(pos-p1)),
                    along_remain=float(max(0., seg_len-s_cl)),
                    cte=cross, seg_heading=float(np.arctan2(seg_dir[1], seg_dir[0])))

    def compute_command(self, x: float, y: float, yaw: float):
        """Returns ([vx, vy, wz], done)."""
        if not self.active or self.index >= len(self.waypoints):
            self.stop(); return [0., 0., 0.], True

        goal         = self.waypoints[self.index]
        is_corner    = self._is_corner_endpoint(self.index)
        corner_ang   = self._corner_angle_deg_at(self.index)
        reach_tol    = AUTO_CORNER_REACH_TOL if is_corner else AUTO_REACH_TOL

        state        = self._build_segment_state(x, y)
        dist         = state['dist_to_end']
        along_remain = state['along_remain']
        cte          = state['cte']
        seg_heading  = state['seg_heading']

        # --- 1. Frozen & Stuck 检测 (保持原逻辑) ---
        FROZEN_EPS, FROZEN_STEPS = 0.02, 300
        if self._frozen_ref_pos is None:
            self._frozen_ref_pos = (x, y); self._frozen_counter = 0
        else:
            moved = np.hypot(x-self._frozen_ref_pos[0], y-self._frozen_ref_pos[1])
            if moved < FROZEN_EPS:
                self._frozen_counter += 1
                if self._frozen_counter >= FROZEN_STEPS:
                    self.index += 1
                    self._frozen_ref_pos = None; self._frozen_counter = 0
                    if self.index >= len(self.waypoints):
                        self.stop(); return [0., 0., 0.], True
                    return self.compute_command(x, y, yaw)
            else:
                self._frozen_ref_pos = (x, y); self._frozen_counter = 0

        # --- 2. 拐角处理: 先原地对准下一段路径 ---
        if is_corner and dist <= AUTO_CORNER_REACH_TOL:
            next_dir    = self.waypoints[self.index+1] - self.waypoints[self.index]
            next_yaw    = float(np.arctan2(next_dir[1], next_dir[0]))
            next_yaw_err= wrap_to_pi(next_yaw - yaw)
            if abs(next_yaw_err) > AUTO_CORNER_TURN_ONLY_YAW:
                wz = float(np.clip(AUTO_KP_YAW * next_yaw_err, -AUTO_MAX_WZ, AUTO_MAX_WZ))
                self.last_debug = dict(
                    index=self.index, total=len(self.waypoints),
                    vx=0., vy=0., wz=wz, mode=f'CORNER_TURN({corner_ang:.0f}deg)',
                    dist=float(dist), yaw_err=float(next_yaw_err), cte=float(cte))
                return [0., 0., wz], False

        # --- 3. 到达判定 ---
        if dist <= reach_tol or (along_remain <= AUTO_SEGMENT_END_SWITCH_DIST and dist <= max(reach_tol, 0.30)):
            self.index += 1
            if self.index >= len(self.waypoints):
                self.stop(); return [0., 0., 0.], True
            return self.compute_command(x, y, yaw)

        # --- 4. 核心控制逻辑 (VX, VY, WZ 联动) ---

        # [航向计算]
        desired_heading = seg_heading - float(np.arctan2(AUTO_CTE_GAIN * cte, max(0.25, AUTO_MAX_VX)))
        yaw_err = wrap_to_pi(desired_heading - yaw)

        # [角速度 WZ]
        wz = float(np.clip(AUTO_KP_YAW * yaw_err, -AUTO_MAX_WZ, AUTO_MAX_WZ))

        # [横移速度 VY]
        vy = float(np.clip(-1.2 * cte, -1.0, 1.0))

        # [线速度 VX]
        slow_scale = min(1.0, max(along_remain, dist) / AUTO_SLOWDOWN_RADIUS)
        vx_base = float(np.clip(AUTO_KP_FWD * max(along_remain, dist), 0., AUTO_MAX_VX) * slow_scale)

        # 边转边走逻辑：vx 随角度偏差余弦缩放
        v_yaw_scale = max(0.0, np.cos(yaw_err))

        if abs(yaw_err) > AUTO_ROTATE_IN_PLACE_YAW:
            vx = vx_base * 0.5  # 大角度转弯时保留10%的前进动力
            mode = 'BIG_TURN_MOVE'
        else:
            vx = vx_base * v_yaw_scale
            if abs(yaw_err) > AUTO_ALLOW_FWD_YAW:
                vx *= 0.6
                mode = 'SEG_SLOW_TURN'
            else:
                vx = max(vx, AUTO_MIN_CRUISE_VX)
                mode = 'SEG_CRUISE'

        # [特殊修正]
        if is_corner and dist < AUTO_CORNER_SLOWDOWN_DIST:
            vx = min(vx * AUTO_CORNER_SLOWDOWN_SCALE, AUTO_CORNER_APPROACH_VX)
            mode = f'CORNER_APPROACH({corner_ang:.0f}deg)'

        if dist < AUTO_MIN_FWD_DIST:
            vx = 0.; vy = 0.; mode = 'NEAR_GOAL' # 临近终点关闭平移，防止抖动

        # --- 5. 调试与返回 ---
        self.last_debug = dict(
            index=self.index, total=len(self.waypoints),
            x=float(x), y=float(y), yaw=float(yaw),
            goal_x=float(goal[0]), goal_y=float(goal[1]), dist=float(dist),
            target_yaw=float(desired_heading), yaw_err=float(yaw_err),
            vx=float(vx), vy=float(vy), wz=float(wz), mode=mode,
            stuck_counter=self._stuck_counter, is_corner=is_corner, cte=float(cte))
        self._emit_debug(force=(self.index != self._last_debug_index))
        self._last_debug_index = self.index

        return [float(vx), float(vy), float(wz)], False


# ===========================================================================
# HybridCmdVelSource  – keyboard teleop + A* path follower, non-conflicting
# ===========================================================================
class HybridCmdVelSource:
    """
    Velocity command source that combines:
      • Keyboard manual control (arrow keys, N/M for yaw)
      • A* autonomous navigation from a YAML occupancy map

    Both modes are always active – keyboard temporarily overrides auto.
    After MANUAL_TIMEOUT_S of no key activity the follower resumes.

    Keyboard bindings (active when --nav is passed):
      ↑ / ↓          forward / backward
      ← / →          strafe left / right
      N / M           yaw left / right
      Space / C       stop + cancel auto mode
      K               A* plan to goal → start auto immediately
      G               A* plan to goal (don't start auto)
      P               start auto with last loaded path
      R               re-plan and start with current robot pose
    """
    MANUAL_TIMEOUT_S = 0.5   # seconds after last keypress before auto resumes

    def __init__(self, map_yaml: str, goal_xy: tuple,
                 inflation_radius: float = 0.4,
                 hard_inflation_radius: float = 0.35,
                 linear_speed: float = KB_LINEAR_SPEED,
                 yaw_speed: float = KB_YAW_SPEED,
                 max_lin_x: float = 2.0,
                 max_lin_y: float = 1.0,
                 max_ang_z: float = 1.5):
        self._map_yaml              = map_yaml
        self._goal_xy               = goal_xy        # (x, y) world coord
        self._inflation_radius      = inflation_radius       # 软膨胀：代价惩罚层
        self._hard_inflation_radius = hard_inflation_radius  # 硬膨胀：机器人物理半径
        self._linear_speed          = linear_speed
        self._yaw_speed             = yaw_speed
        self._max_lin_x             = max_lin_x
        self._max_lin_y             = max_lin_y
        self._max_ang_z             = max_ang_z

        # Keyboard state
        self._vx: float = 0.0
        self._vy: float = 0.0
        self._wz: float = 0.0
        self._last_key_time: float = 0.0

        # Request flags (set by keyboard callbacks, consumed by main loop)
        self.request_plan_and_start: bool = False
        self.request_plan_only:      bool = False
        self.request_start_auto:     bool = False
        self.request_cancel:         bool = False
        # ★ 新增：回家 & 多路径巡游请求标志
        self.request_go_home:        bool = False
        self.request_multi_path:     bool = False
        self.request_teleport_home:  bool = False  # tick_multi 触发，主循环执行传送

        # Path follower
        self._follower   = WaypointFollower()
        self._auto_mode  = False
        self._waypoints  = []

        # ★ 多路径巡游状态
        self._multi_active:    bool  = False
        self._multi_paths:     list  = []
        self._multi_path_idx:  int   = 0
        self._multi_home_xy:   tuple = (0.0, 0.0)
        self._returning_home:  bool  = False
        self._next_path_idx:   int   = 0

        # Planner cache
        self._grid:      Optional[GridMap2D] = None
        self._slim_grid: Optional[GridMap2D] = None
        self._cache_key  = None

        # Carb keyboard subscription (installed in start())
        self._input = carb.input.acquire_input_interface()
        self._kb_sub = None

    # ------------------------------------------------------------------
    def start(self):
        """Subscribe to keyboard events. Call after AppLauncher is up."""
        try:
            kb = omni.appwindow.get_default_app_window().get_keyboard()
            self._kb_sub = self._input.subscribe_to_keyboard_events(kb, self._on_key)
            print("[HybridNav] Keyboard subscribed (GUI).")
            print("[HybridNav] Keys: ↑↓←→ move | N/M yaw | K plan+start | G plan | P start | Space/C cancel | R home | T multi-path")
            self._terminal_thread = None
        except Exception:
            # Headless or no app window: fall back to terminal keyboard reader
            print("[HybridNav] GUI keyboard unavailable — falling back to terminal input.")
            self._kb_sub = None
            self._start_terminal_keyboard()
        # If the app was launched with a headless flag, ensure terminal fallback
        try:
            if getattr(args_cli, 'headless', False):
                if getattr(self, '_terminal_thread', None) is None:
                    print('[HybridNav] args_cli.headless detected — starting terminal input fallback.')
                    self._start_terminal_keyboard()
        except Exception:
            pass

    def stop(self):
        self._kb_sub = None
        self._follower.stop()
        self._auto_mode = False
        # stop terminal reader if active
        try:
            self._stop_terminal_keyboard()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _start_terminal_keyboard(self):
        """Start a background thread that reads stdin for key presses (headless fallback)."""
        if getattr(self, "_terminal_thread", None):
            return
        self._terminal_running = True
        self._terminal_thread = threading.Thread(target=self._terminal_reader_loop, daemon=True)
        # save terminal state
        try:
            self._orig_term_attrs = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        except Exception:
            self._orig_term_attrs = None
        self._terminal_thread.start()

    def _stop_terminal_keyboard(self):
        if not getattr(self, "_terminal_thread", None):
            return
        self._terminal_running = False
        self._terminal_thread.join(timeout=1.0)
        self._terminal_thread = None
        if getattr(self, "_orig_term_attrs", None) is not None:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._orig_term_attrs)
            except Exception:
                pass

    def _terminal_reader_loop(self):
        """Read key sequences from stdin and map to the same actions as GUI keys."""
        while getattr(self, "_terminal_running", False):
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not r:
                    continue
                data = os.read(sys.stdin.fileno(), 8)
                if not data:
                    continue
                try:
                    s = data.decode(errors="ignore")
                except Exception:
                    s = ""
                # Arrow keys are escape sequences: \x1b[A, \x1b[B, \x1b[C, \x1b[D
                if s.startswith("\x1b"):
                    if s.startswith("\x1b[A"):
                        # up
                        self._vx = +self._linear_speed
                        self._last_key_time = time.time()
                    elif s.startswith("\x1b[B"):
                        self._vx = -self._linear_speed
                        self._last_key_time = time.time()
                    elif s.startswith("\x1b[C"):
                        self._vy = -self._linear_speed
                        self._last_key_time = time.time()
                    elif s.startswith("\x1b[D"):
                        self._vy = +self._linear_speed
                        self._last_key_time = time.time()
                else:
                    ch = s.strip().lower()
                    if not ch:
                        continue
                    for c in ch:
                        if c == "n":
                            self._wz = +self._yaw_speed
                            self._last_key_time = time.time()
                        elif c == "m":
                            self._wz = -self._yaw_speed
                            self._last_key_time = time.time()
                        elif c == " ":
                            self._vx = self._vy = self._wz = 0.0
                            self.request_cancel = True
                        elif c == "c":
                            self.request_cancel = True
                            print("[HybridNav] Cancel auto requested (c).")
                        elif c == "k":
                            self.request_plan_and_start = True
                            print("[HybridNav] Plan + start requested (k).")
                        elif c == "g":
                            self.request_plan_only = True
                            print("[HybridNav] Plan only requested (g).")
                        elif c == "p":
                            self.request_start_auto = True
                            print("[HybridNav] Start auto requested (p).")
                        elif c == "r":
                            self.request_go_home = True
                            print("[HybridNav] Return to home requested (r).")
                        elif c == "t":
                            self.request_multi_path = True
                            print("[HybridNav] Multi-path mode requested (t).")
                        elif c == "s":
                            # stop motion
                            self._vx = self._vy = self._wz = 0.0
                            self._last_key_time = time.time()
            except Exception:
                # ignore errors and keep loop alive
                time.sleep(0.05)

    # ------------------------------------------------------------------
    def _on_key(self, event):
        pressed  = event.type in (KeyboardEventType.KEY_PRESS, KeyboardEventType.KEY_REPEAT)
        released = event.type == KeyboardEventType.KEY_RELEASE

        motion_keys = {KeyboardInput.UP, KeyboardInput.DOWN,
                       KeyboardInput.LEFT, KeyboardInput.RIGHT,
                       KeyboardInput.N, KeyboardInput.M}

        def axis(name, value):
            if pressed:
                setattr(self, name, value)
                self._last_key_time = time.time()
            elif released:
                setattr(self, name, 0.0)

        if event.input == KeyboardInput.UP:
            axis("_vx", +self._linear_speed)
        elif event.input == KeyboardInput.DOWN:
            axis("_vx", -self._linear_speed)
        elif event.input == KeyboardInput.LEFT:
            axis("_vy", +self._linear_speed)
        elif event.input == KeyboardInput.RIGHT:
            axis("_vy", -self._linear_speed)
        elif event.input == KeyboardInput.N:
            axis("_wz", +self._yaw_speed)
        elif event.input == KeyboardInput.M:
            axis("_wz", -self._yaw_speed)
        elif event.input == KeyboardInput.SPACE and pressed:
            self._vx = self._vy = self._wz = 0.0
            self.request_cancel = True
        elif event.input == KeyboardInput.C and pressed:
            self.request_cancel = True
            print("[HybridNav] Cancel auto requested (C).")
        elif event.input == KeyboardInput.K and pressed:
            self.request_plan_and_start = True
            print("[HybridNav] Plan + start requested (K).")
        elif event.input == KeyboardInput.G and pressed:
            self.request_plan_only = True
            print("[HybridNav] Plan only requested (G).")
        elif event.input == KeyboardInput.P and pressed:
            self.request_start_auto = True
            print("[HybridNav] Start auto requested (P).")
        elif event.input == KeyboardInput.R and pressed:
            self.request_go_home = True
            print("[HybridNav] Return to home requested (R).")
        elif event.input == KeyboardInput.T and pressed:
            self.request_multi_path = True
            print("[HybridNav] Multi-path mode requested (T).")

        # Any motion key → temporarily override auto mode
        if event.input in motion_keys and pressed:
            self._last_key_time = time.time()

        return True

    # ------------------------------------------------------------------
    def _is_keyboard_active(self) -> bool:
        """True if a key was pressed recently enough to override auto."""
        return (time.time() - self._last_key_time) < self.MANUAL_TIMEOUT_S

    # ------------------------------------------------------------------
    def _load_planner_grid(self):
        """双层膨胀地图加载。
        - hard_map  : 硬膨胀（机器人物理半径），A* 完全不能通过
        - slim_map  : 用于 Bresenham 视线检测（hard 的 60%）
        - 软膨胀代价: 通过 clearance cost 体现在 A* 代价函数中（用 soft_inflation_radius）
        """
        import copy
        key = (self._map_yaml, OCC_MAP_TREAT_UNKNOWN_AS_OCCUPIED,
               GRID_RESOLUTION, self._inflation_radius, self._hard_inflation_radius)
        if self._grid is not None and self._cache_key == key:
            return self._grid, self._slim_grid

        print(f"[HybridNav] Loading occupancy map: {self._map_yaml}")
        print(f"[HybridNav] Dual-layer inflation: hard={self._hard_inflation_radius:.2f}m  "
              f"soft={self._inflation_radius:.2f}m")

        raw_grid, _ = load_ros_occupancy_map(
            yaml_path=self._map_yaml,
            treat_unknown_as_occupied=OCC_MAP_TREAT_UNKNOWN_AS_OCCUPIED,
        )
        if GRID_RESOLUTION is not None:
            from slam_nav_multi_road import resample_grid_map_nearest
            raw_grid = resample_grid_map_nearest(raw_grid, GRID_RESOLUTION)

        # ── 硬膨胀地图：A* 可行性判断（机器人物理半径，完全不可通行）──────────
        hard_grid = copy.deepcopy(raw_grid)
        if self._hard_inflation_radius > 0.0:
            hard_grid.inflate(self._hard_inflation_radius)
            print(f"[HybridNav] Hard map inflated={self._hard_inflation_radius:.2f}m  "
                  f"shape={hard_grid.shape}")

        # ── Slim 地图：Bresenham 视线检测（硬膨胀的 60%，更严格）──────────────
        slim_grid = copy.deepcopy(raw_grid)
        slim_infl = self._hard_inflation_radius * 0.6
        if slim_infl > 0.0:
            slim_grid.inflate(slim_infl)

        # ── 软膨胀地图：仅用于 A* clearance cost 距离变换 ─────────────────────
        # clearance cost 是基于 hard_grid 的距离变换来计算的
        # soft_inflation_radius 决定惩罚的影响范围（通过 ASTAR_CLEARANCE_SAFE_DIST 控制）
        # 这里我们用 soft_inflation_radius 覆盖 ASTAR_CLEARANCE_SAFE_DIST
        # 让软膨胀区域在代价上体现，但不在可行性上体现
        self._soft_clearance_dist = max(self._inflation_radius, self._hard_inflation_radius)

        hard_grid._inflation_radius_used = (
            f"hard={self._hard_inflation_radius:.2f}m / soft={self._inflation_radius:.2f}m"
        )

        self._grid      = hard_grid
        self._slim_grid = slim_grid
        self._cache_key = key
        return hard_grid, slim_grid

    # ------------------------------------------------------------------
    def do_plan(self, robot_x: float, robot_y: float) -> bool:
        """Run A* from (robot_x, robot_y) to self._goal_xy.
        Returns True on success."""
        try:
            grid, slim_grid = self._load_planner_grid()
        except Exception as e:
            print(f"[HybridNav] Map load failed: {e}")
            return False

        start_xy = (robot_x, robot_y)
        goal_xy  = self._goal_xy
        print(f"[HybridNav] Planning: start=({robot_x:.2f},{robot_y:.2f}) "
              f"goal=({goal_xy[0]:.2f},{goal_xy[1]:.2f})")
        try:
            planner = AStarGridPlanner(
                grid_map=grid, slim_map=slim_grid,
                allow_diagonal=ASTAR_ALLOW_DIAGONAL,
                use_clearance_cost=ASTAR_USE_CLEARANCE_COST,
                clearance_safe_dist_m=getattr(self, '_soft_clearance_dist', ASTAR_CLEARANCE_SAFE_DIST),
                clearance_cost_weight=ASTAR_CLEARANCE_COST_WEIGHT,
                clearance_power=ASTAR_CLEARANCE_POWER,
            )
            path_idx, waypoints, meta = planner.plan_world(
                start_xy=start_xy,
                goal_xy=goal_xy,
                min_waypoint_spacing=ASTAR_MIN_WAYPOINT_SPACING,
            )
        except Exception as e:
            print(f"[HybridNav] A* failed: {e}")
            return False

        # Drop first waypoint if it's practically at start
        if waypoints and np.hypot(waypoints[0][0]-robot_x,
                                  waypoints[0][1]-robot_y) < max(AUTO_REACH_TOL, 0.15):
            waypoints = waypoints[1:]
        if not waypoints:
            waypoints = [goal_xy]

        self._waypoints = list(waypoints)
        print(f"[HybridNav] Plan OK: {meta['path_cells']} cells → "
              f"{len(waypoints)} waypoints. "
              f"First=({waypoints[0][0]:.2f},{waypoints[0][1]:.2f})")

        # ---- 保存膨胀地图 + 规划路径到 PNG ----------------------------------
        try:
            map_dir   = os.path.dirname(os.path.abspath(self._map_yaml))
            png_path  = os.path.join(map_dir, "nav_plan.png")
            save_nav_map_png(
                grid_map  = grid,
                path_idx  = path_idx,
                waypoints = waypoints,
                start_xy  = start_xy,
                goal_xy   = goal_xy,
                save_path = png_path,
            )
        except Exception as _e:
            print(f"[NavMap] PNG 保存失败（不影响导航）: {_e}")
        # ---------------------------------------------------------------------

        return True

    def start_auto(self):
        if not self._waypoints:
            print("[HybridNav] No waypoints – press K to plan first.")
            return
        self._follower.load_path(self._waypoints)
        self._auto_mode = self._follower.active
        print(f"[HybridNav] Auto mode started, {len(self._waypoints)} waypoints.")

    def cancel_auto(self):
        self._follower.stop()
        self._auto_mode = False
        self._multi_active = False
        self._returning_home = False
        self._vx = self._vy = self._wz = 0.0
        print("[HybridNav] Auto mode cancelled.")

    def set_goal(self, goal_xy: tuple):
        """Update navigation goal (x, y)."""
        self._goal_xy = goal_xy
        print(f"[HybridNav] Goal updated to ({goal_xy[0]:.2f}, {goal_xy[1]:.2f})")

    # ==================================================================
    # ★ 功能三：R 键 — 取消导航，通知主循环执行全状态重置传送
    # ==================================================================
    def go_home(self):
        """停止一切导航，主循环会执行实际传送（需要访问 env）。"""
        self.cancel_auto()
        # request_go_home 已在主循环消费，此处仅清理导航状态

    # ==================================================================
    # ★ 功能二：T 键 — 多路径巡游（传送版）
    # ==================================================================
    def plan_multi_paths(self, start_x: float, start_y: float,
                         home_xy: tuple,
                         n_paths: int = 5,
                         perturb_m: float = 3.0) -> bool:
        """从 home 位置出发，规划 n_paths 条随机扰动路径。
        每条走完后由主循环传送回 home，再走下一条。
        所有路径均从 (start_x, start_y) = home 预先规划。
        """
        import random
        self._multi_paths      = []
        self._multi_home_xy    = home_xy
        self._multi_path_idx   = 0
        self._multi_active     = False
        self._returning_home   = False
        self.request_teleport_home = False

        goal_x, goal_y = self._goal_xy

        for k in range(n_paths):
            if k == 0:
                gx, gy = goal_x, goal_y
            else:
                angle = random.uniform(0, 2 * np.pi)
                dist  = random.uniform(0.5, perturb_m)
                gx    = goal_x + dist * np.cos(angle)
                gy    = goal_y + dist * np.sin(angle)

            ok = self._do_plan_to(start_x, start_y, gx, gy)
            if not ok:
                print(f"[MultiPath] Path {k+1}/{n_paths} planning failed → skipping.")
                continue
            self._multi_paths.append((list(self._waypoints), (gx, gy)))
            print(f"[MultiPath] Path {k+1}/{n_paths} → goal=({gx:.2f},{gy:.2f})  "
                  f"{len(self._waypoints)} waypoints")

        if not self._multi_paths:
            print("[MultiPath] No valid paths generated.")
            return False

        print(f"[MultiPath] {len(self._multi_paths)}/{n_paths} paths ready. Starting path 1.")
        self._multi_active = True
        self._start_multi_path(0)
        return True

    def _do_plan_to(self, sx: float, sy: float, gx: float, gy: float) -> bool:
        saved = self._goal_xy
        self._goal_xy = (gx, gy)
        ok = self.do_plan(sx, sy)
        self._goal_xy = saved
        return ok

    def _start_multi_path(self, idx: int):
        self._multi_path_idx = idx
        waypoints, goal = self._multi_paths[idx]
        self._waypoints = list(waypoints)
        self._follower.load_path(self._waypoints)
        self._auto_mode = self._follower.active
        self._returning_home = False
        print(f"[MultiPath] ▶ Path {idx+1}/{len(self._multi_paths)}  "
              f"goal=({goal[0]:.2f},{goal[1]:.2f})  {len(waypoints)} waypoints")

    def tick_multi(self):
        """每帧调用。路径走完时设置 request_teleport_home，
        主循环传送后调用 on_teleport_done() 继续下一条。
        """
        if not self._multi_active:
            return
        if self._returning_home:  # 等主循环传送完成
            return
        if not self._auto_mode:
            idx = self._multi_path_idx
            n   = len(self._multi_paths)
            if idx < n - 1:
                print(f"[MultiPath] Path {idx+1}/{n} done → teleporting home.")
                self._returning_home       = True
                self._next_path_idx        = idx + 1
                self.request_teleport_home = True   # ★ 主循环执行传送
            else:
                print("[MultiPath] ✓ All paths completed!")
                self._multi_active = False

    def on_teleport_done(self):
        """主循环传送完成后调用，启动下一条路径。"""
        self._returning_home       = False
        self.request_teleport_home = False
        if self._multi_active and self._next_path_idx < len(self._multi_paths):
            self._start_multi_path(self._next_path_idx)
        else:
            print("[MultiPath] ✓ All paths completed after last teleport!")
            self._multi_active = False

    # ------------------------------------------------------------------
    def get_command(self, x: float, y: float, yaw: float) -> tuple[float, float, float]:
        """
        Called every env step.
        Priority: keyboard (if recently active) > path follower > zero.
        """
        if self._is_keyboard_active():
            # Clamp keyboard to policy limits
            vx = float(np.clip(self._vx, -self._max_lin_x, self._max_lin_x))
            vy = float(np.clip(self._vy, -self._max_lin_y, self._max_lin_y))
            wz = float(np.clip(self._wz, -self._max_ang_z, self._max_ang_z))
            return vx, vy, wz

        if self._auto_mode and self._follower.active:
            cmd, done = self._follower.compute_command(x, y, yaw)
            if done:
                self._auto_mode = False
                print("[HybridNav] Goal reached – auto mode stopped.")
            # Clamp auto output to policy limits
            vx = float(np.clip(cmd[0], -self._max_lin_x, self._max_lin_x))
            vy = float(np.clip(cmd[1], -self._max_lin_y, self._max_lin_y))
            wz = float(np.clip(cmd[2], -self._max_ang_z, self._max_ang_z))
            return vx, vy, wz

        return 0.0, 0.0, 0.0


# ===========================================================================
# Helpers (original)
# ===========================================================================
def _resolve_onnx_path(log_dir: str, explicit_onnx: str | None) -> str:
    if explicit_onnx:
        try:
            return retrieve_file_path(explicit_onnx)
        except Exception:
            path = Path(explicit_onnx).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Cannot find ONNX file: {path}")
            return str(path)
    default_onnx = Path(log_dir) / "exported" / "policy.onnx"
    if not default_onnx.is_file():
        raise FileNotFoundError(
            f"Could not find default ONNX file at: {default_onnx}. Use --onnx.")
    return str(default_onnx)


def _make_onnx_session(onnx_path: str, prefer_gpu: bool) -> ort.InferenceSession:
    sess_options = ort.SessionOptions()
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = (["CUDAExecutionProvider", "CPUExecutionProvider"]
                 if prefer_gpu else ["CPUExecutionProvider"])
    try:
        return ort.InferenceSession(onnx_path, sess_options=sess_options, providers=providers)
    except Exception:
        if prefer_gpu:
            return ort.InferenceSession(onnx_path, sess_options=sess_options,
                                        providers=["CPUExecutionProvider"])
        raise

# 4.23 修改
# def _extract_policy_obs(obs):
#     if isinstance(obs, torch.Tensor):
#         return obs
#     if hasattr(obs, "keys"):
#         keys = list(obs.keys()) if callable(getattr(obs, "keys", None)) else []
#         for key in ("policy", "obs", "observations"):
#             try:
#                 if key in keys or (hasattr(obs, "__contains__") and key in obs):
#                     v = obs[key]
#                     if isinstance(v, torch.Tensor):
#                         return v
#             except Exception:
#                 pass
#         for key in keys:
#             try:
#                 v = obs[key]
#                 if isinstance(v, torch.Tensor):
#                     return v
#             except Exception:
#                 pass
#         raise TypeError(f"Unsupported observation container keys: {keys}")
#     if isinstance(obs, (tuple, list)) and len(obs) > 0:
#         return _extract_policy_obs(obs[0])
#     raise TypeError(f"Unsupported observation type: {type(obs)}")

def _extract_policy_obs(obs):
    """从TensorDict提取ONNX推理所需的观测。
    HIM策略: obs_history [N,5,53] → flatten → [N,265]，拼上当前obs[N,53] = [N,318]
    """
    if isinstance(obs, torch.Tensor):
        return obs
    if hasattr(obs, "keys"):
        keys = list(obs.keys()) if callable(getattr(obs, "keys", None)) else []
        # HIM策略：拼接 obs_history + 当前obs 组成完整输入
        if "obs_history" in keys and "policy" in keys:
            obs_history = obs["obs_history"]          # [N, 5, 53]
            obs_current = obs["policy"][:, :53]       # 取前53维作为当前obs
            obs_hist_flat = obs_history.reshape(obs_history.shape[0], -1)  # [N, 265]
            return torch.cat([obs_hist_flat, obs_current], dim=-1)          # [N, 318]
        # 直接有policy key
        for key in ("policy", "obs", "observations"):
            if key in keys:
                v = obs[key]
                if isinstance(v, torch.Tensor):
                    return v
    if isinstance(obs, (tuple, list)) and len(obs) > 0:
        return _extract_policy_obs(obs[0])
    raise TypeError(f"Unsupported observation type: {type(obs)}")

def _get_robot_xy_yaw(env) -> tuple[float, float, float]:
    """Extract (x, y, yaw) from IsaacLab environment."""
    try:
        base = env.unwrapped
        for name in ("robot", "m20", "legged_robot", "anymal"):
            try:
                robot = base.scene[name]
                pos  = robot.data.root_pos_w[0].cpu().numpy()   # [x, y, z]
                quat = robot.data.root_quat_w[0].cpu().numpy()  # [w, x, y, z]
                w, x, y, z = quat
                yaw = float(np.arctan2(2.0*(w*z + x*y),
                                       1.0 - 2.0*(y*y + z*z)))
                return float(pos[0]), float(pos[1]), yaw
            except (KeyError, AttributeError):
                continue
    except Exception:
        pass
    return 0.0, 0.0, 0.0


def _full_reset_robot(env, x: float, y: float, yaw: float) -> bool:
    """瞬间传送机器人到 (x, y, yaw)，同时重置所有状态与内部缓存"""
    try:
        # ★ 关键修复：将被 PyTorch 限制的张量修改操作包裹在 inference_mode 中
        with torch.inference_mode():
            base = env.unwrapped
            target_name = None
            
            # 1. 安全获取场景中的机器人名称
            if hasattr(base, "scene"):
                for name in ("robot", "m20", "legged_robot", "anymal"):
                    if name in base.scene.keys():
                        target_name = name
                        break
                        
            if target_name is None:
                print(f"[Reset Error] 找不到机器人对象，传送失败！")
                return False
                
            robot = base.scene[target_name]
            env_ids = torch.tensor([0], device=env.unwrapped.device)

            # 2. 设定根节点状态 (现在在 inference_mode 下，允许 inplace 修改)
            root_state = robot.data.default_root_state.clone()
            root_state[0, 0] = float(x)
            root_state[0, 1] = float(y)
            
            half_yaw = float(yaw) * 0.5
            root_state[0, 3] = float(np.cos(half_yaw))  # w
            root_state[0, 4] = 0.0                       # x
            root_state[0, 5] = 0.0                       # y
            root_state[0, 6] = float(np.sin(half_yaw))  # z
            root_state[0, 7:13] = 0.0                    # 强行将线速度与角速度清零

            # 3. 显式写入底层物理引擎
            robot.write_root_state_to_sim(root_state, env_ids=env_ids)

            # 4. 关节状态清零 (防止传送后因为旧姿态摔倒)
            joint_pos = robot.data.default_joint_pos.clone()
            joint_vel = torch.zeros_like(joint_pos)
            robot.write_joint_state_to_sim(joint_pos, joint_vel, env_ids=env_ids)

            # 5. ★ 关键：重置机器人的内部历史数据缓存
            if hasattr(robot, "reset"):
                robot.reset(env_ids=env_ids)

            print(f"[Reset] 成功传送到 ({x:.3f}, {y:.3f}, yaw={float(np.degrees(yaw)):.1f}°)")
            return True
            
    except Exception as e:
        print(f"[Reset Error] 传送发生异常: {e}")
    return False

def _inject_velocity_command(env, vx: float, vy: float, wz: float):
    """
    终极版：安全注入速度指令，并物理冻结 Isaac Lab 的内部指令刷新机制。
    """
    cmd_manager = env.unwrapped.command_manager
    target_tensor = torch.tensor([vx, vy, wz], device=env.unwrapped.device)

    # 1. 覆盖对外暴露的指令 buffer
    try:
        cmd_manager.get_command("base_velocity")[:] = target_tensor
    except KeyError:
        pass

    # 2. ★ 终极杀手锏：拦截并冻结内部更新机制 (Monkey Patch)
    try:
        cmd_term = cmd_manager.get_term("base_velocity")

        # 同步覆盖内部的核心状态
        if hasattr(cmd_term, "vel_command_b"):
            cmd_term.vel_command_b[:] = target_tensor

        # 如果还没有被冻结，我们就强行替换它的 compute 方法
        if not getattr(cmd_term, "_is_frozen_by_teleop", False):
            # 将环境内部的 compute 方法替换为一个什么都不做的空函数
            # 这样 env.step() 调用它时，它就不会再把指令重置为 0 了
            cmd_term.compute = lambda *args, **kwargs: None
            
            # 打上标记，防止重复 patch
            cmd_term._is_frozen_by_teleop = True
            
    except KeyError:
        pass
# ===========================================================================
# Main
# ===========================================================================
@hydra_task_config(args_cli.task, args_cli.agent)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg,
         agent_cfg: RslRlOnPolicyRunnerCfg):

    agent_cfg = cli_args.update_rsl_rl_cfg(agent_cfg, args_cli)
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else 1
    env_cfg.seed            = agent_cfg.seed
    env_cfg.sim.device      = (args_cli.device if args_cli.device is not None
                               else env_cfg.sim.device)

    # ------------------------------------------------------------------
    # keyboard mode (pure teleop / 建图)  – unchanged
    # ------------------------------------------------------------------
    if args_cli.keyboard:
        env_cfg.scene.num_envs = 1
        env_cfg.terminations.time_out = None
        env_cfg.commands.base_velocity.debug_vis = False
        kb_cfg = Se2KeyboardCfg(
            v_x_sensitivity=env_cfg.commands.base_velocity.ranges.lin_vel_x[1] / 2,
            v_y_sensitivity=env_cfg.commands.base_velocity.ranges.lin_vel_y[1],
            omega_z_sensitivity=env_cfg.commands.base_velocity.ranges.ang_vel_z[1],
        )
        controller = Se2Keyboard(kb_cfg)
        env_cfg.observations.policy.velocity_commands = ObsTerm(
            func=lambda env: torch.tensor(controller.advance(), dtype=torch.float32)
                             .unsqueeze(0).to(env.device),
        )

    # ------------------------------------------------------------------
    # ★ nav mode – hybrid A* planner + keyboard  (replaces /cmd_vel)
    # ------------------------------------------------------------------
    hybrid_source: HybridCmdVelSource | None = None
    if args_cli.nav:
        env_cfg.scene.num_envs = 1
        env_cfg.terminations.time_out = None
        env_cfg.commands.base_velocity.debug_vis = False

        hybrid_source = HybridCmdVelSource(
            map_yaml             = args_cli.map_yaml,
            goal_xy              = (args_cli.goal_x, args_cli.goal_y),
            inflation_radius     = args_cli.inflation_radius,
            hard_inflation_radius= args_cli.hard_inflation_radius,
            max_lin_x            = args_cli.max_lin_x,
            max_lin_y            = args_cli.max_lin_y,
            max_ang_z            = args_cli.max_ang_z,
        )
        hybrid_source.start()

        _src = hybrid_source  # capture for lambda

        def _hybrid_velocity_cmd(env):
            rx, ry, ryaw = _get_robot_xy_yaw(env)
            vx, vy, wz   = _src.get_command(rx, ry, ryaw)
            return torch.tensor([[vx, vy, wz]], dtype=torch.float32).to(env.device)

        env_cfg.observations.policy.velocity_commands = ObsTerm(func=_hybrid_velocity_cmd)
        print(f"[Nav] Hybrid A*+keyboard mode active.")
        print(f"[Nav] Map  : {args_cli.map_yaml}")
        print(f"[Nav] Goal : ({args_cli.goal_x}, {args_cli.goal_y})")

    # ------------------------------------------------------------------
    # ★ cmd_vel mode – 订阅 /cmd_vel 注入速度指令（速度响应测试）
    # ------------------------------------------------------------------
    cmd_vel_bridge: CmdVelBridge | None = None
    cmd_vel_kb:     HybridCmdVelSource | None = None   # ★ cmd_vel 模式附加键盘控制
    if args_cli.cmd_vel:
        env_cfg.scene.num_envs = 1
        env_cfg.terminations.time_out = None
        env_cfg.commands.base_velocity.debug_vis = False

        cmd_vel_bridge = CmdVelBridge(
            topic      = args_cli.cmd_vel_topic,
            max_lin_x  = args_cli.max_lin_x,
            max_lin_y  = args_cli.max_lin_y,
            max_ang_z  = args_cli.max_ang_z,
        )
        cmd_vel_bridge.start()

        # ★ cmd_vel 模式附加键盘控制（箭头键/N/M 覆盖 /cmd_vel，R 键传送回起点）
        # HybridCmdVelSource 只用于键盘订阅，地图只在按 K/G 时才会加载
        cmd_vel_kb = HybridCmdVelSource(
            map_yaml             = args_cli.map_yaml,
            goal_xy              = (args_cli.goal_x, args_cli.goal_y),
            inflation_radius     = args_cli.inflation_radius,
            hard_inflation_radius= args_cli.hard_inflation_radius,
            max_lin_x            = args_cli.max_lin_x,
            max_lin_y            = args_cli.max_lin_y,
            max_ang_z            = args_cli.max_ang_z,
        )
        cmd_vel_kb.start()
        print("[CmdVel] Keyboard overlay: ↑↓←→ move | N/M yaw | R teleport home | 键盘优先于 /cmd_vel")

        # ================= 补充缺失的 ObsTerm 覆盖 =================
        _cmd_vel_src = cmd_vel_bridge  # 捕获局部变量给 lambda 使用
        _kb_src = cmd_vel_kb           # 补充：捕获键盘对象

        def _cmd_vel_velocity_cmd(env):
            # 修改：在此处加入与主循环完全一致的优先级判断
            if _kb_src is not None and _kb_src._is_keyboard_active():
                vx, vy, wz = _kb_src.get_command(0.0, 0.0, 0.0)
            else:
                vx, vy, wz = _cmd_vel_src.get()
                
            # 返回 shape 为 [num_envs, 3] 的张量，即 [[vx, vy, wz]]
            return torch.tensor([[vx, vy, wz]], dtype=torch.float32).to(env.device)

        # 强制将策略的期望速度观测替换为我们订阅到的 cmd_vel + 键盘控制
        env_cfg.observations.policy.velocity_commands = ObsTerm(func=_cmd_vel_velocity_cmd)
        # =========================================================

        print(f"[CmdVel] Bridge started, listening on {args_cli.cmd_vel_topic}")
        print(f"[CmdVel] Velocity limits: "
              f"vx={args_cli.max_lin_x}, vy={args_cli.max_lin_y}, wz={args_cli.max_ang_z}")
        print(f"[CmdVel] 测试命令示例:")
        print(f"  ros2 topic pub {args_cli.cmd_vel_topic} geometry_msgs/msg/Twist "
              f'"{{linear: {{x: 0.5}}, angular: {{z: 1.0}}}}"')

    # ------------------------------------------------------------------
    # ONNX session
    # ------------------------------------------------------------------
    log_root_path = os.path.abspath(
        os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
    resume_path = (retrieve_file_path(args_cli.checkpoint)
                   if args_cli.checkpoint
                   else get_checkpoint_path(log_root_path, agent_cfg.load_run,
                                            agent_cfg.load_checkpoint))
    log_dir   = os.path.dirname(resume_path)
    onnx_path = _resolve_onnx_path(log_dir, args_cli.onnx)
    ort_session = _make_onnx_session(onnx_path, prefer_gpu=(not args_cli.onnx_cpu))
    input_name  = ort_session.get_inputs()[0].name
    # 4.23 添加
    print("[ONNX] 模型输入列表:")
    for inp in ort_session.get_inputs():
        print(f"  name={inp.name}, shape={inp.shape}, dtype={inp.type}")
    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------
    env = gym.make(args_cli.task, cfg=env_cfg,
                   render_mode="rgb_array" if args_cli.video else None)
    if isinstance(env.unwrapped, DirectMARLEnv):
        env = multi_agent_to_single_agent(env)
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

    # ------------------------------------------------------------------
    # 3DGS 碰撞体初始化（必须在 env 创建后、play 前完成）
    # ------------------------------------------------------------------
    # 检查是否是 Perception 环境（含 3DGS 场景）
    _3dgs_root = getattr(getattr(env_cfg, "scene", None), "gaussian_scene", None)
    if _3dgs_root is not None:
        _3dgs_prim_path = "/World/envs/env_0/gauss"
        apply_collision_to_3dgs(_3dgs_prim_path, approximation="none")
        # 让物理引擎走几帧，确保碰撞体注册生效
        for _ in range(5):
            simulation_app.update()
    else:
        print("[Collision] No gaussian_scene found in env_cfg.scene, skipping 3DGS collision setup.")

    # ------------------------------------------------------------------
    # ROS2 bridge graph
    # ------------------------------------------------------------------
    # if args_cli.enable_ros2_bridge:
    #     bridge_cfg = Ros2M20BridgeCfg()
    #     build_ros2_bridge_graph(bridge_cfg)
    if args_cli.enable_ros2_bridge:
        bridge_cfg = Ros2M20BridgeCfg()
        build_ros2_bridge_graph(bridge_cfg)
        # ★ 让物理引擎走几帧，确保 IMU 传感器产生有效数据
        for _ in range(3):
            simulation_app.update()
    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    obs = env.get_observations()
    dt  = env.unwrapped.step_dt

    if not hasattr(main, "_log_counter"): main._log_counter = 0
    lookahead_dist = 2  # 前瞻距离 (米)，根据机器人步速可调

    # ★ 记录初始位置（供 R 键回家、多路径巡游回起点使用）
    simulation_app.update()
    _init_x, _init_y, _init_yaw = _get_robot_xy_yaw(env)
    _home_xy = (_init_x, _init_y)
    print(f"[Home] Initial position recorded: ({_init_x:.3f}, {_init_y:.3f})")

    while simulation_app.is_running():
        start_time = time.time()

        # ---- 1. Handle keyboard requests from hybrid source (A* planner) ----
        if hybrid_source is not None:
            if hybrid_source.request_cancel:
                hybrid_source.request_cancel = False
                hybrid_source.cancel_auto()

            if hybrid_source.request_plan_and_start:
                hybrid_source.request_plan_and_start = False
                rx, ry, _ = _get_robot_xy_yaw(env)
                ok = hybrid_source.do_plan(rx, ry)
                if ok:
                    hybrid_source.start_auto()

            elif hybrid_source.request_plan_only:
                hybrid_source.request_plan_only = False
                rx, ry, _ = _get_robot_xy_yaw(env)
                hybrid_source.do_plan(rx, ry)

            if hybrid_source.request_start_auto:
                hybrid_source.request_start_auto = False
                hybrid_source.start_auto()

            # ★ R 键：直接传送回初始位置，重置全部状态
            if hybrid_source.request_go_home:
                hybrid_source.request_go_home = False
                hybrid_source.go_home()                          # 停导航
                _full_reset_robot(env, _home_xy[0], _home_xy[1], _init_yaw)

            # ★ T 键：启动多路径巡游（所有路径从 home 出发预先规划）
            if hybrid_source.request_multi_path:
                hybrid_source.request_multi_path = False
                hybrid_source.plan_multi_paths(
                    start_x   = _home_xy[0],
                    start_y   = _home_xy[1],
                    home_xy   = _home_xy,
                    n_paths   = args_cli.multi_paths,
                    perturb_m = args_cli.multi_perturb_m,
                )

            teleported_this_frame = False
            # ★ 多路径传送回家（tick_multi 触发，主循环执行）
            if hybrid_source.request_teleport_home:
                _full_reset_robot(env, _home_xy[0], _home_xy[1], _init_yaw)
                hybrid_source.on_teleport_done()   # 传送完成 → 启动下一条路径
                teleported_this_frame = True       # 标记当前帧发生过物理传送
                
        # ---- 2. Path Following (A* nav mode) ----
        if args_cli.nav and hybrid_source:
            if teleported_this_frame:
                # ★ 关键：传送当帧跳过导航计算，强制下发0速度，等待物理引擎在下一帧刷新位置
                target_vx, target_vy, target_wz = 0.0, 0.0, 0.0
                nav_active = True
            else:
                curr_x, curr_y, curr_yaw = _get_robot_xy_yaw(env)
                # ★ 多路径巡游 tick（检测路径完成，设置传送标志）
                hybrid_source.tick_multi()
                target_vx, target_vy, target_wz = hybrid_source.get_command(curr_x, curr_y, curr_yaw)
                nav_active = hybrid_source._auto_mode


            env.unwrapped.command_manager.get_command("base_velocity")[:] = torch.tensor(
                [target_vx, target_vy, target_wz], device=env.unwrapped.device
            )

            main._log_counter += 1
            if main._log_counter % 20 == 0:
                if nav_active:
                    print(f"[NAV LOG] 正在自动导航: VX={target_vx:.3f}, VY={target_vy:.3f}, WZ={target_wz:.3f} | Pose=({curr_x:.2f}, {curr_y:.2f})")
                elif hybrid_source._is_keyboard_active():
                    print(f"[NAV LOG] 键盘接管中: VX={target_vx:.3f}, VY={target_vy:.3f}, WZ={target_wz:.3f}")
                else:
                    print(f"[NAV LOG] 待机/已到达: VX=0.0, VY=0.0, WZ=0.0")

        # ---- 3. ★ cmd_vel bridge 注入（速度响应测试模式）----
        if args_cli.cmd_vel and cmd_vel_bridge is not None:

            # ★ R 键：传送回初始位置，重置全部状态
            if cmd_vel_kb is not None and cmd_vel_kb.request_go_home:
                cmd_vel_kb.request_go_home = False
                _full_reset_robot(env, _home_xy[0], _home_xy[1], _init_yaw)

            # ★ 键盘优先：有键盘输入时用键盘速度，否则用 /cmd_vel
            if cmd_vel_kb is not None and cmd_vel_kb._is_keyboard_active():
                vx, vy, wz = cmd_vel_kb.get_command(0.0, 0.0, 0.0)
                src = "KB"
            else:
                vx, vy, wz = cmd_vel_bridge.get()
                src = "ROS"

            _inject_velocity_command(env, vx, vy, wz)

            main._log_counter += 1
            if main._log_counter % 20 == 0:
                print(f"[CMDVEL LOG] [{src}] VX={vx:.3f}, VY={vy:.3f}, WZ={wz:.3f}")

        # ---- 4. Policy inference ----
        with torch.inference_mode():
            policy_obs = _extract_policy_obs(obs)
            actions_np = ort_session.run(
                None, {input_name: policy_obs.detach().cpu().numpy()})[0]
            actions = torch.from_numpy(actions_np).to(env.unwrapped.device)
            # 4.23
            # obs, _, _, _ = env.step(actions)
            step_ret, _, _, _ = env.step(actions)
            obs = step_ret  # 保持TensorDict格式，_extract_policy_obs会处理

        # ---- 5. 后续处理 ----
        if args_cli.keyboard:
            camera_follow(env)

        # ---- Real-time pacing ----
        sleep_time = dt - (time.time() - start_time)
        if args_cli.real_time and sleep_time > 0:
            time.sleep(sleep_time)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    if hybrid_source is not None:
        hybrid_source.stop()
    if cmd_vel_kb is not None:
        cmd_vel_kb.stop()
    if cmd_vel_bridge is not None:
        cmd_vel_bridge.stop()
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()