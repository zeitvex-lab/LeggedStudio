"""H7 导航评估回写 PolicyArtifact 的落档语义测试。

**为什么单独钉这块**：`backend/navigation_api.py::_record_navigation_evaluation` 此前是
best-effort **静默** 返回 `None` —— 没有 `artifact.json` 就悄悄不写、写失败也悄悄不写，而接口
照样回 `{"success": True}`。也就是说"落档没落上"这件事**在外部完全不可见**，而 H7 的判据是
"完成率/误差/碰撞/稳定性**落档**"。本模块把三条语义钉死：

1. **落档成功**：四项指标真的写进档案（不是"函数被调用了"就算数）；
2. **未落档必须上报**：无 artifact / 缺指标 / 档案损坏，各自回一个可分辨的原因；
3. **不得用默认值伪造**：worker 报告里缺某项时**拒绝写入**（旧写法会静默写 0.0 —— 那等于
   往策略档案里写一句"完成率 0%"的假话）。注意判据是"**键在不在**"，不是"值真假"：
   报告里真实给出的 0.0 照写。

`navigation_api` 在本模块之前**零测试覆盖**（这正是它被称为"记录·参考"的原因）。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.navigation_api import NAVIGATION_METRICS, _record_navigation_evaluation


def _artifact_dict() -> dict:
    """最小但**合法**的 PolicyArtifact（只为落档语义服务，不冒充真实训练产物）。"""
    return {
        "artifact_id": "demo_bot_forward_walk_ppo_v1",
        "robot_contract_id": "demo_bot_contract_v1",
        "robot_contract_hash": "0" * 64,
        "robot_contract_snapshot": {"contract_id": "demo_bot_contract_v1"},
        "task_name": "forward_walk",
        "algorithm": "PPO",
        "algorithm_config": {"lr": 3e-4},
        "metrics": {
            "iterations": 100,
            "episodes": 50,
            "success_rate": 0.9,
            "avg_reward": 12.5,
            "final_reward": 15.0,
            "training_duration_seconds": 600.0,
        },
        "pytorch_model_path": "model_final.pt",
        "pytorch_model_hash": "1" * 64,
        "obs_normalizer": {"mean": [0.0], "std": [1.0]},
        "environment": "mjlab",
        "mjlab_version": "0.1.0",
        "python_version": "3.11",
        "pytorch_version": "2.3.0",
        "cuda_version": "12.1",
    }


def _nav_result(**overrides) -> dict:
    payload = {
        "route_completion": 0.75,
        "mean_tracking_error": 0.21,
        "collision_count": 2,
        "stability_score": 0.5,
    }
    payload.update(overrides)
    return payload


REQUEST = SimpleNamespace(map_id="warehouse", waypoints=[[0.0, 0.0], [2.0, 1.0]], episodes=3)


class NavigationWritebackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.task_dir = Path(self._tmp.name)
        self.task = SimpleNamespace(task_dir=self.task_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_artifact(self) -> Path:
        path = self.task_dir / "artifact.json"
        path.write_text(json.dumps(_artifact_dict(), ensure_ascii=False), encoding="utf-8")
        return path

    def test_four_metrics_are_really_written(self):
        """落档成功：四项指标写进 artifact，而不是"函数没抛错"就算过。"""
        path = self._write_artifact()
        status = _record_navigation_evaluation(self.task, _nav_result(), REQUEST)
        self.assertTrue(status["recorded"], status)
        self.assertEqual(str(path), status["artifact"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        evaluation = saved["navigation_evaluation"]
        self.assertEqual("warehouse", evaluation["map_id"])
        self.assertEqual(0.75, evaluation["route_completion"])
        self.assertEqual(0.21, evaluation["mean_tracking_error"])
        self.assertEqual(2, evaluation["collision_count"])
        self.assertEqual(0.5, evaluation["stability_score"])
        self.assertEqual(3, evaluation["episodes"])

    def test_missing_artifact_is_reported(self):
        """无 artifact：**上报原因**，不再静默跳过。"""
        status = _record_navigation_evaluation(self.task, _nav_result(), REQUEST)
        self.assertFalse(status["recorded"])
        self.assertEqual("artifact_missing", status["reason"])
        self.assertIn("artifact.json", status["artifact"])

    def test_missing_metric_is_refused_not_defaulted(self):
        """缺指标：拒绝写入并指名缺哪个；**档案保持原样**（不得写 0.0 冒充）。"""
        path = self._write_artifact()
        payload = _nav_result()
        del payload["stability_score"]
        status = _record_navigation_evaluation(self.task, payload, REQUEST)
        self.assertFalse(status["recorded"])
        self.assertEqual("metrics_missing", status["reason"])
        self.assertEqual(["stability_score"], status["missing"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(saved.get("navigation_evaluation"), "缺指标时不许落任何半成品档案")

    def test_real_zero_values_are_recorded(self):
        """真实给出的 0.0 照写 —— 判据是"键在不在"，不是"值真假"。"""
        path = self._write_artifact()
        status = _record_navigation_evaluation(
            self.task,
            _nav_result(route_completion=0.0, mean_tracking_error=0.0, collision_count=0, stability_score=0.0),
            REQUEST,
        )
        self.assertTrue(status["recorded"], status)
        evaluation = json.loads(path.read_text(encoding="utf-8"))["navigation_evaluation"]
        self.assertEqual(0.0, evaluation["route_completion"])
        self.assertEqual(0, evaluation["collision_count"])

    def test_corrupt_artifact_is_reported_not_swallowed(self):
        """档案损坏：转成可读原因（不抛、也不静默）。"""
        (self.task_dir / "artifact.json").write_text("{ not json", encoding="utf-8")
        status = _record_navigation_evaluation(self.task, _nav_result(), REQUEST)
        self.assertFalse(status["recorded"])
        self.assertIn("JSONDecodeError", status["reason"])

    def test_metrics_constant_matches_worker_report(self):
        """防漂移：落档必需的四项必须与 worker 实际产出的键同名。

        `_record_navigation_evaluation` 的严格检查会让"键名漂移"表现为**拒绝落档**——
        这本身是可见的（好过静默），但更该在改 worker 时就红。故这里核对源头文本。
        """
        worker = Path(__file__).resolve().parents[1] / "adapters" / "mjlab" / "native_worker.py"
        source = worker.read_text(encoding="utf-8")
        for name in NAVIGATION_METRICS:
            self.assertIn(f'"{name}"', source, f"worker 报告里缺少落档指标 {name}（键名漂移会让落档被拒）")


if __name__ == "__main__":
    unittest.main()
