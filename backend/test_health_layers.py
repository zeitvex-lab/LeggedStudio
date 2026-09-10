"""A3 六层体检的验收测试。

任务清单 A3：**断 CUDA / 卸 mjlab / 空注册表**，各能定位到对应层，
并给出中文原因与处置。三种故障都通过依赖注入复现，不需要真实硬件。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.health_layers import LAYER_NAMES, build_layer_report

WORKSPACE = Path(__file__).resolve().parents[1]


def ok_gpu() -> dict:
    return {"available": True, "devices": [{"name": "RTX 4090", "memory_mib": "24564", "driver": "566"}]}


def no_gpu() -> dict:
    return {"available": False, "reason": "nvidia-smi not found"}


def ok_tasks() -> list[str]:
    return ["go2/velocity-flat", "go2/velocity-rough", "g1/velocity-flat", "zex-w/velocity"]


def ok_scene(robot_id: str) -> tuple[bool, str]:
    return True, f"{robot_id} 模型与场景资源齐备"


class HealthLayersTest(unittest.TestCase):
    """基线：全绿时 ready 且无 first_failure，L4–L6 默认 skip。"""

    def test_all_pass_baseline(self) -> None:
        report = build_layer_report(
            gpu_probe=ok_gpu, list_tasks=ok_tasks, scene_check=ok_scene,
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


class BrokenGpuLocatesL0Test(unittest.TestCase):
    """断 CUDA → 必须定位到 L0，且后续层 blocked（fail-fast）。"""

    def test_missing_gpu_stops_at_l0(self) -> None:
        report = build_layer_report(
            gpu_probe=no_gpu, list_tasks=ok_tasks, scene_check=ok_scene,
        )
        self.assertFalse(report["ready"])
        self.assertEqual(report["first_failure"], "L0")
        statuses = {layer["id"]: layer["status"] for layer in report["layers"]}
        self.assertEqual(statuses["L0"], "fail")
        self.assertEqual(statuses["L1"], "blocked", "fail-fast：L1 不应在 L0 失败后照常执行")
        self.assertIn("GPU", statuses and report["layers"][0]["reason"])
        self.assertIn("驱动", report["layers"][0]["action"], "处置必须是中文且可执行")


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
        report = build_layer_report(
            gpu_probe=ok_gpu, list_tasks=lambda: [], scene_check=ok_scene,
        )
        self.assertEqual(report["first_failure"], "L2")
        layer = report["layers"][2]
        self.assertEqual(layer["status"], "fail")
        self.assertIn("注册表为空", layer["reason"])
        self.assertIn("recipe_registry", layer["action"])


class MissingSceneLocatesL3Test(unittest.TestCase):
    """场景资源缺失 → 必须定位到 L3。"""

    def test_missing_scene_stops_at_l3(self) -> None:
        report = build_layer_report(
            gpu_probe=ok_gpu, list_tasks=ok_tasks,
            scene_check=lambda robot_id: (False, f"缺少机型模型 assets/robots/{robot_id}/model/robot.xml"),
        )
        self.assertEqual(report["first_failure"], "L3")
        layer = report["layers"][3]
        self.assertEqual(layer["status"], "fail")
        self.assertIn("robot.xml", layer["reason"])
        self.assertIn("导入", layer["action"], "处置必须指向重新导入包")


if __name__ == "__main__":
    unittest.main()
