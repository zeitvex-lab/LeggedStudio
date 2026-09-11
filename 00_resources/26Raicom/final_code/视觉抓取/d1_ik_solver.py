#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D1 机械臂逆运动学求解器 (基于 URDF FK + 阻尼最小二乘)
====================================================

基于 D1ForwardKinematics (URDF 参数) 的数值 IK 求解器。

方法: 阻尼最小二乘法 (Damped Least Squares / Levenberg-Marquardt)
  Δθ = Jᵀ · (J·Jᵀ + λ²·I)⁻¹ · Δx

特点:
  - 解析雅可比 (通过 FK 链计算, 非数值差分)
  - 支持关节锁定 (locked_joints)
  - 自适应阻尼因子
  - 关节限位钳位保护

用法:
    from d1_forward_kinematics import D1ForwardKinematics
    from d1_ik_solver import D1InverseKinematics, D1ReachabilityAnalyzer

    fk = D1ForwardKinematics()
    ik = D1InverseKinematics(fk, ref_angles=[-90,10,55,0,-61,0])
    angles, ok, info = ik.solve_relative_xyz_with_orientation(
        5, 0, 0, ori_weight=0.0, locked_joints={3:0, 4:-61, 5:0})
"""

import numpy as np
from typing import List, Tuple, Optional

from d1_forward_kinematics import D1ForwardKinematics

DEG_TO_RAD = np.pi / 180.0
RAD_TO_DEG = 180.0 / np.pi


# ============================================================
# 可达性分析器
# ============================================================

class D1ReachabilityAnalyzer:
    """D1 机械臂工作空间可达性检查"""

    def __init__(self, fk: D1ForwardKinematics):
        self.fk = fk

    @property
    def max_reach_mm(self) -> float:
        return self.fk.max_reach_mm

    def check_reachable(self, target_mm) -> bool:
        """检查目标位置是否在理论工作空间内

        Args:
            target_mm: np.ndarray (3,) 或 list, 目标位置 (mm)
        Returns:
            bool
        """
        target = np.asarray(target_mm, dtype=float).flatten()
        dist = np.linalg.norm(target)
        return dist <= self.max_reach_mm


# ============================================================
# IK 求解器
# ============================================================

class D1InverseKinematics:
    """D1 机械臂逆运动学求解器 (DLS 数值方法)"""

    def __init__(self,
                 fk: D1ForwardKinematics = None,
                 ref_angles: List[float] = None,
                 damping: float = 0.3,
                 max_iters: int = 200,
                 tol_position: float = 0.1,
                 nullspace_gain: float = 0.0):
        """
        Args:
            fk: D1ForwardKinematics 实例
            ref_angles: J0-J5 参考关节角度 (度), 其 FK 位置作为 XYZ 原点
            damping: 初始阻尼因子 λ
            max_iters: 最大迭代次数
            tol_position: 位置收敛阈值 (mm)
            nullspace_gain: 零空间投影增益 (0=不使用)
        """
        self._fk = fk if fk is not None else D1ForwardKinematics()

        # 兼容 arm_ik_control.py 通过属性访问
        self.fk = self._fk

        self.damping = damping
        self.max_iters = max_iters
        self.tol_position = tol_position
        self.nullspace_gain = nullspace_gain

        # 关节限位 (度)
        self.joint_limits = [
            (-135, 135),   # J0
            (-90, 90),     # J1
            (-90, 90),     # J2
            (-135, 135),   # J3
            (-90, 90),     # J4
            (-135, 135),   # J5
        ]

        # 参考姿态
        if ref_angles is not None:
            self.set_reference(ref_angles)
        else:
            self._ref_angles = np.array([0.0] * 6)
            self._ref_position = np.zeros(3)

        # 统计
        self._total_solves = 0
        self._successful_solves = 0

    # ================================================================
    # 参考坐标系
    # ================================================================

    def set_reference(self, ref_angles: List[float]):
        """设置参考原点, 其末端位置作为 XYZ 原点 (0,0,0)"""
        self._ref_angles = np.array(ref_angles[:6], dtype=float)
        T_ref = self._fk.forward_kinematics(ref_angles[:6])
        self._ref_position = T_ref[:3, 3].copy()

    @property
    def ref_angles(self) -> np.ndarray:
        """参考关节角度 (度), 兼容 list 访问"""
        return self._ref_angles

    @property
    def ref_position(self) -> np.ndarray:
        """参考位置 (mm), 兼容 ndarray 操作"""
        return self._ref_position

    # ================================================================
    # 运动学链 + 解析雅可比
    # ================================================================

    def _compute_kinematics_chain(self, angles: np.ndarray):
        """计算 FK + 各关节在世界坐标系中的位置和旋转轴

        Returns:
            (T_ee: 4x4, joint_positions: list[3], joint_axes: list[3])
        """
        T = np.eye(4, dtype=np.float64)
        joint_positions = []
        joint_axes = []

        for i, (angle_deg, param) in enumerate(zip(angles, self._fk.joint_params)):
            theta_rad = np.deg2rad(angle_deg * param.angle_sign)
            T_origin = self._fk.origin_transform(param.origin_xyz, param.origin_rpy)

            # 关节原点位置
            p_joint = (T @ T_origin)[:3, 3]
            joint_positions.append(p_joint)

            # 关节旋转轴在世界坐标系中的方向
            axis_local = np.array(param.axis_xyz, dtype=np.float64)
            axis_world = (T @ T_origin)[:3, :3] @ axis_local
            axis_world = axis_world / np.linalg.norm(axis_world)
            joint_axes.append(axis_world)

            # 累积变换
            T_rot = self._fk.axis_rotation(param.axis_xyz, theta_rad)
            T = T @ T_origin @ T_rot

        return T, joint_positions, joint_axes

    def compute_jacobian(self, angles: np.ndarray) -> np.ndarray:
        """6×6 解析几何雅可比 (mm/deg)

        每列对应 D1 库的输入角度 (已补偿 angle_sign)
        """
        T_ee, positions, axes = self._compute_kinematics_chain(angles)
        p_ee = T_ee[:3, 3]

        J = np.zeros((6, 6), dtype=np.float64)

        for i in range(6):
            z_i = axes[i]
            p_i = positions[i]
            sign = self._fk.joint_params[i].angle_sign
            # 位置: z_i × (p_ee - p_i) (mm/rad) → × sign → × DEG_TO_RAD → mm/deg
            J[:3, i] = np.cross(z_i, p_ee - p_i) * sign * DEG_TO_RAD
            J[3:, i] = z_i * sign * DEG_TO_RAD

        return J

    def _clamp_joints(self, angles: np.ndarray) -> np.ndarray:
        """钳位到关节限位"""
        clamped = angles.copy()
        for i, (lo, hi) in enumerate(self.joint_limits):
            if clamped[i] < lo:
                clamped[i] = lo
            elif clamped[i] > hi:
                clamped[i] = hi
        return clamped

    # ================================================================
    # IK 求解 (主入口)
    # ================================================================

    def solve_relative_xyz_with_orientation(self,
                                              x_cm: float,
                                              y_cm: float,
                                              z_cm: float,
                                              ori_weight: float = 0.0,
                                              locked_joints: dict = None) -> Tuple[
                                                  List[float], bool, dict]:
        """相对 XYZ 逆运动学求解

        Args:
            x_cm, y_cm, z_cm: 相对参考位置的偏移 (cm)
            ori_weight: 姿态约束权重 (0.0 = 仅位置)
            locked_joints: dict {joint_index: angle_deg}, 锁定关节

        Returns:
            (angles_6dof: list[float], success: bool, info: dict)
            info keys: error_mm, error_ori_deg, j4_angle, iterations
        """
        if locked_joints is None:
            locked_joints = {}

        # 目标位置 (mm)
        target_mm = self._ref_position + np.array([x_cm * 10.0,
                                                    y_cm * 10.0,
                                                    z_cm * 10.0])

        # 初始角度: 参考角度 + 锁定关节覆盖
        angles = self._ref_angles.copy()
        for j_idx, j_angle in locked_joints.items():
            angles[j_idx] = float(j_angle)

        # 自由度掩码
        free_mask = np.array([i not in locked_joints for i in range(6)],
                             dtype=bool)
        n_free = int(free_mask.sum())

        if n_free == 0:
            # 无自由关节, 直接返回锁定角度
            T = self._fk.forward_kinematics(angles)
            p_current = T[:3, 3]
            pos_error = target_mm - p_current
            error_mm = float(np.linalg.norm(pos_error))
            info = {'error_mm': error_mm, 'error_ori_deg': 0.0,
                    'iterations': 0, 'j4_angle': float(angles[4])}
            return (list(angles), error_mm < self.tol_position, info)

        # ---- 阻尼最小二乘迭代 ----
        damping = self.damping
        best_error = float('inf')
        best_angles = angles.copy()

        for iteration in range(self.max_iters):
            # FK
            T = self._fk.forward_kinematics(angles)
            p_current = T[:3, 3]
            R_current = T[:3, :3]

            # 位置误差 (mm)
            pos_error = target_mm - p_current
            error_mm = float(np.linalg.norm(pos_error))

            # 姿态误差
            error_ori_deg = 0.0
            if ori_weight > 1e-9:
                T_ref = self._fk.forward_kinematics(self._ref_angles)
                R_err = R_current.T @ T_ref[:3, :3]
                trace = np.clip(np.trace(R_err), -1.0, 3.0)
                angle_rad = np.arccos((trace - 1.0) / 2.0)
                error_ori_deg = float(np.degrees(angle_rad))

            # 记录最优
            if error_mm < best_error:
                best_error = error_mm
                best_angles = angles.copy()

            # 收敛
            if error_mm < self.tol_position:
                self._successful_solves += 1
                self._total_solves += 1
                return (list(best_angles), True,
                        self._make_info(float(best_error), error_ori_deg,
                                        iteration + 1, best_angles))

            # 雅可比
            J_full = self.compute_jacobian(angles)     # (6, 6), mm/deg
            J_pos = J_full[:3, :]                       # (3, 6)

            # 构建误差向量
            if ori_weight > 1e-9:
                if angle_rad > 1e-9:
                    axis = (1.0 / (2.0 * np.sin(angle_rad))) * np.array([
                        R_err[2, 1] - R_err[1, 2],
                        R_err[0, 2] - R_err[2, 0],
                        R_err[1, 0] - R_err[0, 1],
                    ])
                    ori_error = axis * angle_rad
                else:
                    ori_error = np.zeros(3)
                error_vec = np.concatenate([pos_error,
                                             ori_weight * ori_error * 57.3])
                J = np.vstack([J_pos, ori_weight * J_full[3:, :]])
            else:
                error_vec = pos_error
                J = J_pos

            # 屏蔽锁定关节
            J_free = J[:, free_mask]

            # 阻尼最小二乘
            if n_free > 0:
                JJt = J_free @ J_free.T
                n_eq = J_free.shape[0]
                I_damped = np.eye(n_eq) * (damping ** 2)
                try:
                    delta_free = J_free.T @ np.linalg.solve(JJt + I_damped,
                                                             error_vec)
                except np.linalg.LinAlgError:
                    JTJ = J_free.T @ J_free
                    I_jt = np.eye(n_free) * (damping ** 2)
                    delta_free = np.linalg.solve(JTJ + I_jt,
                                                  J_free.T @ error_vec)
            else:
                delta_free = np.array([])

            # 零空间投影
            delta = np.zeros(6)
            delta[free_mask] = delta_free

            if self.nullspace_gain > 1e-9 and n_free > 0 and n_free > n_eq:
                nullspace = angles - self._ref_angles
                J_pinv = np.linalg.pinv(J_free)
                null_proj = (np.eye(n_free) - J_pinv @ J_free) @ nullspace[free_mask]
                delta[free_mask] += self.nullspace_gain * null_proj

            # 步长限制
            max_step = 10.0  # 度
            step_norm = np.max(np.abs(delta))
            if step_norm > max_step:
                delta *= max_step / step_norm

            angles += delta
            angles = self._clamp_joints(angles)

            # 自适应阻尼
            if error_mm < 2.0:
                damping = max(0.01, damping * 0.8)
            else:
                damping = min(10.0, damping * 1.2)

        # 达最大迭代
        self._total_solves += 1
        success = best_error < max(self.tol_position * 20, 10.0)
        return (list(best_angles), success,
                self._make_info(float(best_error), error_ori_deg,
                                self.max_iters, best_angles))

    # ================================================================
    # 辅助
    # ================================================================

    def _make_info(self, error_mm, error_ori_deg, iterations, angles):
        return {
            'error_mm': error_mm,
            'error_ori_deg': error_ori_deg,
            'iterations': iterations,
            'j4_angle': float(angles[4]),
        }

    def print_status(self):
        """打印求解器状态"""
        rate = (self._successful_solves / self._total_solves * 100.0
                if self._total_solves > 0 else 0.0)
        print(f"\n[IK Solver 状态]")
        print(f"  参考角度: {[f'{a:.1f}' for a in self._ref_angles]} deg")
        print(f"  参考位置: [{self._ref_position[0]:.0f}, "
              f"{self._ref_position[1]:.0f}, {self._ref_position[2]:.0f}] mm")
        print(f"  damping={self.damping}, max_iters={self.max_iters}, "
              f"tol={self.tol_position}mm")
        print(f"  求解: {self._successful_solves}/{self._total_solves} "
              f"({rate:.0f}% 成功)")


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    fk = D1ForwardKinematics()
    REF = [-90.0, 10.0, 55.0, 0.0, -61.0, 0.0]

    T_ref = fk.forward_kinematics(REF)
    p_ref = T_ref[:3, 3]
    print(f"[自测] 参考位置: [{p_ref[0]:.1f}, {p_ref[1]:.1f}, {p_ref[2]:.1f}] mm")

    ik = D1InverseKinematics(fk, REF, damping=0.3, max_iters=200,
                             tol_position=0.1, nullspace_gain=0.0)

    locked = {3: 0.0, 4: -61.0, 5: 0.0}

    # 测试1: 零位移
    angles, ok, info = ik.solve_relative_xyz_with_orientation(
        0, 0, 0, ori_weight=0.0, locked_joints=locked)
    print(f"\n[测试1] 零位移: ok={ok}, error={info['error_mm']:.4f}mm, "
          f"iters={info['iterations']}")
    print(f"  角度: {[f'{a:.1f}' for a in angles]}")

    # 测试2: X+10cm
    angles, ok, info = ik.solve_relative_xyz_with_orientation(
        10, 0, 0, ori_weight=0.0, locked_joints=locked)
    T = fk.forward_kinematics(angles)
    p = T[:3, 3]
    offset = p - p_ref
    print(f"\n[测试2] X+10cm: ok={ok}, error={info['error_mm']:.4f}mm, "
          f"iters={info['iterations']}")
    print(f"  角度: {[f'{a:.1f}' for a in angles]}")
    print(f"  实际偏移: ({offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}) mm")

    # 测试3: X+20cm
    angles, ok, info = ik.solve_relative_xyz_with_orientation(
        20, 0, 0, ori_weight=0.0, locked_joints=locked)
    T = fk.forward_kinematics(angles)
    p = T[:3, 3]
    offset = p - p_ref
    print(f"\n[测试3] X+20cm: ok={ok}, error={info['error_mm']:.4f}mm, "
          f"iters={info['iterations']}")
    print(f"  角度: {[f'{a:.1f}' for a in angles]}")
    print(f"  实际偏移: ({offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}) mm")

    # 测试4: Z-5cm
    angles, ok, info = ik.solve_relative_xyz_with_orientation(
        0, 0, -5, ori_weight=0.0, locked_joints=locked)
    T = fk.forward_kinematics(angles)
    p = T[:3, 3]
    offset = p - p_ref
    print(f"\n[测试4] Z-5cm: ok={ok}, error={info['error_mm']:.4f}mm, "
          f"iters={info['iterations']}")
    print(f"  角度: {[f'{a:.1f}' for a in angles]}")
    print(f"  实际偏移: ({offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}) mm")

    # 可达性
    analyzer = D1ReachabilityAnalyzer(fk)
    print(f"\n[可达性] 最大半径: {analyzer.max_reach_mm:.0f} mm")
    print(f"  参考位置可达: {analyzer.check_reachable(ik.ref_position)}")
