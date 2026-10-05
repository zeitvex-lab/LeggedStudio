"""完训≠达标 completion 钩子回归锁（2026-10-05 ㊃ 补充二的下一环）。

三件事：①档案判据声明的解析门（`_profile_criteria_declared`，未声明/缺文件不猜）；
②探针的发射语义（未声明不射 / 已有判定不重射 / 发射失败落日志 fail-soft）；
③判定面（`TrainingTask.to_dict` 把 trend_probe.json 的 criteria_tracking 暴露成
``criteria``——判负显式化，API 可见）。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from contracts.contract_legacy_v2 import ContractLegacyV2

import adapters.mjlab.launcher as launcher_mod


def _mk_repo(root: Path, *, declared: bool) -> Path:
    """临时仓库树：assets/robots/r1/training/profiles/p1.json（按需带判据声明）。"""
    pkg = root / "assets" / "robots" / "r1" / "training" / "profiles"
    pkg.mkdir(parents=True)
    profile: dict = {"profile_id": "p1"}
    if declared:
        profile["criteria"] = {"tracking": {
            "cases": ["0.5,0,0"], "err_max": 0.4, "cross_max": 0.2}}
    (pkg / "p1.json").write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    return root


def _mk_task_dir(root: Path, *, profile_id: str = "p1", robot_id: str = "r1",
                 broken: bool = False) -> Path:
    task = root / "workspace" / "task_x"
    task.mkdir(parents=True)
    if broken:
        (task / "training_config.json").write_text("{bad json", encoding="utf-8")
    else:
        (task / "training_config.json").write_text(
            json.dumps({"profile_id": profile_id}), encoding="utf-8")
        (task / "contract.json").write_text(
            json.dumps({"robot_id": robot_id}), encoding="utf-8")
    return task


class ProfileCriteriaDeclaredTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old = launcher_mod._REPO_ROOT

    def tearDown(self) -> None:
        launcher_mod._REPO_ROOT = self._old
        self._tmp.cleanup()

    def _use(self, *, declared: bool) -> Path:
        launcher_mod._REPO_ROOT = _mk_repo(self.root, declared=declared)
        return _mk_task_dir(self.root)

    def test_declared_returns_tracking_block(self):
        got = launcher_mod._profile_criteria_declared(self._use(declared=True))
        self.assertEqual(["0.5,0,0"], got["cases"])
        self.assertEqual(0.4, got["err_max"])

    def test_undeclared_profile_is_none(self):
        self.assertIsNone(launcher_mod._profile_criteria_declared(self._use(declared=False)))

    def test_missing_profile_id_or_robot_id_is_none(self):
        launcher_mod._REPO_ROOT = _mk_repo(self.root, declared=True)
        task = _mk_task_dir(self.root)
        (task / "training_config.json").write_text("{}", encoding="utf-8")
        self.assertIsNone(launcher_mod._profile_criteria_declared(task))
        (task / "contract.json").write_text("{}", encoding="utf-8")
        self.assertIsNone(launcher_mod._profile_criteria_declared(task))

    def test_unknown_profile_file_is_none(self):
        launcher_mod._REPO_ROOT = _mk_repo(self.root, declared=True)
        task = _mk_task_dir(self.root, profile_id="ghost")
        self.assertIsNone(launcher_mod._profile_criteria_declared(task))

    def test_broken_task_json_is_none_not_crash(self):
        launcher_mod._REPO_ROOT = _mk_repo(self.root, declared=True)
        task = _mk_task_dir(self.root, broken=True)
        self.assertIsNone(launcher_mod._profile_criteria_declared(task))


class SpawnCriteriaProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old = launcher_mod._REPO_ROOT

    def tearDown(self) -> None:
        launcher_mod._REPO_ROOT = self._old
        self._tmp.cleanup()

    def test_undeclared_profile_never_spawns(self):
        launcher_mod._REPO_ROOT = _mk_repo(self.root, declared=False)
        task = _mk_task_dir(self.root)
        with mock.patch.object(launcher_mod.subprocess, "Popen") as popen:
            self.assertFalse(launcher_mod._spawn_criteria_probe(task, Path("py.exe")))
        popen.assert_not_called()

    def test_existing_report_is_not_rerun(self):
        """重发/续训场景：trend_probe.json 已在 = 判定已在，不重复跑。"""
        launcher_mod._REPO_ROOT = _mk_repo(self.root, declared=True)
        task = _mk_task_dir(self.root)
        (task / "trend_probe.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(launcher_mod.subprocess, "Popen") as popen:
            self.assertFalse(launcher_mod._spawn_criteria_probe(task, Path("py.exe")))
        popen.assert_not_called()

    def test_declared_profile_spawns_probe_once_with_run_and_robot(self):
        launcher_mod._REPO_ROOT = _mk_repo(self.root, declared=True)
        task = _mk_task_dir(self.root)
        with mock.patch.object(launcher_mod.subprocess, "Popen") as popen:
            self.assertTrue(launcher_mod._spawn_criteria_probe(task, Path("py.exe")))
        self.assertEqual(1, popen.call_count)
        cmd = popen.call_args[0][0]
        self.assertIn("trend_probe.py", " ".join(cmd))
        self.assertIn(str(task), cmd)
        self.assertIn("r1", cmd)

    def test_spawn_failure_is_soft_and_logged(self):
        launcher_mod._REPO_ROOT = _mk_repo(self.root, declared=True)
        task = _mk_task_dir(self.root)
        with mock.patch.object(launcher_mod.subprocess, "Popen",
                               side_effect=OSError("no exec")):
            self.assertFalse(launcher_mod._spawn_criteria_probe(task, Path("py.exe")))
        self.assertIn("probe spawn failed",
                      (task / "criteria_probe.log").read_text(encoding="utf-8"))


class TaskDictCriteriaSurfaceTest(unittest.TestCase):
    """to_dict 把档案判据判定暴露成 criteria——「完训但判负」API 可见。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "workspace"
        self.workspace.mkdir(parents=True)
        fixture = (Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
                   / "unitree_go2.v2.json")
        self.contract = ContractLegacyV2.from_json_file(str(fixture))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _task(self):
        from backend.training_manager import TrainingManager
        manager = TrainingManager(workspace_dir=str(self.workspace))
        manager.launcher.launch_training = mock.Mock(return_value="x")  # type: ignore[assignment]
        tid = manager.create_task(contract=self.contract,
                                  config={"backend": "native_mjlab"})
        return manager.get_task(tid)

    def test_no_report_means_null_criteria(self):
        task = self._task()
        self.assertIsNone(task.to_dict().get("criteria"))

    def test_report_block_is_surfaced(self):
        task = self._task()
        (task.task_dir / "trend_probe.json").write_text(json.dumps({
            "verdict": "no_trend",
            "criteria_tracking": {"pass": False, "evaluated": 4, "err_max": 0.4},
        }), encoding="utf-8")
        criteria = task.to_dict().get("criteria")
        self.assertIsNotNone(criteria)
        self.assertFalse(criteria["pass"])
        self.assertEqual(4, criteria["evaluated"])


if __name__ == "__main__":
    unittest.main()
