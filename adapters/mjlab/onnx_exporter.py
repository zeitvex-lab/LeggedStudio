"""
ONNX Exporter
基于 Microduck RL 和 RC_WheelLeg 的 ONNX 导出经验
"""

import torch
import onnx
import onnxruntime as ort
import numpy as np
from pathlib import Path
from typing import Tuple, Optional
from dataclasses import dataclass
import time


@dataclass
class ExportResult:
    """导出结果"""
    success: bool
    onnx_path: str
    max_numerical_diff: float
    opset_version: int
    input_shape: list
    output_shape: list
    inference_time_ms: float
    error_message: str = ""


def attach_metadata_to_onnx(onnx_path: str, metadata: dict) -> None:
    """把部署契约作为 metadata_props 盖章进 ONNX（键名与 mjlab exporter 对齐）。

    浏览器 sim2sim 加载策略时读取同一组键做契约校验：
    joint_names / joint_stiffness / joint_damping / default_joint_pos /
    command_names / observation_names / action_scale / clip_actions / run_path
    """
    model = onnx.load(onnx_path)
    for k, v in metadata.items():
        entry = onnx.StringStringEntryProto()
        entry.key = k
        entry.value = ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)
        model.metadata_props.append(entry)
    onnx.save(model, onnx_path)


class ONNXExporter:
    """
    ONNX 导出器
    确保数值一致性和高性能推理
    """

    def __init__(self, opset_version: int = 17):
        self.opset_version = opset_version

    def export(
        self,
        model: torch.nn.Module,
        dummy_input: torch.Tensor,
        output_path: str,
        input_names: list = None,
        output_names: list = None,
        dynamic_axes: dict = None,
        metadata: dict = None
    ) -> ExportResult:
        """
        导出 ONNX 模型并验证

        Args:
            model: PyTorch 模型
            dummy_input: 示例输入 (batch_size, obs_dim)
            output_path: 输出路径
            input_names: 输入名称列表
            output_names: 输出名称列表
            dynamic_axes: 动态轴配置

        Returns:
            ExportResult: 导出结果
        """
        try:
            # 默认参数
            if input_names is None:
                input_names = ['observation']
            if output_names is None:
                output_names = ['action']
            if dynamic_axes is None:
                dynamic_axes = {
                    'observation': {0: 'batch_size'},
                    'action': {0: 'batch_size'}
                }

            print("[Exporter] Exporting to ONNX...")

            # 确保模型在评估模式
            model.eval()

            # 导出
            with torch.no_grad():
                torch.onnx.export(
                    model,
                    dummy_input,
                    output_path,
                    export_params=True,
                    opset_version=self.opset_version,
                    do_constant_folding=True,
                    input_names=input_names,
                    output_names=output_names,
                    dynamic_axes=dynamic_axes,
                    verbose=False
                )

            print(f"[Exporter] ONNX model saved: {output_path}")

            # 部署契约盖章（joint_names/增益/默认角/clip 等），浏览器加载时校验
            if metadata:
                attach_metadata_to_onnx(output_path, metadata)
                print(f"[Exporter] Metadata stamped: {sorted(metadata.keys())}")

            # 验证模型
            print("[Exporter] Validating ONNX model...")
            onnx_model = onnx.load(output_path)
            onnx.checker.check_model(onnx_model)
            print("[Exporter] ONNX model is valid")

            # 数值一致性验证
            print("[Exporter] Testing numerical consistency...")
            max_diff = self._test_numerical_consistency(
                model,
                output_path,
                dummy_input
            )

            print(f"[Exporter] Max numerical diff: {max_diff:.2e}")

            if max_diff > 1e-4:
                print(f"[Exporter] Warning: Large numerical difference detected!")

            # 性能测试
            print("[Exporter] Testing inference speed...")
            inference_time = self._test_inference_speed(
                output_path,
                dummy_input
            )

            print(f"[Exporter] Inference time: {inference_time:.2f} ms")

            # 获取输入输出形状
            input_shape = list(dummy_input.shape)
            output_shape = list(model(dummy_input).shape)

            return ExportResult(
                success=True,
                onnx_path=output_path,
                max_numerical_diff=max_diff,
                opset_version=self.opset_version,
                input_shape=input_shape,
                output_shape=output_shape,
                inference_time_ms=inference_time
            )

        except Exception as e:
            print(f"[Exporter] Export failed: {e}")
            import traceback
            traceback.print_exc()

            return ExportResult(
                success=False,
                onnx_path=output_path,
                max_numerical_diff=0.0,
                opset_version=self.opset_version,
                input_shape=[],
                output_shape=[],
                inference_time_ms=0.0,
                error_message=str(e)
            )

    def _test_numerical_consistency(
        self,
        torch_model: torch.nn.Module,
        onnx_path: str,
        test_input: torch.Tensor,
        num_tests: int = 10
    ) -> float:
        """测试数值一致性"""
        max_diffs = []

        # 创建 ONNX Runtime 会话
        ort_session = ort.InferenceSession(
            onnx_path,
            providers=['CPUExecutionProvider']
        )

        with torch.no_grad():
            for _ in range(num_tests):
                # 生成随机输入
                random_input = torch.randn_like(test_input)

                # PyTorch 推理
                torch_output = torch_model(random_input).cpu().numpy()

                # ONNX 推理
                ort_inputs = {ort_session.get_inputs()[0].name: random_input.numpy()}
                ort_output = ort_session.run(None, ort_inputs)[0]

                # 计算差异
                diff = np.abs(torch_output - ort_output).max()
                max_diffs.append(diff)

        return max(max_diffs)

    def _test_inference_speed(
        self,
        onnx_path: str,
        test_input: torch.Tensor,
        num_runs: int = 100
    ) -> float:
        """测试推理速度（毫秒）"""
        # 创建会话
        ort_session = ort.InferenceSession(
            onnx_path,
            providers=['CPUExecutionProvider']
        )

        input_name = ort_session.get_inputs()[0].name
        ort_input = {input_name: test_input.numpy()}

        # 预热
        for _ in range(10):
            ort_session.run(None, ort_input)

        # 计时
        start_time = time.time()
        for _ in range(num_runs):
            ort_session.run(None, ort_input)
        end_time = time.time()

        avg_time_ms = (end_time - start_time) / num_runs * 1000

        return avg_time_ms

    def export_with_normalizer(
        self,
        policy_model: torch.nn.Module,
        obs_mean: np.ndarray,
        obs_std: np.ndarray,
        output_path: str,
        obs_dim: int
    ) -> ExportResult:
        """
        导出包含 normalizer 的模型
        参考 Microduck RL 的做法
        """

        class PolicyWithNormalizer(torch.nn.Module):
            def __init__(self, policy, obs_mean, obs_std):
                super().__init__()
                self.policy = policy
                self.register_buffer('obs_mean', torch.tensor(obs_mean, dtype=torch.float32))
                self.register_buffer('obs_std', torch.tensor(obs_std, dtype=torch.float32))

            def forward(self, obs):
                # 归一化
                obs_normalized = (obs - self.obs_mean) / (self.obs_std + 1e-8)
                # 推理
                action = self.policy(obs_normalized)
                return action

        # 创建包含 normalizer 的模型
        wrapped_model = PolicyWithNormalizer(
            policy_model,
            obs_mean,
            obs_std
        )

        wrapped_model.eval()

        # 导出
        dummy_input = torch.randn(1, obs_dim)
        return self.export(
            model=wrapped_model,
            dummy_input=dummy_input,
            output_path=output_path
        )


