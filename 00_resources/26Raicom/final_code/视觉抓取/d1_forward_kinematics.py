#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D1 机械臂正运动学 (基于 D1-550 URDF 参数)

数据来源: https://github.com/gpittonMeko/mujoco_go2_d1
URDF文件: d1_550_description/urdf/d1_550_description.urdf

D1 机械臂结构 (6-DOF + 夹爪):
    底座(J0) → 大臂(J1) → 小臂(J2) → 扭转(J3) → 腕部(J4) → 腕扭(J5) → 夹爪(J6)

注意: J0-J5 为旋转关节(影响末端位姿), J6 为夹爪(不影响末端位姿)

URDF 关节映射:
    D1 J0 (底座旋转)  → URDF Joint1 (axis: -Z, origin: [0, 0, 73.8]mm)
    D1 J1 (大臂)      → URDF Joint2 (axis: +Y, origin: [0, -27.6, 57.8]mm)
    D1 J2 (小臂)      → URDF Joint3 (axis: +Y, origin: [0, -0.4, 270]mm)
    D1 J3 (扭转)      → URDF Joint4 (axis: +X, origin: [50, 27.5, 41.3]mm)
    D1 J4 (腕部)      → URDF Joint5 (axis: +Y, origin: [154.7, -25.8, 0.1]mm)
    D1 J5 (腕扭)      → URDF Joint6 (axis: +X, origin: [77.7, 25.8, -1.1]mm)
    D1 J6 (夹爪)      → URDF Joint_L/R (prismatic, origin: [71.8, ±33, 3.1]mm)

用法:
    from d1_forward_kinematics import D1ForwardKinematics
    fk = D1ForwardKinematics()
    T = fk.forward_kinematics([-90, 10, 55, 0, -61, 0])  # J0-J5 角度(度)
    # T 是 4x4 齐次变换矩阵 (基座 → 末端法兰, 单位: mm)
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class JointParam:
    """URDF 单关节参数 (非 DH 约定, 直接使用 URDF origin + axis)"""
    name: str           # 关节名称
    origin_xyz: Tuple[float, float, float]  # 平移 (mm)
    origin_rpy: Tuple[float, float, float]  # 旋转 (rad)
    axis_xyz: Tuple[float, float, float]    # 旋转轴
    angle_sign: float   # +1 或 -1, D1库角度→URDF角度的符号
    lower_limit_deg: float  # 关节限位 (度)
    upper_limit_deg: float


