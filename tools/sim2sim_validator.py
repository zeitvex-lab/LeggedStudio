"""
Sim2Sim Validator
跨仿真器验证工具（参考 RoboGauge 和 RC_WheelLeg）

K3 起本文件的**字段一致性守卫**不再自成一套：与导出闸门共用
``backend.contract_adjudicator``（``backend.export_gate.sim2sim_contract_guard``），
因此"训练 → 部署"和"训练 → 另一引擎"两条链路对同一份契约差异给出**同一处置**。

注意：``Sim2SimValidator._test_in_env`` 目前仍是占位实现（返回模拟数值），
跨引擎的真实 episode 运行属 K6；本文件当前**可用于**的是契约守卫
（:func:`guard_contract_consistency`）与结果落档（``create_sim2sim_result``）。
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np

from contracts.contract_legacy_v2 import ContractLegacyV2
from contracts.policy_artifact import PolicyArtifact, Sim2SimResult


def _as_dict(contract: Any) -> Dict[str, Any]:
    """把契约对象转成可裁决的 dict（兼容 pydantic 模型 / 自定义 to_dict / 原始 dict）。"""
    if isinstance(contract, dict):
        return contract
    for attribute in ("model_dump", "to_dict", "dict"):
        method = getattr(contract, attribute, None)
        if callable(method):
            try:
                value = method()
            except Exception:  # pragma: no cover - 转换失败即视为不可裁决
                continue
            if isinstance(value, dict):
                return value
    raise TypeError(f"无法把 {type(contract).__name__} 转成 dict 用于契约裁决")


def guard_contract_consistency(
    source_snapshot: Dict[str, Any], target_contract: Any
) -> Dict[str, Any]:
    """跨引擎字段守卫（K3）：与导出闸门同一实现，仅 ``context`` 为 ``sim2sim``。

    Returns:
        裁决报告 ``{ok, disposition, entries, blockers, warnings, context, counts}``；
        每条目含 **字段 / 源值 / 目标值 / 处置 / 依据**。
    """
    from backend.export_gate import sim2sim_contract_guard

    return sim2sim_contract_guard(_as_dict(source_snapshot), _as_dict(target_contract))


@dataclass
class Sim2SimTestResult:
    """Sim2Sim 测试结果"""
    source_env: str
    target_env: str

    # 源环境性能
    source_success_rate: float
    source_avg_reward: float
    source_avg_velocity: float

    # 目标环境性能
    target_success_rate: float
    target_avg_reward: float
    target_avg_velocity: float

    # 性能下降
    success_rate_drop: float  # (source - target) / source
    reward_drop: float
    velocity_drop: float

    # 总体评估
    passed: bool
    threshold: float = 0.15  # 15% 性能下降阈值

    # 修复（2026-09-13）：原本 `tested_at: datetime` 跟在默认参数之后，dataclass 会在
    # **导入模块时**直接抛 TypeError（non-default argument follows default argument），
    # 也就是本文件此前根本 import 不了——给了默认值即修复，同时保留"不传就是此刻"。
    tested_at: datetime = field(default_factory=datetime.now)


class Sim2SimValidator:
    """
    Sim2Sim 验证器
    测试策略在不同仿真器间的迁移性能
    """

    def __init__(
        self,
        contract: ContractLegacyV2,
        performance_threshold: float = 0.15
    ):
        """
        Args:
            contract: Robot Contract
            performance_threshold: 可接受的性能下降阈值（例如 0.15 = 15%）
        """
        self.contract = contract
        self.performance_threshold = performance_threshold

    def contract_guard(self, source_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """跨引擎字段守卫（K3）：训练快照 vs 本验证器持有的目标契约。

        与导出闸门共用 ``backend.contract_adjudicator``，所以同一份契约差异在两条
        链路上得到同一个处置（deny / warn / allow）。
        """
        return guard_contract_consistency(source_snapshot, self.contract)

    def validate(
        self,
        artifact: PolicyArtifact,
        source_env: str = "mjlab",
        target_env: str = "mujoco",
        num_episodes: int = 50,
        contract_snapshot: Optional[Dict[str, Any]] = None
    ) -> Sim2SimTestResult:
        """
        执行 Sim2Sim 验证

        Args:
            artifact: Policy Artifact
            source_env: 源环境（训练环境）
            target_env: 目标环境（迁移环境）
            num_episodes: 测试 episode 数
            contract_snapshot: 训练时的契约快照；提供时先跑跨引擎字段守卫（K3），
                裁决为 deny 直接拒绝——字段都对不上就谈不上"跨引擎性能"。

        Returns:
            Sim2SimTestResult
        """
        if contract_snapshot is not None:
            guard = self.contract_guard(contract_snapshot)
            if not guard["ok"]:
                raise ValueError(
                    "跨引擎契约守卫拒绝（K3，fail-closed）：\n" + "\n".join(guard["blockers"])
                )
            print(f"[Sim2Sim] Contract guard passed ({guard['counts']})")
        print(f"[Sim2Sim] Validating: {artifact.artifact_id}")
        print(f"[Sim2Sim] Source: {source_env} → Target: {target_env}")
        print(f"[Sim2Sim] Running {num_episodes} episodes in each environment...")

        # 在源环境中测试
        print(f"\n[Sim2Sim] Testing in source environment ({source_env})...")
        source_metrics = self._test_in_env(artifact, source_env, num_episodes)

        # 在目标环境中测试
        print(f"[Sim2Sim] Testing in target environment ({target_env})...")
        target_metrics = self._test_in_env(artifact, target_env, num_episodes)

        # 计算性能下降
        success_drop = (source_metrics["success_rate"] - target_metrics["success_rate"]) / source_metrics["success_rate"] if source_metrics["success_rate"] > 0 else 0
        reward_drop = (source_metrics["avg_reward"] - target_metrics["avg_reward"]) / abs(source_metrics["avg_reward"]) if source_metrics["avg_reward"] != 0 else 0
        velocity_drop = (source_metrics["avg_velocity"] - target_metrics["avg_velocity"]) / source_metrics["avg_velocity"] if source_metrics["avg_velocity"] > 0 else 0

        # 判断是否通过（主要看成功率下降）
        passed = success_drop <= self.performance_threshold

        result = Sim2SimTestResult(
            source_env=source_env,
            target_env=target_env,
            source_success_rate=source_metrics["success_rate"],
            source_avg_reward=source_metrics["avg_reward"],
            source_avg_velocity=source_metrics["avg_velocity"],
            target_success_rate=target_metrics["success_rate"],
            target_avg_reward=target_metrics["avg_reward"],
            target_avg_velocity=target_metrics["avg_velocity"],
            success_rate_drop=success_drop,
            reward_drop=reward_drop,
            velocity_drop=velocity_drop,
            passed=passed,
            threshold=self.performance_threshold,
            tested_at=datetime.now()
        )

        # 打印结果
        print(f"\n[Sim2Sim] Results:")
        print(f"  Source success rate: {source_metrics['success_rate'] * 100:.1f}%")
        print(f"  Target success rate: {target_metrics['success_rate'] * 100:.1f}%")
        print(f"  Performance drop: {success_drop * 100:.1f}%")
        print(f"  Status: {'✓ PASSED' if passed else '✗ FAILED'} (threshold: {self.performance_threshold * 100:.1f}%)")

        return result

    def _test_in_env(
        self,
        artifact: PolicyArtifact,
        env_name: str,
        num_episodes: int
    ) -> Dict[str, float]:
        """在指定环境中测试策略"""

        # TODO: 实际创建环境并运行策略
        # 这里需要根据 env_name 创建对应的环境
        # if env_name == "mjlab":
        #     env = create_mjlab_env(self.contract)
        # elif env_name == "mujoco":
        #     env = create_mujoco_env(self.contract)

        # 临时：模拟结果
        if env_name == "mjlab":
            # 源环境（训练环境）- 性能较好
            success_rate = 0.85 + np.random.rand() * 0.05
            avg_reward = 150.0 + np.random.randn() * 10.0
            avg_velocity = 1.5 + np.random.randn() * 0.1
        else:
            # 目标环境 - 通常有 5-10% 的性能下降
            success_rate = 0.78 + np.random.rand() * 0.05
            avg_reward = 135.0 + np.random.randn() * 10.0
            avg_velocity = 1.4 + np.random.randn() * 0.1

        return {
            "success_rate": success_rate,
            "avg_reward": avg_reward,
            "avg_velocity": avg_velocity
        }

    def create_sim2sim_result(
        self,
        test_result: Sim2SimTestResult
    ) -> Sim2SimResult:
        """转换为 Policy Artifact 的 Sim2SimResult 格式"""
        return Sim2SimResult(
            source_env=test_result.source_env,
            target_env=test_result.target_env,
            source_success_rate=test_result.source_success_rate,
            target_success_rate=test_result.target_success_rate,
            performance_drop=test_result.success_rate_drop,
            tested_at=test_result.tested_at
        )


# ========== 便捷函数 ==========

def validate_sim2sim(
    artifact: PolicyArtifact,
    contract: ContractLegacyV2,
    source_env: str = "mjlab",
    target_env: str = "mujoco",
    num_episodes: int = 50,
    threshold: float = 0.15
) -> Sim2SimTestResult:
    """
    验证 Sim2Sim 性能

    Args:
        artifact: Policy Artifact
        contract: Robot Contract
        source_env: 源环境
        target_env: 目标环境
        num_episodes: 测试 episode 数
        threshold: 性能下降阈值

    Returns:
        Sim2SimTestResult
    """
    validator = Sim2SimValidator(contract, performance_threshold=threshold)
    return validator.validate(artifact, source_env, target_env, num_episodes)


if __name__ == "__main__":
    # 测试
    from contracts.contract_legacy_v2 import create_go2_contract
    from contracts.policy_artifact import create_artifact_from_training, TrainingMetrics

    # 创建测试数据
    contract = create_go2_contract()
    artifact = create_artifact_from_training(
        contract=contract,
        task_name="forward_walk",
        algorithm="PPO",
        model_path="outputs/test_model.pt",
        metrics=TrainingMetrics(
            iterations=1000,
            episodes=4096,
            success_rate=0.85,
            avg_reward=150.0,
            final_reward=180.0,
            training_duration_seconds=7200
        )
    )

    # 验证 Sim2Sim
    validator = Sim2SimValidator(contract, performance_threshold=0.15)
    result = validator.validate(
        artifact=artifact,
        source_env="mjlab",
        target_env="mujoco",
        num_episodes=10
    )

    print("\n" + "=" * 50)
    print("Sim2Sim Validation Result:")
    print("=" * 50)
    print(f"Source: {result.source_env}")
    print(f"  Success rate: {result.source_success_rate * 100:.1f}%")
    print(f"  Avg reward: {result.source_avg_reward:.2f}")
    print(f"\nTarget: {result.target_env}")
    print(f"  Success rate: {result.target_success_rate * 100:.1f}%")
    print(f"  Avg reward: {result.target_avg_reward:.2f}")
    print(f"\nPerformance Drop: {result.success_rate_drop * 100:.1f}%")
    print(f"Status: {'✓ PASSED' if result.passed else '✗ FAILED'}")
