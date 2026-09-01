"""
Robot Contract Validator
验证 Contract 的完整性和正确性
"""

from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
import hashlib
import xml.etree.ElementTree as ET

from contracts.robot_contract_v2 import RobotContractV2
from contracts.asset_paths import resolve_asset_path


@dataclass
class ValidationError:
    """验证错误"""
    level: str  # "error" / "warning"
    category: str  # "urdf" / "joints" / "dimensions" / "control"
    message: str
    field: str = ""


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def summary(self) -> str:
        if self.valid:
            return f"✓ Valid ({len(self.warnings)} warnings)"
        return f"✗ Invalid ({len(self.errors)} errors, {len(self.warnings)} warnings)"


class RobotContractValidator:
    """Contract 验证器"""

    def validate(self, contract: RobotContractV2) -> ValidationResult:
        """完整验证"""
        errors = []
        warnings = []

        # 1. URDF 验证
        errors.extend(self._validate_urdf(contract))

        # 2. 关节验证
        errors.extend(self._validate_joints(contract))

        # 3. 维度一致性
        errors.extend(self._validate_dimensions(contract))

        # 4. 控制参数
        warnings.extend(self._validate_control(contract))

        # 5. 部署映射（如果存在）
        if contract.deployment:
            warnings.extend(self._validate_deployment(contract))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def _validate_urdf(self, contract: RobotContractV2) -> List[ValidationError]:
        """验证 URDF 文件"""
        errors = []
        urdf_path = resolve_asset_path(contract.urdf.path)

        # 检查文件存在
        if not urdf_path.exists():
            errors.append(ValidationError(
                level="error",
                category="urdf",
                message=f"URDF file not found: {urdf_path}",
                field="urdf.path"
            ))
            return errors

        # 检查哈希
        try:
            actual_hash = self._compute_file_hash(urdf_path)
            if contract.urdf.hash and actual_hash != contract.urdf.hash:
                errors.append(ValidationError(
                    level="error",
                    category="urdf",
                    message=f"URDF hash mismatch (expected: {contract.urdf.hash[:8]}..., got: {actual_hash[:8]}...)",
                    field="urdf.hash"
                ))
        except Exception as e:
            errors.append(ValidationError(
                level="error",
                category="urdf",
                message=f"Failed to compute URDF hash: {e}",
                field="urdf.hash"
            ))

        # 解析 URDF 并验证关节
        try:
            tree = ET.parse(urdf_path)
            root = tree.getroot()

            # 提取所有关节名称
            urdf_joints = [joint.get('name') for joint in root.findall('.//joint')]

            # 检查 Contract 中的关节是否存在于 URDF
            for joint_name in contract.joints.actuated_joints:
                if joint_name not in urdf_joints:
                    errors.append(ValidationError(
                        level="error",
                        category="urdf",
                        message=f"Actuated joint '{joint_name}' not found in URDF",
                        field="joints.actuated_joints"
                    ))

            for joint_name in contract.joints.passive_joints:
                if joint_name not in urdf_joints:
                    errors.append(ValidationError(
                        level="error",
                        category="urdf",
                        message=f"Passive joint '{joint_name}' not found in URDF",
                        field="joints.passive_joints"
                    ))

        except Exception as e:
            errors.append(ValidationError(
                level="error",
                category="urdf",
                message=f"Failed to parse URDF: {e}",
                field="urdf.path"
            ))

        return errors

    def _validate_joints(self, contract: RobotContractV2) -> List[ValidationError]:
        """验证关节配置"""
        errors = []

        # 检查关节数量
        num_actuated = len(contract.joints.actuated_joints)

        # 检查 action_dim 匹配
        if contract.action.dimension != num_actuated:
            errors.append(ValidationError(
                level="error",
                category="joints",
                message=f"Action dimension ({contract.action.dimension}) doesn't match actuated joints count ({num_actuated})",
                field="action.dimension"
            ))

        # 检查 joint_order 匹配
        if len(contract.action.joint_order) != num_actuated:
            errors.append(ValidationError(
                level="error",
                category="joints",
                message=f"Joint order length ({len(contract.action.joint_order)}) doesn't match actuated joints count ({num_actuated})",
                field="action.joint_order"
            ))

        # 检查 joint_order 中的关节是否都在 actuated_joints 中
        actuated_set = set(contract.joints.actuated_joints)
        for joint_name in contract.action.joint_order:
            if joint_name not in actuated_set:
                errors.append(ValidationError(
                    level="error",
                    category="joints",
                    message=f"Joint '{joint_name}' in joint_order is not in actuated_joints",
                    field="action.joint_order"
                ))

        # 检查 default_pose 长度
        if len(contract.joints.default_pose) != num_actuated:
            errors.append(ValidationError(
                level="error",
                category="joints",
                message=f"Default pose length ({len(contract.joints.default_pose)}) doesn't match actuated joints count ({num_actuated})",
                field="joints.default_pose"
            ))

        return errors

    def _validate_dimensions(self, contract: RobotContractV2) -> List[ValidationError]:
        """验证维度一致性"""
        errors = []

        # 观测维度合理性检查（粗略）
        min_obs_dim = len(contract.joints.actuated_joints) * 2  # 至少 pos + vel
        if contract.observation.dimension < min_obs_dim:
            errors.append(ValidationError(
                level="error",
                category="dimensions",
                message=f"Observation dimension ({contract.observation.dimension}) seems too small (minimum expected: {min_obs_dim})",
                field="observation.dimension"
            ))

        return errors

    def _validate_control(self, contract: RobotContractV2) -> List[ValidationError]:
        """验证控制参数"""
        warnings = []

        # 检查控制频率合理性
        if contract.control.control_hz < 20:
            warnings.append(ValidationError(
                level="warning",
                category="control",
                message=f"Control frequency ({contract.control.control_hz} Hz) is very low",
                field="control.control_hz"
            ))

        if contract.control.control_hz > 100:
            warnings.append(ValidationError(
                level="warning",
                category="control",
                message=f"Control frequency ({contract.control.control_hz} Hz) is very high",
                field="control.control_hz"
            ))

        # 检查 physics_hz 合理性
        if contract.control.physics_hz < 500:
            warnings.append(ValidationError(
                level="warning",
                category="control",
                message=f"Physics frequency ({contract.control.physics_hz} Hz) is low for legged robots",
                field="control.physics_hz"
            ))

        return warnings

    def _validate_deployment(self, contract: RobotContractV2) -> List[ValidationError]:
        """验证部署映射"""
        warnings = []

        if contract.deployment and contract.deployment.can_bus_mapping:
            # 检查所有驱动关节是否都有 CAN ID 映射
            for joint_name in contract.joints.actuated_joints:
                if joint_name not in contract.deployment.can_bus_mapping:
                    warnings.append(ValidationError(
                        level="warning",
                        category="deployment",
                        message=f"Joint '{joint_name}' has no CAN bus mapping",
                        field="deployment.can_bus_mapping"
                    ))

        return warnings

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """计算文件的 SHA-256 哈希"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()


# ========== 便捷函数 ==========

def validate_contract(contract: RobotContractV2) -> ValidationResult:
    """验证 Contract"""
    validator = RobotContractValidator()
    return validator.validate(contract)


def validate_contract_file(contract_path: str) -> ValidationResult:
    """验证 Contract 文件"""
    contract = RobotContractV2.from_json_file(contract_path)
    return validate_contract(contract)


if __name__ == "__main__":
    # 测试
    from contracts.robot_contract_v2 import create_go2_contract

    contract = create_go2_contract()
    result = validate_contract(contract)

    print("Validation Result:")
    print(result.summary())
    print()

    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - [{error.category}] {error.message}")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - [{warning.category}] {warning.message}")