class D1ForwardKinematics:
    """D1 机械臂正运动学 (基于 URDF origin + axis 约定)

    使用 URDF 原生参数, 不需要 D-H 转换:
        T_base_to_ee = T_origin_1 * Rot_1(theta1) * T_origin_2 * Rot_2(theta2) * ...

    输入: D1 库的关节角度 (度), 对应 J0-J5
    输出: 4x4 齐次变换矩阵 (基座 → 末端法兰, 单位: mm)
    """

    # D1-550 URDF 关节参数 (从 SolidWorks 导出)
    # 来源: github.com/gpittonMeko/mujoco_go2_d1
    URDF_JOINTS: List[JointParam] = [
        # J0: 底座旋转 (URDF Joint1)
        JointParam(
            name="Joint1 (底座)",
            origin_xyz=(0.0, 0.0, 73.8),
            origin_rpy=(0.0, 0.0, 0.0),
            axis_xyz=(0.0, 0.0, -1.0),
            angle_sign=-1.0,
            lower_limit_deg=-135, upper_limit_deg=135,
        ),
        # J1: 大臂 (URDF Joint2)
        JointParam(
            name="Joint2 (大臂)",
            origin_xyz=(0.0, -27.6, 57.8),
            origin_rpy=(0.0, 0.0, 0.0),
            axis_xyz=(0.0, 1.0, 0.0),
            angle_sign=1.0,
            lower_limit_deg=-90, upper_limit_deg=90,
        ),
        # J2: 小臂 (URDF Joint3)
        JointParam(
            name="Joint3 (小臂)",
            origin_xyz=(0.0, -0.4, 270.0),
            origin_rpy=(0.0, 0.0, 0.0),
            axis_xyz=(0.0, 1.0, 0.0),
            angle_sign=1.0,
            lower_limit_deg=-90, upper_limit_deg=90,
        ),
        # J3: 扭转 (URDF Joint4)
        JointParam(
            name="Joint4 (扭转)",
            origin_xyz=(50.0, 27.5, 41.325),
            origin_rpy=(0.0, 0.0, 0.0),
            axis_xyz=(1.0, 0.0, 0.0),
            angle_sign=1.0,
            lower_limit_deg=-135, upper_limit_deg=135,
        ),
        # J4: 腕部 (URDF Joint5)
        JointParam(
            name="Joint5 (腕部)",
            origin_xyz=(154.68, -25.8, 0.1),
            origin_rpy=(0.0, 0.0, 0.0),
            axis_xyz=(0.0, 1.0, 0.0),
            angle_sign=1.0,
            lower_limit_deg=-90, upper_limit_deg=90,
        ),
        # J5: 腕扭 (URDF Joint6)
        JointParam(
            name="Joint6 (腕扭)",
            origin_xyz=(77.7, 25.822, -1.0718),
            origin_rpy=(0.0, 0.0, 0.0),
            axis_xyz=(1.0, 0.0, 0.0),
            angle_sign=1.0,
            lower_limit_deg=-135, upper_limit_deg=135,
        ),
    ]

    JOINT_NAMES = ["arm_j0", "arm_j1", "arm_j2", "arm_j3",
                   "arm_j4", "arm_j5", "arm_j6"]
    JOINT_LABELS = ["底座", "大臂", "小臂", "扭转", "腕部", "腕扭", "夹爪"]

    def __init__(self,
                 joint_params: List[JointParam] = None,
                 base_transform: np.ndarray = None,
                 tool_transform: np.ndarray = None):
        self.joint_params = joint_params if joint_params is not None else self.URDF_JOINTS
        self.T_world_to_base = base_transform if base_transform is not None else np.eye(4)
        self.T_flange_to_tool = tool_transform if tool_transform is not None else np.eye(4)
        self.NUM_JOINTS = len(self.joint_params)
        self._cached_reach = None

    @staticmethod
    def origin_transform(xyz: Tuple[float, float, float],
                         rpy: Tuple[float, float, float]) -> np.ndarray:
        """URDF origin → 4x4 齐次变换矩阵"""
        x, y, z = xyz
        r, p, yaw = rpy

        cr, sr = np.cos(r), np.sin(r)
        cp, sp = np.cos(p), np.sin(p)
        cy, sy = np.cos(yaw), np.sin(yaw)

        R = np.array([
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp,     cp * sr,                cp * cr],
        ], dtype=np.float64)

        T = np.eye(4, dtype=np.float64)
        T[:3, :3] = R
        T[:3, 3] = [x, y, z]
        return T

    @staticmethod
    def axis_rotation(axis: Tuple[float, float, float], theta_rad: float) -> np.ndarray:
        """Rodrigues 公式: 绕任意轴旋转的 4x4 矩阵"""
        ax = np.array(axis, dtype=np.float64)
        ax = ax / np.linalg.norm(ax)

        c = np.cos(theta_rad)
        s = np.sin(theta_rad)
        v = 1 - c
        ux, uy, uz = ax

        R = np.array([
            [c + ux * ux * v,     ux * uy * v - uz * s, ux * uz * v + uy * s],
            [uy * ux * v + uz * s, c + uy * uy * v,     uy * uz * v - ux * s],
            [uz * ux * v - uy * s, uz * uy * v + ux * s, c + uz * uz * v],
        ], dtype=np.float64)

        T = np.eye(4, dtype=np.float64)
        T[:3, :3] = R
        return T

    def forward_kinematics(self, joint_angles_deg: List[float]) -> np.ndarray:
        """正运动学: D1 关节角度 → 末端法兰位姿

        链式: T = T_origin_1 * Rot_1(theta1) * T_origin_2 * Rot_2(theta2) * ...

        Args:
            joint_angles_deg: J0-J5 角度列表 (度), J6 (夹爪) 忽略
        Returns:
            4x4 齐次变换矩阵 (基座 → 末端法兰, 单位: mm)
        """
        angles = joint_angles_deg[:self.NUM_JOINTS]
        T = np.eye(4, dtype=np.float64)

        for angle_deg, param in zip(angles, self.joint_params):
            theta_rad = np.deg2rad(angle_deg * param.angle_sign)
            T_origin = self.origin_transform(param.origin_xyz, param.origin_rpy)
            T_rot = self.axis_rotation(param.axis_xyz, theta_rad)
            T = T @ T_origin @ T_rot

        return T

    def forward_kinematics_world(self, joint_angles_deg: List[float]) -> np.ndarray:
        """世界坐标系下的 FK (含工具变换)"""
        T_base_to_flange = self.forward_kinematics(joint_angles_deg)
        return self.T_world_to_base @ T_base_to_flange @ self.T_flange_to_tool

    def get_joint_transforms(self, joint_angles_deg: List[float]) -> List[np.ndarray]:
        """获取基座→各关节坐标系的变换链"""
        angles = joint_angles_deg[:self.NUM_JOINTS]
        transforms = []
        T = np.eye(4, dtype=np.float64)

        for angle_deg, param in zip(angles, self.joint_params):
            theta_rad = np.deg2rad(angle_deg * param.angle_sign)
            T_origin = self.origin_transform(param.origin_xyz, param.origin_rpy)
            T_rot = self.axis_rotation(param.axis_xyz, theta_rad)
            T = T @ T_origin @ T_rot
            transforms.append(T.copy())

        return transforms

    def get_end_effector_pose(self, joint_angles_deg: List[float]) -> Tuple[np.ndarray, np.ndarray]:
        """返回末端法兰 (position_mm, rotation_matrix_3x3)"""
        T = self.forward_kinematics(joint_angles_deg)
        return T[:3, 3], T[:3, :3]

    @property
    def max_reach_mm(self) -> float:
        """理论最大臂展 (mm)"""
        if self._cached_reach is None:
            total = 0.0
            for param in self.joint_params:
                total += np.linalg.norm(param.origin_xyz)
            self._cached_reach = total
        return self._cached_reach

    def print_params(self):
        """打印关节参数表"""
        print("\n" + "=" * 80)
        print("  D1 机械臂关节参数 (来源: D1-550 URDF)")
        print("=" * 80)
        print(f"  {'关节':<6} {'名称':<8} {'origin XYZ (mm)':>30}  "
              f"{'axis':>14}  {'限位(°)':>16}")
        print("  " + "-" * 76)
        for i, p in enumerate(self.joint_params):
            xyz_str = f"({p.origin_xyz[0]:.1f}, {p.origin_xyz[1]:.1f}, {p.origin_xyz[2]:.1f})"
            axis_str = f"({p.axis_xyz[0]:+.0f}, {p.axis_xyz[1]:+.0f}, {p.axis_xyz[2]:+.0f})"
            limit_str = f"[{p.lower_limit_deg:.0f}, {p.upper_limit_deg:.0f}]"
            print(f"  J{i:<5} {p.name:<8} {xyz_str:>30}  {axis_str:>14}  {limit_str:>16}")
        print("=" * 80)
        print(f"  估算最大臂展: ~{self.max_reach_mm:.0f} mm")
        print()


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    fk = D1ForwardKinematics()
    fk.print_params()

    print("FK 计算结果 (使用 D1-550 URDF 参数):")
    print("-" * 80)

    ref = [-90.0, 10.0, 55.0, 0.0, -61.0, 0.0]
    T_ref = fk.forward_kinematics(ref)
    p_ref = T_ref[:3, 3]
    print(f"  参考姿态 {ref}")
    print(f"  末端位置: [{p_ref[0]:.1f}, {p_ref[1]:.1f}, {p_ref[2]:.1f}] mm")

    test_poses = {
        "zero":       [0,   -30,  60,   0,  -30,   0],
        "home":       [0,   -30,  70,   0,  -45,   0],
        "伸直":       [0,   0,   0,    0,    0,   0],
    }

    for name, angles in test_poses.items():
        T = fk.forward_kinematics(angles)
        p = T[:3, 3]
        print(f"  {name:12s}: [{p[0]:>8.1f}, {p[1]:>8.1f}, {p[2]:>8.1f}] mm")
