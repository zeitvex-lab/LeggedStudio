"""
Robot Contract Validator
验证 Contract 的完整性和正确性
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List
from dataclasses import dataclass
import hashlib
import xml.etree.ElementTree as ET

from contracts.contract_legacy_v2 import ContractLegacyV2
from contracts.asset_paths import resolve_asset_path


def normalize_line_endings(data: bytes) -> bytes:
    """CRLF → LF。归一规则全仓只此一份实现（B39 口径：一个工件只有一个哈希）。

    为什么不做原始字节：同一份资产在 Windows（CRLF 检出 / 文本写入）与 Linux/CI（LF 检出）
    会得到**两个**哈希，``urdf.hash`` 这类"模型有没有被改过"的判据一旦随平台漂移，
    就只剩下"在某一台机器上自洽"。归一化只动行尾，仍能检出内容改动
    （改一个字符哈希就变），不会掩盖模型漂移。
    实现上调用方必须**整份读入再归一**：分块读时 ``\\r\\n`` 可能恰好被切在两块之间，
    跨块的那一处会漏归一 —— 这种错随文件长度随机出现，最难查。
    """
    return data.replace(b"\r\n", b"\n")


def normalized_sha256(data: bytes) -> str:
    """规范化内容 SHA-256（CRLF → LF 后摘要）—— **单文件**摘要的唯一实现。

    ``pack_catalog`` / ``tools/generate_packs.py`` / ``policy_artifacts`` 等处此前各写一份
    （注释里靠"两侧必须同步修改"维系），现在全部委托到这里：口径是代码事实，不是口头约定。
    """
    return hashlib.sha256(normalize_line_endings(data)).hexdigest()


def package_digest(entries: Iterable[tuple[Path, bytes]]) -> str:
    """规范化**包内容**摘要：``(包内相对路径, 字节)`` 按路径排序后连路径一起摘要。

    与 :func:`normalized_sha256` 的区别只有"路径"这一维 —— 同一份字节放在不同路径是不同包，
    所以单独一个函数，而不是让调用方自己拼。

    三件必须同时成立的事（B39 口径：一个工件只有一个哈希）：

    * **上传与目录拷贝必须得到同一个 digest**：Web 走 base64 上传、CLI 走 ``onboard <dir>``
      目录拷贝，两条入口描述同一份资产，digest 不同就会产出两个包（幂等破坏）；
    * **排序键是包内相对路径**（``as_posix``），与调用方给的绝对路径无关；
    * **内容先 CRLF → LF 归一**（:func:`normalize_line_endings`）—— 不归一时，同一份资产在
      Windows（CRLF）与 CI（LF）得到两个 digest。**2026-09-19 实测**：本仓 4 个机器人包
      "归一 / 不归一"算出的值**全都不同**（包内是 OBJ 这类文本网格），所以"一边归一、
      一边不归一"的两处实现一旦被放到同一次比较里，就会把同一份内容判成两份。
    """

    digest = hashlib.sha256()
    for relative, data in sorted(entries, key=lambda pair: Path(pair[0]).as_posix()):
        digest.update(Path(relative).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(normalize_line_endings(data))
        digest.update(b"\0")
    return digest.hexdigest()


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

    def validate(self, contract: ContractLegacyV2) -> ValidationResult:
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

    def _validate_urdf(self, contract: ContractLegacyV2) -> List[ValidationError]:
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

    def _validate_joints(self, contract: ContractLegacyV2) -> List[ValidationError]:
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

    def _validate_dimensions(self, contract: ContractLegacyV2) -> List[ValidationError]:
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

    def _validate_control(self, contract: ContractLegacyV2) -> List[ValidationError]:
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

    def _validate_deployment(self, contract: ContractLegacyV2) -> List[ValidationError]:
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
        """计算文件的规范化 SHA-256（CRLF → LF）。规则与理由见模块级 ``normalized_sha256``。"""
        return normalized_sha256(Path(file_path).read_bytes())


# ========== 便捷函数 ==========

def validate_contract(contract: ContractLegacyV2) -> ValidationResult:
    """验证 Contract"""
    validator = RobotContractValidator()
    return validator.validate(contract)


def validate_contract_file(contract_path: str) -> ValidationResult:
    """验证 Contract 文件"""
    contract = ContractLegacyV2.from_json_file(contract_path)
    return validate_contract(contract)


if __name__ == "__main__":
    # 测试
    from contracts.contract_legacy_v2 import create_go2_contract

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
