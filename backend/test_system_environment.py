"""U11：/api/system/environment 数据真值化的验收测试。

背景（00_know/05_任务清单.md §U 行 11）：工作台首页系统状态（原 dashboard）的 Python/CUDA/MJLab
行是展示层硬编码假值，因为端点只返回 control_plane.python_version + adapters。
修复后端点新增 ``gpu``（与 /api/health/layers L0 同源的 gpu_probe 三态）与
``adapters.mjlab.version``（dist-info 实装版本，复用 training/runs.venv_package_versions）。

口径：
  * 控制面不 import torch/mjlab（铁律）——version 从 venv 的 ``*.dist-info``
    目录名读，是文件系统操作不是 import；
  * fail-soft —— 无 venv / 探测失败时 version 如实 null、gpu 如实 unknown，
    端点绝不 500；
  * gpu 与 health 端点**同源**——同一探测函数（adapters.mjlab.preflight.gpu_probe），
    两个端点的 mode 口径必须一致（同源断言，防止将来另写一份探测漂移）。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fastapi.testclient import TestClient

from backend.api_complete import app

ENVIRONMENT_URL = "/api/system/environment"


class SystemEnvironmentTruthTests(unittest.TestCase):
    """端点返回结构 + 真值字段类型 + fail-soft 行为。"""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_payload_has_gpu_and_mjlab_version_keys(self) -> None:
        payload = self.client.get(ENVIRONMENT_URL).json()
        # 新增真值键在位
        self.assertIn("gpu", payload)
        self.assertIn("version", payload["adapters"]["mjlab"])
        self.assertIn("version_status", payload["adapters"]["mjlab"])
        # 既有契约不回归
        self.assertIn("control_plane", payload)
        self.assertEqual(set(payload["adapters"]), {"mjlab"})

    def test_gpu_shape_and_known_modes(self) -> None:
        payload = self.client.get(ENVIRONMENT_URL).json()
        gpu = payload["gpu"]
        # 类型契约：mode 是三态之一（探测失败才 unknown），devices 是列表
        self.assertIsInstance(gpu["mode"], str)
        self.assertIn(gpu["mode"], {"cuda", "cpu-only", "unavailable", "unknown"})
        self.assertIsInstance(gpu["devices"], list)
        for device in gpu["devices"]:
            self.assertIn("name", device)
        # mode=cuda 时必须有设备佐证（有 GPU 却不给 devices = 又一处假值）
        if gpu["mode"] == "cuda":
            self.assertTrue(gpu["devices"], "mode=cuda 但 devices 为空 —— 违反真值口径")

    def test_mjlab_version_type_contract(self) -> None:
        payload = self.client.get(ENVIRONMENT_URL).json()
        mjlab = payload["adapters"]["mjlab"]
        # version 只能是「实装版本字符串」或「如实 null」，绝不允许编一个假版本号
        self.assertTrue(mjlab["version"] is None or isinstance(mjlab["version"], str))
        if mjlab["version"] is None:
            self.assertIn(mjlab["version_status"]["status"], {"not_installed", "unknown"})
            self.assertTrue(mjlab["version_status"]["reason"], "version=null 时必须给中文原因")
        else:
            self.assertEqual(mjlab["version_status"]["status"], "installed")

    def test_mjlab_version_matches_dist_info_on_disk(self) -> None:
        """version 必须来自 venv dist-info 的落盘真值，不是编出来的。"""
        from backend.training.runs import venv_package_versions

        payload = self.client.get(ENVIRONMENT_URL).json()
        expected = venv_package_versions().get("mjlab")
        actual = payload["adapters"]["mjlab"]["version"]
        self.assertEqual(actual, expected)

    def test_missing_venv_reports_not_installed_without_raising(self) -> None:
        """无 venv（tmp 空目录模拟）：version 如实 null + not_installed，端点不抛不 500。"""
        with TemporaryDirectory() as tmp:
            empty_venv = Path(tmp) / "no-venv-here"
            with mock.patch(
                "contracts.path_bootstrap.adapter_venv_dir", return_value=empty_venv
            ):
                payload = self.client.get(ENVIRONMENT_URL).json()
        self.assertEqual(payload["adapters"]["mjlab"]["version"], None)
        self.assertEqual(payload["adapters"]["mjlab"]["version_status"]["status"], "not_installed")
        self.assertIn("venv", payload["adapters"]["mjlab"]["version_status"]["reason"])

    def test_venv_without_mjlab_reports_null_with_reason(self) -> None:
        """venv 存在但没装 mjlab（空 site-packages）：version null + unknown + 中文原因。"""
        with TemporaryDirectory() as tmp:
            fake_venv = Path(tmp) / "venv"
            (fake_venv / "Lib" / "site-packages").mkdir(parents=True)
            with mock.patch(
                "contracts.path_bootstrap.adapter_venv_dir", return_value=fake_venv
            ):
                payload = self.client.get(ENVIRONMENT_URL).json()
        self.assertEqual(payload["adapters"]["mjlab"]["version"], None)
        self.assertEqual(payload["adapters"]["mjlab"]["version_status"]["status"], "unknown")
        self.assertTrue(payload["adapters"]["mjlab"]["version_status"]["reason"])

    def test_gpu_probe_failure_degrades_softly(self) -> None:
        """gpu_probe 本身炸了：mode 落 unknown + 中文 reason，端点不 500（fail-soft）。"""
        with mock.patch(
            "adapters.mjlab.preflight.gpu_probe",
            side_effect=RuntimeError("nvidia-smi 假故障"),
        ):
            payload = self.client.get(ENVIRONMENT_URL).json()
        gpu = payload["gpu"]
        self.assertEqual(gpu["mode"], "unknown")
        self.assertEqual(gpu["status"], "error")
        self.assertIn("GPU 探测失败", gpu["reason"])
        self.assertEqual(gpu["devices"], [])

    def test_environment_and_health_gpu_same_source(self) -> None:
        """同源断言：environment 的 gpu 与 health 的 L0 口径必须一致（同一探测实现）。

        mock 掉同一落点 ``adapters.mjlab.preflight.gpu_probe``（两个端点的唯一真值源），
        注入一个带特征名的设备 —— 两个端点都必须如实透出同一 mode 与该设备。
        """
        def fake_gpu_probe() -> dict:
            return {
                "available": True, "mode": "cuda", "cpu_ready": True,
                "devices": [{"name": "TESTMARK-4090", "memory_mib": "24564", "driver": "566"}],
                "reason": "1 device(s)", "action": "无需处置",
            }

        with mock.patch("adapters.mjlab.preflight.gpu_probe", side_effect=fake_gpu_probe):
            environment = self.client.get(ENVIRONMENT_URL).json()
            health = self.client.get("/api/health/layers").json()

        env_gpu = environment["gpu"]
        l0 = next(layer for layer in health["layers"] if layer["id"] == "L0")
        self.assertEqual(env_gpu["mode"], "cuda")
        self.assertEqual(l0["mode"], "cuda")
        self.assertEqual(env_gpu["mode"], l0["mode"])
        self.assertEqual(env_gpu["devices"][0]["name"], "TESTMARK-4090")
        self.assertEqual(l0["devices"][0]["name"], "TESTMARK-4090")

    def test_control_plane_never_imports_torch_or_mjlab(self) -> None:
        """铁律复测：端点调用前后 torch/mjlab 都不进 sys.modules（dist-info 是读文件）。"""
        import sys

        baseline = set(sys.modules)
        self.client.get(ENVIRONMENT_URL).json()
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("mjlab", sys.modules)
        # 收尾：清掉探测期间可能新引入的其他模块，不污染同进程后续测试
        for name in set(sys.modules) - baseline:
            del sys.modules[name]


if __name__ == "__main__":
    unittest.main()
