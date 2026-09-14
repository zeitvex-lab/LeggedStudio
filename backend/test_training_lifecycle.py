"""F6 前半：训练进程生命周期无僵尸——启动孤儿判定 + 退出清理接线。

覆盖四件事：
1. **已死孤儿终结** —— status.json 记 running 但 pid 已不存在 → 恢复时如实
   终结为 failed（orphan_finalized=true），不伪造完成态；
2. **存活孤儿标记与清理** —— pid 仍在运行 → 状态置 orphaned，stop_task 按 pid
   走 taskkill/os.kill 清理分支（**不真杀进程**：monkeypatch subprocess/os 后
   只断言收到的命令）；
3. **终态任务不受牵连** —— completed 等终态档案恢复后原样保留；
4. **退出接线** —— TestClient 的 with 块触发 lifespan shutdown，确认
   shutdown_global_manager 被调用（控制面退出即清理 running worker）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.robot_contract_v2 import RobotContractV2  # noqa: E402


def _sample_contract() -> RobotContractV2:
    """与 test_training_idempotency 同款：真实合法的 v2 契约夹具。"""
    fixture = Path(__file__).resolve().parents[1] / "contracts" / "fixtures" / "unitree_go2.v2.json"
    return RobotContractV2.from_json_file(str(fixture))


def _make_task(workspace: Path, task_id: str, status_payload: dict) -> Path:
    """合成一个可被 _load_existing_tasks 恢复的任务目录（契约+配置+状态）。"""
    task_dir = workspace / task_id
    task_dir.mkdir(parents=True)
    _sample_contract().to_json_file(str(task_dir / "contract.json"))
    (task_dir / "training_config.json").write_text(
        json.dumps({"backend": "native_mjlab", "algorithm": "PPO", "max_iterations": 10}),
        encoding="utf-8",
    )
    (task_dir / "status.json").write_text(json.dumps(status_payload, ensure_ascii=False), encoding="utf-8")
    return task_dir


def _read_status(task_dir: Path) -> dict:
    return json.loads((task_dir / "status.json").read_text(encoding="utf-8"))


class OrphanFinalizeTest(unittest.TestCase):
    """启动补账（worker 已死分支）：watcher 随旧控制面死了，如实终结、不伪造。"""

    def test_running_task_with_dead_pid_is_finalized_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            _make_task(workspace, "t_dead", {"status": "running", "pid": 999999, "exit_code": None})
            from backend.training_manager import TrainingManager

            TrainingManager(workspace_dir=str(workspace))
            status = _read_status(workspace / "t_dead")
            self.assertEqual(status["status"], "failed")
            self.assertIn("控制面重启", status["error"])
            self.assertTrue(status["orphan_finalized"])

    def test_pending_task_without_pid_counts_as_dead(self):
        """pid 缺失/None：从未真正起过 worker（或旧档案没记 pid）→ 归入已死分支。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            _make_task(workspace, "t_pending", {"status": "pending", "pid": None, "exit_code": None})
            from backend.training_manager import TrainingManager

            TrainingManager(workspace_dir=str(workspace))
            status = _read_status(workspace / "t_pending")
            self.assertEqual(status["status"], "failed")
            self.assertTrue(status["orphan_finalized"])