# ========== 便捷函数 ==========

def export_policy_to_onnx(
    model_path: str,
    onnx_output_path: str,
    obs_dim: int,
    act_dim: int,
    obs_mean: Optional[np.ndarray] = None,
    obs_std: Optional[np.ndarray] = None
) -> ExportResult:
    """
    从 PyTorch 模型文件导出 ONNX

    Args:
        model_path: PyTorch 模型路径 (.pt)
        onnx_output_path: ONNX 输出路径
        obs_dim: 观测维度
        act_dim: 动作维度
        obs_mean: 观测均值（可选）
        obs_std: 观测标准差（可选）

    Returns:
        ExportResult
    """
    # 加载模型
    checkpoint = torch.load(model_path, map_location='cpu')

    # TODO: 根据实际模型结构加载
    # model = ActorCritic(obs_dim, act_dim)
    # model.load_state_dict(checkpoint['model_state_dict'])

    # 临时：创建简单模型用于测试
    model = torch.nn.Sequential(
        torch.nn.Linear(obs_dim, 128),
        torch.nn.ReLU(),
        torch.nn.Linear(128, 128),
        torch.nn.ReLU(),
        torch.nn.Linear(128, act_dim),
        torch.nn.Tanh()
    )

    exporter = ONNXExporter()

    # 如果有 normalizer，包含进去
    if obs_mean is not None and obs_std is not None:
        return exporter.export_with_normalizer(
            policy_model=model,
            obs_mean=obs_mean,
            obs_std=obs_std,
            output_path=onnx_output_path,
            obs_dim=obs_dim
        )
    else:
        dummy_input = torch.randn(1, obs_dim)
        return exporter.export(
            model=model,
            dummy_input=dummy_input,
            output_path=onnx_output_path
        )


if __name__ == "__main__":
    # 测试
    print("Testing ONNX Exporter...")

    # 创建简单模型
    obs_dim = 48
    act_dim = 12

    model = torch.nn.Sequential(
        torch.nn.Linear(obs_dim, 128),
        torch.nn.ReLU(),
        torch.nn.Linear(128, 128),
        torch.nn.ReLU(),
        torch.nn.Linear(128, act_dim),
        torch.nn.Tanh()
    )

    # 导出
    exporter = ONNXExporter()
    dummy_input = torch.randn(1, obs_dim)

    result = exporter.export(
        model=model,
        dummy_input=dummy_input,
        output_path="outputs/test_policy.onnx"
    )

    print("\nExport Result:")
    print(f"  Success: {result.success}")
    print(f"  Max diff: {result.max_numerical_diff:.2e}")
    print(f"  Inference time: {result.inference_time_ms:.2f} ms")
    print(f"  Input shape: {result.input_shape}")
    print(f"  Output shape: {result.output_shape}")
