"""A3 六层体检的验收测试。

任务清单 A3：**断 CUDA / 卸 mjlab / 空注册表**，各能定位到对应层，
并给出中文原因与处置。三种故障都通过依赖注入复现，不需要真实硬件。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.health_layers import LAYER_NAMES, build_layer_report

WORKSPACE = Path(__file__).resolve().parents[1]


def ok_gpu() -> dict:
    return cuda_gpu()


def no_gpu() -> dict:
    """无 GPU：三态探测默认落到 unavailable（未注入训练栈可用性）。"""
    return {"available": False, "mode": "unavailable", "cpu_ready": False,
            "reason": "nvidia-smi not found",
            "action": "先跑 scripts/provision_cpu_training.sh 供应 CPU 训练环境"}


def cpu_only_gpu() -> dict:
    """无 GPU 但训练栈可用：CPU 训练链路就绪。"""
    return {"available": False, "mode": "cpu-only", "cpu_ready": True,
            "reason": "nvidia-smi not found",
            "action": "CPU 训练链路可用：可跑仿真与最小训练冒烟；正式训练建议使用 NVIDIA GPU"}


def cuda_gpu() -> dict:
    return {"available": True, "mode": "cuda", "cpu_ready": True,
            "devices": [{"name": "RTX 4090", "memory_mib": "24564", "driver": "566"}]}


def ok_tasks() -> list[str]:
    return ["go2/velocity-flat", "go2/velocity-rough", "g1/velocity-flat", "zex-w/velocity"]


def ok_scene(robot_id: str) -> tuple[bool, str]:
    return True, f"{robot_id} 模型与场景资源齐备"


def venv_with_frameworks(root: Path) -> Path:
    """构造含 mjlab/torch/mujoco/warp 目录的假适配器 venv，隔离真实安装环境。"""
    site = root / "lib" / "python3.12" / "site-packages"
    for module in ("mjlab", "torch", "mujoco", "warp"):
        (site / module).mkdir(parents=True, exist_ok=True)
    return root


class HealthLayersTest(unittest.TestCase):
    """基线：全绿时 ready 且无 first_failure，L4–L6 默认 skip。"""

    def test_all_pass_baseline(self) -> None:
        with TemporaryDirectory() as directory:
            report = build_layer_report(
                gpu_probe=ok_gpu, list_tasks=ok_tasks, scene_check=ok_scene,
                venv=venv_with_frameworks(Path(directory) / "venv"),
            )
        self.assertTrue(report["ready"])
        self.assertIsNone(report["first_failure"])
        statuses = {layer["id"]: layer["status"] for layer in report["layers"]}
        self.assertEqual(
            statuses,
            {"L0": "pass", "L1": "pass", "L2": "pass", "L3": "pass",
             "L4": "skip", "L5": "skip", "L6": "skip"},
        )
        # 每层都必须带中文原因与处置（验收硬性要求）
        for layer in report["layers"]:
            self.assertTrue(layer["reason"], layer["id"])
            self.assertTrue(layer["action"], layer["id"])

    def test_layer_names_cover_l0_to_l6(self) -> None:
        self.assertEqual(set(LAYER_NAMES), {f"L{i}" for i in range(7)})


class NoGpuFallsBackToCpuTest(unittest.TestCase):
    """无 GPU 但训练栈可用（cpu-only）→ L0 告警但**不阻断**：CPU 可继续做仿真与冒烟验证。

    正式训练建议使用 GPU，但 CPU 回退不应让体检在 L0 就停摆。
    """

    def test_missing_gpu_warns_but_proceeds(self) -> None:
        with TemporaryDirectory() as directory:
            venv = venv_with_frameworks(Path(directory) / "venv")
            report = build_layer_report(
                gpu_probe=cpu_only_gpu, list_tasks=ok_tasks, scene_check=ok_scene, venv=venv,
            )
        self.assertTrue(report["ready"], "无 GPU 不应阻断 CPU 验证路径")
        self.assertIsNone(report["first_failure"])
        statuses = {layer["id"]: layer["status"] for layer in report["layers"]}
        self.assertEqual(statuses["L0"], "warn")
        self.assertNotEqual(statuses["L1"], "blocked", "无 GPU 不应把框架检查标为受阻")
        self.assertEqual(statuses["L1"], "pass")
        self.assertIn("CPU", report["layers"][0]["reason"])
        self.assertIn("GPU", report["layers"][0]["action"], "处置必须点明训练建议用 GPU")
        self.assertIn("CPU", report["layers"][0]["action"], "处置必须说明 CPU 可验证")


class CpuOnlyVsUnavailableTest(unittest.TestCase):
    """L0 三态：无 GPU + 训练栈可用(cpu-only) 与 无 GPU + 栈没装(unavailable) 的处置必须不同。

    这是本轮新增的关键区分：以前两者都只报"回退 CPU"，用户分不清"能跑"还是
    "压根没装训练栈"。
    """

    def _report(self, probe):
        with TemporaryDirectory() as directory:
            return build_layer_report(
                gpu_probe=probe, list_tasks=ok_tasks, scene_check=ok_scene,
                venv=venv_with_frameworks(Path(directory) / "venv"),
            )

    def test_cpu_only_points_to_cpu_capability(self):
        layer = self._report(cpu_only_gpu)["layers"][0]
        self.assertEqual(layer["status"], "warn")
        self.assertEqual(layer["mode"], "cpu-only")
        self.assertIn("CPU", layer["reason"])
        self.assertIn("GPU", layer["action"])

    def test_unavailable_points_to_provisioning(self):
        layer = self._report(no_gpu)["layers"][0]
        self.assertEqual(layer["status"], "warn")
        self.assertEqual(layer["mode"], "unavailable")
        self.assertIn("供应", layer["action"])

    def test_cuda_passes_with_device_listed(self):
        layer = self._report(ok_gpu)["layers"][0]
        self.assertEqual(layer["status"], "pass")
        self.assertEqual(layer["mode"], "cuda")
        self.assertEqual(layer["devices"][0]["name"], "RTX 4090")


class MissingFrameworkLocatesL1Test(unittest.TestCase):
    """卸 mjlab → 必须定位到 L1（框架层）。"""

    def test_missing_packages_stop_at_l1(self) -> None:
        report = build_layer_report(
            gpu_probe=ok_gpu, list_tasks=ok_tasks, scene_check=ok_scene,
            venv=WORKSPACE / "does" / "not" / "exist",
        )
        self.assertEqual(report["first_failure"], "L1")
        layer = report["layers"][1]
        self.assertEqual(layer["status"], "fail")
        self.assertIn("mjlab", layer["reason"], "必须点名缺失的框架包")
        self.assertIn("配置环境", layer["action"], "处置必须指向启动器的环境供应")


class EmptyRegistryLocatesL2Test(unittest.TestCase):
    """空注册表 → 必须定位到 L2（任务注册层）。"""

    def test_empty_tasks_stop_at_l2(self) -> None:
        with TemporaryDirectory() as directory:
            report = build_layer_report(
                gpu_probe=ok_gpu, list_tasks=lambda: [], scene_check=ok_scene,
                venv=venv_with_frameworks(Path(directory) / "venv"),
            )
        self.assertEqual(report["first_failure"], "L2")
        layer = report["layers"][2]
        self.assertEqual(layer["status"], "fail")
        self.assertIn("注册表为空", layer["reason"])
        self.assertIn("recipe_registry", layer["action"])


class MissingSceneLocatesL3Test(unittest.TestCase):
    """场景资源缺失 → 必须定位到 L3。"""

    def test_missing_scene_stops_at_l3(self) -> None:
        with TemporaryDirectory() as directory:
            report = build_layer_report(
                gpu_probe=ok_gpu, list_tasks=ok_tasks,
                scene_check=lambda robot_id: (False, f"缺少机型模型 assets/robots/{robot_id}/model/robot.xml"),
                venv=venv_with_frameworks(Path(directory) / "venv"),
            )
        self.assertEqual(report["first_failure"], "L3")
        layer = report["layers"][3]
        self.assertEqual(layer["status"], "fail")
        self.assertIn("robot.xml", layer["reason"])
        self.assertIn("导入", layer["action"], "处置必须指向重新导入包")


if __name__ == "__main__":
    unittest.main()