class LiveOrphanTest(unittest.TestCase):
    """存活孤儿：标 orphaned，stop 走按 pid 清理分支（monkeypatch，绝不真杀）。"""

    def test_running_task_with_live_pid_is_marked_orphaned(self):
        """pid 用当前测试进程自己的 pid：一定"活着"，且后续只 monkeypatch 不真杀。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            _make_task(workspace, "t_live", {"status": "running", "pid": os.getpid(), "exit_code": None})
            from backend.training_manager import TrainingManager

            manager = TrainingManager(workspace_dir=str(workspace))
            status = _read_status(workspace / "t_live")
            self.assertEqual(status["status"], "orphaned")
            self.assertIn("脱离监督", status["error"])
            self.assertEqual(manager.get_task("t_live").status, "orphaned")

    def test_stop_task_for_orphaned_uses_pid_terminate(self):
        """stop 对 orphaned 任务按 pid 清理：Windows 断言 taskkill 命令，POSIX 断言 os.kill。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            _make_task(workspace, "t_live2", {"status": "running", "pid": os.getpid(), "exit_code": None})
            from backend import training_manager as tm

            manager = tm.TrainingManager(workspace_dir=str(workspace))
            self.assertEqual(_read_status(workspace / "t_live2")["status"], "orphaned")

            with mock.patch.object(tm.subprocess, "run") as run_mock, \
                    mock.patch.object(tm.os, "kill") as kill_mock:
                manager.stop_task("t_live2")
            self.assertEqual(_read_status(workspace / "t_live2")["status"], "stopped")
            if sys.platform == "win32":
                run_mock.assert_called_once()
                cmd = [str(part) for part in run_mock.call_args.args[0]]
                self.assertIn("taskkill", " ".join(cmd).lower())
                self.assertIn(str(os.getpid()), cmd)  # /PID 带的是 status.json 记录的 pid
                kill_mock.assert_not_called()
            else:
                # POSIX：_pid_alive 也走 os.kill(pid, 0)，故只断言"最终收到 SIGKILL"
                import signal

                run_mock.assert_not_called()
                kills = [(call.args[0], call.args[1]) for call in kill_mock.call_args_list]
                self.assertIn((os.getpid(), signal.SIGKILL), kills)

    def test_stop_task_skips_kill_when_orphan_pid_already_gone(self):
        """stop 之前 worker 自行退出的竞态：pid 已死则不发起 kill，直接落 stopped。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            task_dir = _make_task(workspace, "t_gone", {"status": "running", "pid": os.getpid(), "exit_code": None})
            from backend import training_manager as tm

            manager = tm.TrainingManager(workspace_dir=str(workspace))
            self.assertEqual(_read_status(task_dir)["status"], "orphaned")
            payload = _read_status(task_dir)
            payload["pid"] = 999999  # 换成不存在的 pid，模拟 worker 已先退出
            (task_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with mock.patch.object(tm.subprocess, "run") as run_mock, \
                    mock.patch.object(tm.os, "kill") as kill_mock:
                manager.stop_task("t_gone")
            run_mock.assert_not_called()
            kill_mock.assert_not_called()
            self.assertEqual(_read_status(task_dir)["status"], "stopped")


class TerminalTaskUntouchedTest(unittest.TestCase):
    """终态档案不因孤儿判定被改写：别把已完成/失败的任务变成 orphaned/failed。"""

    def test_completed_task_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            _make_task(workspace, "t_done", {"status": "completed", "pid": 999999, "exit_code": 0})
            from backend.training_manager import TrainingManager

            manager = TrainingManager(workspace_dir=str(workspace))
            self.assertEqual(_read_status(workspace / "t_done")["status"], "completed")
            self.assertEqual(manager.get_task("t_done").status, "completed")

    def test_legacy_completed_task_without_pid_field_is_untouched(self):
        """旧格式 status.json 没有 pid 字段的终态任务：维持现状。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            _make_task(workspace, "t_legacy", {"status": "completed"})
            from backend.training_manager import TrainingManager

            TrainingManager(workspace_dir=str(workspace))
            self.assertEqual(_read_status(workspace / "t_legacy"), {"status": "completed"})


class ShutdownWiringTest(unittest.TestCase):
    """退出接线：lifespan shutdown 必须触发训练清理（spy 替身，零副作用）。"""

    @staticmethod
    def _import_api_complete():
        """在 pytest 捕获环境下安全导入 api_complete。

        api_complete 在 win32 上会**模块级**重包 sys.stdout/stderr（UTF-8 控制台）；
        若导入发生在 pytest 捕获期间，新包装器随后被替换/GC 时会把 pytest 的
        临时捕获文件一并关闭，整个会话炸出 "I/O operation on closed file"
        （test_api_complete.py 单独跑 pytest 踩的就是同一个坑）。这里在导入
        期间把标准流指向 devnull，让重包发生在无害对象上；模块已导入时则是
        纯 sys.modules 查表，无副作用。
        """
        if "backend.api_complete" in sys.modules:
            from backend import api_complete

            return api_complete
        saved_out, saved_err = sys.stdout, sys.stderr
        sink = open(os.devnull, "w", encoding="utf-8")
        try:
            sys.stdout = sys.stderr = sink
            from backend import api_complete

            return api_complete
        finally:
            sys.stdout, sys.stderr = saved_out, saved_err
            sink.close()

    def test_lifespan_shutdown_calls_training_cleanup(self):
        # api_complete 较重（挂载静态目录、可选栈探测），放测试内导入，
        # 不拖慢本文件其它用例的收集与执行。
        from fastapi.testclient import TestClient

        from backend import training_manager

        api_complete = self._import_api_complete()

        with mock.patch.object(training_manager, "shutdown_global_manager") as spy:
            # 只有 with 块形式的 TestClient 才触发 lifespan（starlette 语义），
            # 裸 TestClient(app).get(...) 不触发——这正是 test_api_complete.py 不受影响的原因。
            with TestClient(api_complete.app):
                pass  # 进出 with 块 = 完整的 startup → shutdown 生命周期
            spy.assert_called_once()

    def test_shutdown_global_manager_is_noop_without_instance(self):
        """全局实例不存在时退出清理是 no-op：不在退出路径上构造 TrainingManager。"""
        from backend import training_manager as tm

        with mock.patch.object(tm, "_global_manager", None):
            self.assertFalse(tm.shutdown_global_manager())
            # 有实例时才执行 cleanup——用替身验证调用落到 cleanup 上
        fake = mock.Mock(spec=tm.TrainingManager)
        with mock.patch.object(tm, "_global_manager", fake):
            self.assertTrue(tm.shutdown_global_manager())
        fake.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
