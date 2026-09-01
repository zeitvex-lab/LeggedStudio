"""
URDF Validator
完整的 URDF 验证工具（参考 URDF Studio 和 robot_viewer）
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np


@dataclass
class URDFValidationIssue:
    """验证问题"""
    level: str  # "error" / "warning" / "info"
    category: str
    message: str
    location: str = ""


@dataclass
class URDFValidationResult:
    """URDF 验证结果"""
    valid: bool
    urdf_path: str

    # 统计信息
    num_links: int
    num_joints: int
    num_actuated_joints: int
    total_mass: float

    # 验证问题
    errors: List[URDFValidationIssue]
    warnings: List[URDFValidationIssue]
    info: List[URDFValidationIssue]

    # 加载测试结果
    mujoco_loadable: bool
    mujoco_error: str = ""

    def summary(self) -> str:
        if self.valid:
            return f"✓ Valid URDF ({len(self.warnings)} warnings, {len(self.info)} info)"
        return f"✗ Invalid ({len(self.errors)} errors, {len(self.warnings)} warnings)"


class URDFValidator:
    """
    完整的 URDF 验证器
    参考 URDF Studio 和 robot_viewer
    """

    def __init__(self, urdf_path: str):
        self.urdf_path = Path(urdf_path)
        self.urdf_dir = self.urdf_path.parent
        self.tree = None
        self.root = None

    def validate(self) -> URDFValidationResult:
        """执行完整验证"""
        errors = []
        warnings = []
        info = []

        # 1. 文件存在性
        if not self.urdf_path.exists():
            errors.append(URDFValidationIssue(
                level="error",
                category="file",
                message=f"URDF file not found: {self.urdf_path}"
            ))
            return self._create_result(False, errors, warnings, info)

        # 2. XML 解析
        try:
            self.tree = ET.parse(self.urdf_path)
            self.root = self.tree.getroot()
        except Exception as e:
            errors.append(URDFValidationIssue(
                level="error",
                category="xml",
                message=f"Failed to parse XML: {e}"
            ))
            return self._create_result(False, errors, warnings, info)

        # 3. 基础结构验证
        errors.extend(self._validate_structure())

        # 4. Link 验证
        link_issues = self._validate_links()
        errors.extend([i for i in link_issues if i.level == "error"])
        warnings.extend([i for i in link_issues if i.level == "warning"])

        # 5. Joint 验证
        joint_issues = self._validate_joints()
        errors.extend([i for i in joint_issues if i.level == "error"])
        warnings.extend([i for i in joint_issues if i.level == "warning"])

        # 6. Mesh 文件验证
        mesh_issues = self._validate_meshes()
        errors.extend([i for i in mesh_issues if i.level == "error"])
        warnings.extend([i for i in mesh_issues if i.level == "warning"])

        # 7. 质量属性验证
        mass_issues = self._validate_mass_properties()
        warnings.extend([i for i in mass_issues if i.level == "warning"])
        info.extend([i for i in mass_issues if i.level == "info"])

        # 8. MuJoCo 加载测试
        mujoco_loadable, mujoco_error = self._test_mujoco_load()
        if not mujoco_loadable:
            errors.append(URDFValidationIssue(
                level="error",
                category="mujoco",
                message=f"MuJoCo load failed: {mujoco_error}"
            ))

        return self._create_result(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            mujoco_loadable=mujoco_loadable,
            mujoco_error=mujoco_error
        )

    def _validate_structure(self) -> List[URDFValidationIssue]:
        """验证基础结构"""
        issues = []

        # 检查根元素
        if self.root.tag != 'robot':
            issues.append(URDFValidationIssue(
                level="error",
                category="structure",
                message="Root element must be 'robot'"
            ))

        # 检查 robot name
        if 'name' not in self.root.attrib:
            issues.append(URDFValidationIssue(
                level="warning",
                category="structure",
                message="Robot has no 'name' attribute"
            ))

        # 检查是否有 links
        links = self.root.findall('link')
        if len(links) == 0:
            issues.append(URDFValidationIssue(
                level="error",
                category="structure",
                message="No links found in URDF"
            ))

        # 检查是否有 joints
        joints = self.root.findall('joint')
        if len(joints) == 0:
            issues.append(URDFValidationIssue(
                level="warning",
                category="structure",
                message="No joints found in URDF (single-body robot?)"
            ))

        return issues

    def _validate_links(self) -> List[URDFValidationIssue]:
        """验证 links"""
        issues = []
        links = self.root.findall('link')

        link_names = set()
        for link in links:
            link_name = link.get('name')

            # 检查重复名称
            if link_name in link_names:
                issues.append(URDFValidationIssue(
                    level="error",
                    category="link",
                    message=f"Duplicate link name: {link_name}"
                ))
            link_names.add(link_name)

            # 检查 inertial
            inertial = link.find('inertial')
            if inertial is None:
                issues.append(URDFValidationIssue(
                    level="warning",
                    category="link",
                    message=f"Link '{link_name}' has no inertial properties",
                    location=link_name
                ))
            else:
                # 检查质量
                mass_elem = inertial.find('mass')
                if mass_elem is not None:
                    mass_value = float(mass_elem.get('value', 0))
                    if mass_value <= 0:
                        issues.append(URDFValidationIssue(
                            level="warning",
                            category="link",
                            message=f"Link '{link_name}' has zero or negative mass",
                            location=link_name
                        ))

        return issues

    def _validate_joints(self) -> List[URDFValidationIssue]:
        """验证 joints"""
        issues = []
        joints = self.root.findall('joint')
        links = {link.get('name') for link in self.root.findall('link')}

        joint_names = set()
        for joint in joints:
            joint_name = joint.get('name')
            joint_type = joint.get('type')

            # 检查重复名称
            if joint_name in joint_names:
                issues.append(URDFValidationIssue(
                    level="error",
                    category="joint",
                    message=f"Duplicate joint name: {joint_name}"
                ))
            joint_names.add(joint_name)

            # 检查 parent/child
            parent = joint.find('parent')
            child = joint.find('child')

            if parent is None:
                issues.append(URDFValidationIssue(
                    level="error",
                    category="joint",
                    message=f"Joint '{joint_name}' has no parent",
                    location=joint_name
                ))
            elif parent.get('link') not in links:
                issues.append(URDFValidationIssue(
                    level="error",
                    category="joint",
                    message=f"Joint '{joint_name}' parent link not found: {parent.get('link')}",
                    location=joint_name
                ))

            if child is None:
                issues.append(URDFValidationIssue(
                    level="error",
                    category="joint",
                    message=f"Joint '{joint_name}' has no child",
                    location=joint_name
                ))
            elif child.get('link') not in links:
                issues.append(URDFValidationIssue(
                    level="error",
                    category="joint",
                    message=f"Joint '{joint_name}' child link not found: {child.get('link')}",
                    location=joint_name
                ))

            # 检查关节类型
            valid_types = ['revolute', 'continuous', 'prismatic', 'fixed', 'floating', 'planar']
            if joint_type not in valid_types:
                issues.append(URDFValidationIssue(
                    level="error",
                    category="joint",
                    message=f"Joint '{joint_name}' has invalid type: {joint_type}",
                    location=joint_name
                ))

            # 检查关节限位（revolute/prismatic）
            if joint_type in ['revolute', 'prismatic']:
                limit = joint.find('limit')
                if limit is None:
                    issues.append(URDFValidationIssue(
                        level="warning",
                        category="joint",
                        message=f"Joint '{joint_name}' ({joint_type}) has no limits",
                        location=joint_name
                    ))
                else:
                    lower = float(limit.get('lower', 0))
                    upper = float(limit.get('upper', 0))
                    if lower >= upper:
                        issues.append(URDFValidationIssue(
                            level="error",
                            category="joint",
                            message=f"Joint '{joint_name}' has invalid limits: lower >= upper",
                            location=joint_name
                        ))

        return issues

    def _validate_meshes(self) -> List[URDFValidationIssue]:
        """验证 mesh 文件"""
        issues = []

        # 查找所有 mesh 引用
        for geometry in self.root.findall('.//geometry/mesh'):
            filename = geometry.get('filename')
            if filename:
                # 处理 package:// 和相对路径
                mesh_path = self._resolve_mesh_path(filename)

                if not mesh_path.exists():
                    issues.append(URDFValidationIssue(
                        level="error",
                        category="mesh",
                        message=f"Mesh file not found: {filename}"
                    ))

        return issues

    def _validate_mass_properties(self) -> List[URDFValidationIssue]:
        """验证质量属性"""
        issues = []

        total_mass = 0.0
        links_with_mass = 0

        for link in self.root.findall('link'):
            link_name = link.get('name')
            inertial = link.find('inertial')

            if inertial is not None:
                mass_elem = inertial.find('mass')
                if mass_elem is not None:
                    mass = float(mass_elem.get('value', 0))
                    if mass > 0:
                        total_mass += mass
                        links_with_mass += 1

        issues.append(URDFValidationIssue(
            level="info",
            category="mass",
            message=f"Total mass: {total_mass:.2f} kg ({links_with_mass} links with mass)"
        ))

        if total_mass < 1.0:
            issues.append(URDFValidationIssue(
                level="warning",
                category="mass",
                message=f"Total mass seems very low: {total_mass:.2f} kg"
            ))

        if total_mass > 1000.0:
            issues.append(URDFValidationIssue(
                level="warning",
                category="mass",
                message=f"Total mass seems very high: {total_mass:.2f} kg"
            ))

        return issues

    def _test_mujoco_load(self) -> Tuple[bool, str]:
        """测试 MuJoCo 加载"""
        try:
            import mujoco
            model = mujoco.MjModel.from_xml_path(str(self.urdf_path))
            return True, ""
        except ImportError:
            return False, "MuJoCo not installed"
        except Exception as e:
            return False, str(e)

    def _resolve_mesh_path(self, filename: str) -> Path:
        """解析 mesh 路径"""
        if filename.startswith('package://'):
            # 简化处理：移除 package:// 前缀
            filename = filename.replace('package://', '')
            return self.urdf_dir / filename
        elif filename.startswith('file://'):
            return Path(filename.replace('file://', ''))
        else:
            return self.urdf_dir / filename

    def _create_result(
        self,
        valid: bool,
        errors: List[URDFValidationIssue],
        warnings: List[URDFValidationIssue],
        info: List[URDFValidationIssue],
        mujoco_loadable: bool = False,
        mujoco_error: str = ""
    ) -> URDFValidationResult:
        """创建验证结果"""

        # 统计信息
        num_links = len(self.root.findall('link')) if self.root is not None else 0
        num_joints = len(self.root.findall('joint')) if self.root is not None else 0

        # 统计驱动关节（非 fixed）
        num_actuated = 0
        if self.root is not None:
            for joint in self.root.findall('joint'):
                if joint.get('type') != 'fixed':
                    num_actuated += 1

        # 计算总质量
        total_mass = 0.0
        if self.root is not None:
            for link in self.root.findall('link'):
                inertial = link.find('inertial')
                if inertial is not None:
                    mass_elem = inertial.find('mass')
                    if mass_elem is not None:
                        total_mass += float(mass_elem.get('value', 0))

        return URDFValidationResult(
            valid=valid,
            urdf_path=str(self.urdf_path),
            num_links=num_links,
            num_joints=num_joints,
            num_actuated_joints=num_actuated,
            total_mass=total_mass,
            errors=errors,
            warnings=warnings,
            info=info,
            mujoco_loadable=mujoco_loadable,
            mujoco_error=mujoco_error
        )


# ========== 便捷函数 ==========

def validate_urdf(urdf_path: str) -> URDFValidationResult:
    """验证 URDF 文件"""
    validator = URDFValidator(urdf_path)
    return validator.validate()


if __name__ == "__main__":
    # 测试
    import sys

    if len(sys.argv) > 1:
        urdf_path = sys.argv[1]
    else:
        urdf_path = "assets/go2_description/urdf/go2.urdf"

    print(f"Validating: {urdf_path}")
    print()

    result = validate_urdf(urdf_path)

    print(result.summary())
    print()
    print(f"Links: {result.num_links}")
    print(f"Joints: {result.num_joints} ({result.num_actuated_joints} actuated)")
    print(f"Total mass: {result.total_mass:.2f} kg")
    print(f"MuJoCo loadable: {result.mujoco_loadable}")
    print()

    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  [{error.category}] {error.message}")
        print()

    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  [{warning.category}] {warning.message}")
        print()

    if result.info:
        print("Info:")
        for item in result.info:
            print(f"  [{item.category}] {item.message}")
