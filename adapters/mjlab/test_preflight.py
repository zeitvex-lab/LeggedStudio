import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from .preflight import (
    GPU_MODE_CPU_ONLY,
    GPU_MODE_CUDA,
    GPU_MODE_UNAVAILABLE,
    build_report,
    gpu_probe,
    source_metadata,
)


class MjlabPreflightTests(unittest.TestCase):
    def test_workspace_source_metadata(self):
        report = build_report()
        self.assertEqual(report["schema_version"], "mjlab-preflight-1.0")
        self.assertEqual(report["python"]["target"], "3.12.x")
        self.assertEqual(report["mjlab_source"]["name"], "mjlab")
        self.assertEqual(report["mjlab_source"]["version"], "1.6.0")
        self.assertEqual(report["mjlab_source"]["upstream_python_default"], "3.13")
        self.assertTrue(report["baseline_ready"])
        self.assertEqual(report["ready"], all(report["runtime_checks"].values()))

    def test_missing_source_is_reported(self):
        with TemporaryDirectory() as directory:
            metadata = source_metadata(Path(directory) / "missing")
        self.assertFalse(metadata["exists"])
        self.assertNotIn("version", metadata)

    def test_report_exposes_three_state_device_mode(self):
        """体检报告必须给出设备三态，而不是一个容易误读的布尔。"""
        report = build_report()
        self.assertIn(report["device_mode"], {GPU_MODE_CUDA, GPU_MODE_CPU_ONLY, GPU_MODE_UNAVAILABLE})
        self.assertIn("cpu_training_ready", report)
        self.assertEqual(report["device_mode"], report["gpu"]["mode"])


def _no_gpu() -> dict:
    return {"available": False, "devices": [], "reason": "nvidia-smi not found"}


def _no_smi():
    """smi_probe 替身：宿主机无卡。不注入时 gpu_probe 走真 nvidia-smi，
    带卡开发机上"无 GPU"两态根本进不去（2026-09-29 实测判红）。"""
    return [], "nvidia-smi not found"


class GpuProbeTriStateTest(unittest.TestCase):
    """gpu_probe 的三态：cuda / cpu-only / unavailable。

    重点是区分"无 GPU 但 CPU 链路可用"与"无 GPU 且训练栈没装"——两者的处置
    完全不同（前者可跑冒烟，后者必须先供应环境）。
    """

    def test_stack_ready_without_gpu_is_cpu_only(self):
        probe = gpu_probe(torch_probe=lambda: {"available": True}, smi_probe=_no_smi)
        self.assertEqual(probe["mode"], GPU_MODE_CPU_ONLY)
        self.assertFalse(probe["available"])
        self.assertTrue(probe["cpu_ready"])
        # 处置必须同时点明"CPU 可用"与"训练建议 GPU"。
        self.assertIn("CPU", probe["action"])
        self.assertIn("GPU", probe["action"])

    def test_missing_stack_without_gpu_is_unavailable(self):
        probe = gpu_probe(torch_probe=lambda: {"available": False}, smi_probe=_no_smi)
        self.assertEqual(probe["mode"], GPU_MODE_UNAVAILABLE)
        self.assertFalse(probe["cpu_ready"])
        # 处置必须指向环境供应，而不是含糊地"回退 CPU"。
        self.assertIn("provision_cpu_training", probe["action"])

    def test_no_bool_only_contract(self):
        """三态必须自带历史布尔 available 的兼容映射（= mode == cuda）。"""
        probe = gpu_probe(torch_probe=lambda: {"available": True}, smi_probe=_no_smi)
        self.assertEqual(probe["available"], probe["mode"] == GPU_MODE_CUDA)

    def test_gpu_host_is_cuda(self):
        """smi_probe 给出设备 ⇒ cuda（注入正例，反例由上面两态覆盖）。"""
        probe = gpu_probe(
            torch_probe=lambda: {"available": True},
            smi_probe=lambda: ([{"name": "RTX 4060", "memory_mib": "8188", "driver": "566"}], None),
        )
        self.assertEqual(probe["mode"], GPU_MODE_CUDA)
        self.assertTrue(probe["available"])


if __name__ == "__main__":
    unittest.main()
