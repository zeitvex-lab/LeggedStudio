"""
Training Manager
训练任务管理器
"""

from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import json
import os
import subprocess
import sys

from adapters.mjlab.launcher import TrainingLauncher
from contracts.robot_contract_v2 import RobotContractV2


def _package_contract_snapshot(robot_id: str) -> Optional[dict]:
    """读取包当前契约作为训练快照：v3 语义优先合并，v2 数据补全。"""

    from backend.robot_presets import get_robot_preset
    from contracts.contract_loader import load_contract_v3, load_contract_v2, merge_v3_over_v2

    preset = get_robot_preset(robot_id)
    root = Path(str(((preset or {}).get("robot_package") or {}).get("package_root", ""))) if preset else None
    if root is None:
        return None
    try:
        return merge_v3_over_v2(load_contract_v3(root), load_contract_v2(root))
    except Exception:
        # Fall back to the raw v3/v2 record when semantic merge fails so the
        # snapshot still lands (the DENYLIST gate treats drift as a warning).
        for name in ("contract_v3.json", "contract.json"):
            path = root / name
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError):
                    continue
    return None


def _pid_alive(pid: object) -> bool:
    """判活一个 pid（F6 孤儿判定用，不引入 psutil 等第三方依赖）。

    - Windows：ctypes 走 kernel32.OpenProcess + GetExitCodeProcess——句柄打不开
      （pid 不存在/无权限）视为已死；退出码 == STILL_ACTIVE(259) 视为存活。
      显式声明 WinDLL 签名，避免默认 c_int 返回值截断 64 位句柄。
    - POSIX：os.kill(pid, 0) 只探测存在性、不发送信号。
    已知局限：pid 复用会把"恰好分配到同号的新进程"误判为存活——本函数只用于
    控制面启动时的孤儿补账，误判的代价是状态标成 orphaned（可再 stop 清理），
    不会伪造完成态，可接受。
    """
    # bool 是 int 的子类，pid=True 之类的脏数据一并挡掉；缺失/None/0 归入已死分支。
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        STILL_ACTIVE = 259
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32)
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            exit_code = ctypes.c_uint32()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在，只是属于别的用户
    except OSError:
        return False
    return True


def _terminate_orphan_worker(pid: int) -> None:
    """按 pid 终结脱离监督的孤儿 worker（F6：stop_task 的 orphaned 分支）。

    - Windows 用 taskkill /T /F：连同子进程树一起结束（mjlab worker 可能再
      spawn 子进程，只杀根会留下孙进程）。
    - POSIX 只 os.kill 单进程、不用 killpg：launcher 的 Popen 没有
      start_new_session，worker 与控制面同进程组，killpg 会连控制面自己
      一起误杀。
    结果吞错：进程在 stop 之前恰好自行退出的竞态，按"已清理"处理。
    """
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    import signal

    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


class TrainingTask:
    """训练任务"""

    def __init__(
        self,
        task_id: str,
        contract: RobotContractV2,
        config: dict,
        task_dir: Path
    ):
        self.task_id = task_id
        self.contract = contract
        self.config = config
        self.task_dir = task_dir
        self.created_at = datetime.now()
        self.status = "pending"

    def get_progress(self) -> dict:
        """获取进度"""
        progress_file = self.task_dir / "progress.json"
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def get_status_info(self) -> dict:
        """获取状态信息"""
        status_file = self.task_dir / "status.json"
        if status_file.exists():
            try:
                with open(status_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def to_dict(self) -> dict:
        """转为字典"""
        progress = self.get_progress()
        status_info = self.get_status_info()
        runtime_info = {}
        runtime_file = self.task_dir / "runtime.json"
        if runtime_file.exists():
            try:
                runtime_info = json.loads(runtime_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                runtime_info = {}

        return {
            "task_id": self.task_id,
            "contract_id": self.contract.contract_id,
            "robot": self.contract.family,
            "algorithm": self.config.get("algorithm", "PPO"),
            "status": status_info.get("status", self.status),
            "progress": progress.get("progress", 0.0),
            "created_at": self.created_at.isoformat(),
            "config": self.config,
            "current_iteration": progress.get("iteration", 0),
            "max_iterations": self.config.get("max_iterations", 0),
            "reward": progress.get("reward_mean", 0.0)
            ,"success_rate": progress.get("success_rate", status_info.get("success_rate", 0.0))
            ,"pid": status_info.get("pid")
            ,"exit_code": status_info.get("exit_code")
            ,"error": status_info.get("error")
            ,"device": status_info.get("device", runtime_info.get("resolved"))
            ,"runtime": runtime_info
        }


class TrainingManager:
    """训练管理器"""

    def __init__(self, workspace_dir: str | None = None):
        configured_dir = workspace_dir or os.environ.get("LEGGED_STUDIO_WORKSPACE") or "workspace"
        self.workspace_dir = Path(configured_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self.launcher = TrainingLauncher(workspace_dir=str(self.workspace_dir))
        self.tasks: Dict[str, TrainingTask] = {}
        # Idempotency-Key -> task_id mapping, persisted so a control-plane
        # restart does not let a duplicate POST /api/training/create spawn a
        # second training run (Feature 13: idempotent training creation).
        self._idem_path = self.workspace_dir / "_idempotency.json"
        self._idempotency: Dict[str, str] = {}
        self._load_existing_tasks()
        self._load_idempotency()

    def _load_existing_tasks(self) -> None:
        """Recover task metadata after a control-plane restart."""
        for task_dir in sorted(self.workspace_dir.iterdir() if self.workspace_dir.exists() else [], reverse=True):
            contract_path = task_dir / "contract.json"
            config_path = task_dir / "training_config.json"
            if not task_dir.is_dir() or not contract_path.exists() or not config_path.exists():
                continue
            try:
                contract = RobotContractV2.from_json_file(str(contract_path))
                config = json.loads(config_path.read_text(encoding="utf-8"))
                task = TrainingTask(task_dir.name, contract, config, task_dir)
                status_info = task.get_status_info()
                task.status = status_info.get("status", "completed" if (task_dir / "artifact.json").exists() else "pending")
                task.status = self._reconcile_orphaned_task(task, status_info)
                self.tasks[task.task_id] = task
            except Exception as exc:
                print(f"[Manager] Failed to recover {task_dir.name}: {exc}")

    def _reconcile_orphaned_task(self, task: "TrainingTask", status_info: dict) -> str:
        """启动孤儿判定（F6：训练进程生命周期无僵尸）。

        watcher 线程活在控制面进程里（launcher.py），旧控制面一死它先死，worker
        的终态从此无人记录——恢复时按 status.json 里的 pid 判活补账：
        - pid 已死（含缺失/None/0：从未真正起过 worker 或旧档案没记 pid）→
          终结为 failed，error 如实写明"终态无人记录"，不伪造完成态；
        - pid 仍活 → 置 orphaned（新状态值）：worker 还在跑但已脱离监督，
          stop_task 会按 pid 直接清理。
        终态任务（completed/failed/stopped 等非 running/pending 状态）一律不动，
        避免误伤历史档案；orphaned 自身也纳入判定，保证再次重启时幂等。
        """
        status = status_info.get("status") or task.status
        if status not in ("running", "pending", "orphaned"):
            return status
        pid = status_info.get("pid")
        if _pid_alive(pid):
            task.status = "orphaned"
            (task.task_dir / "status.json").write_text(
                json.dumps(
                    {**status_info, "status": "orphaned", "error": "控制面重启，worker 仍在运行但已脱离监督"},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"[Manager] Orphaned task recovered (worker pid {pid} alive): {task.task_id}")
            return "orphaned"
        task.status = "failed"
        (task.task_dir / "status.json").write_text(
            json.dumps(
                {
                    **status_info,
                    "status": "failed",
                    "error": "控制面重启时 worker 已退出（watcher 随旧控制面终止，终态无人记录）",
                    "orphan_finalized": True,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[Manager] Orphaned task finalized as failed (worker pid {pid} gone): {task.task_id}")
        return "failed"

    def _load_idempotency(self) -> None:
        """Load the persisted Idempotency-Key -> task_id map (Feature 13)."""
        try:
            if self._idem_path.exists():
                data = json.loads(self._idem_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Drop entries whose task_dir no longer exists so a stale
                    # key never guards a deleted task.
                    self._idempotency = {
                        k: v for k, v in data.items()
                        if (self.workspace_dir / v).exists()
                    }
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[Manager] Failed to load idempotency map: {exc}")

    def _save_idempotency(self) -> None:
        """Persist the Idempotency-Key -> task_id map (Feature 13)."""
        try:
            self._idem_path.write_text(
                json.dumps(self._idempotency, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"[Manager] Failed to save idempotency map: {exc}")

    def resolve_idempotency(self, key: str) -> Optional[str]:
        """Return an existing task_id for an Idempotency-Key, if any (Feature 13)."""
        if not key:
            return None
        return self._idempotency.get(key)

    def register_idempotency(self, key: str, task_id: str) -> None:
        """Bind an Idempotency-Key to a created task_id (Feature 13)."""
        if not key:
            return
        self._idempotency[key] = task_id
        self._save_idempotency()

    def create_task(
        self,
        contract: RobotContractV2,
        config: dict,
        idempotency_key: str | None = None,
    ) -> str:
        """
        创建训练任务

        Args:
            contract: Robot Contract
            config: 训练配置

        Returns:
            task_id: 任务 ID
        """
        if str(config.get("backend", "native_mjlab")) != "native_mjlab":
            raise ValueError("TrainingManager only supports the native_mjlab backend")

        # Idempotency-Key guard (Feature 13): replaying the same creation request
        # returns the existing task instead of spawning a duplicate worker.
        if idempotency_key:
            existing = self.resolve_idempotency(idempotency_key)
            if existing and self.get_task(existing):
                print(f"[Manager] Idempotent replay of key {idempotency_key!r} -> task {existing}")
                return existing

        # 生成任务 ID
        task_id = self._generate_task_id(contract.contract_id)

        # 创建任务目录
        task_dir = self.workspace_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=False)

        # 保存 Contract
        contract_path = task_dir / "contract.json"
        contract.to_json_file(str(contract_path))

        # 固化契约快照（UniLab contract_snapshot 语义，报告 7 §3）：训练时刻的
        # 包契约 v3（缺则 v2 导出）。导出 DENYLIST gate 以此为训练侧真值，
        # 契约漂移在导出时被 fail-closed 拦截。
        snapshot = _package_contract_snapshot(str(contract.robot_id))
        if snapshot is not None:
            (task_dir / "contract_snapshot.json").write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        # B9 Run 一等对象：四件套在**启动训练之前**落盘（fail-closed）。
        # 档案写不出来就不开训 —— 否则会产出一份无法回溯的 Run；此时 worker 还没起，
        # 拦下来的代价为零。（task_dir 即 Run 目录，run_id 即 task_id）
        from backend.training.runs import create_run_for_task

        run_record = create_run_for_task(task_dir, contract=contract, config=config, task=task_id)
        print(
            f"[Manager] Run archive: {run_record.run_id} "
            f"digest={run_record.inputs_digest[:12]} lock={Path(run_record.environment_lock_path).name}"
        )

        # 创建任务对象
        task = TrainingTask(
            task_id=task_id,
            contract=contract,
            config=config,
            task_dir=task_dir
        )

        self.tasks[task_id] = task

        (task_dir / "status.json").write_text(
            json.dumps({"status": "pending", "pid": None, "exit_code": None}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # 启动训练
        self.launcher.launch_training(
            contract_path=str(contract_path),
            config=config,
            task_id=task_id
        )

        task.status = "running"

        if idempotency_key:
            self.register_idempotency(idempotency_key, task_id)

        print(f"[Manager] Task created: {task_id}")

        return task_id

    def get_task(self, task_id: str) -> Optional[TrainingTask]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_task_status(self, task_id: str) -> dict:
        """获取任务状态"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        return task.to_dict()

    def list_tasks(self) -> List[dict]:
        """列出所有任务"""
        return [task.to_dict() for task in self.tasks.values()]

    def stop_task(self, task_id: str):
        """停止任务"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task_id in self.launcher.processes:
            self.launcher.stop_training(task_id)
        elif task.status == "orphaned" or task.get_status_info().get("status") == "orphaned":
            # F6：控制面重启后恢复的孤儿 worker。launcher.processes 是内存态，
            # 重启后为空——只能按 status.json 记录的 pid 直接清理；pid 已先一步
            # 退出的竞态无需杀，直接落 stopped。
            pid = task.get_status_info().get("pid")
            if _pid_alive(pid):
                _terminate_orphan_worker(int(pid))
        task.status = "stopped"
        (task.task_dir / "status.json").write_text(json.dumps({"status": "stopped"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        print(f"[Manager] Task stopped: {task_id}")

    def delete_task(self, task_id: str):
        """删除任务"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # 先停止
        if task.status == "running":
            self.stop_task(task_id)

        # 删除目录（可选）
        # import shutil
        # shutil.rmtree(task.task_dir)

        # 从列表移除
        del self.tasks[task_id]

        print(f"[Manager] Task deleted: {task_id}")

    def cleanup(self):
        """清理所有任务"""
        for task_id in list(self.tasks.keys()):
            try:
                if self.tasks[task_id].status == "running":
                    self.stop_task(task_id)
            except Exception as e:
                print(f"[Manager] Error stopping {task_id}: {e}")

        self.launcher.cleanup()

    def _generate_task_id(self, contract_id: str) -> str:
        """生成任务 ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base = f"{contract_id}_{timestamp}"
        candidate = base
        suffix = 1
        while candidate in self.tasks or (self.workspace_dir / candidate).exists():
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate


# ========== 全局管理器实例 ==========
_global_manager: Optional[TrainingManager] = None


def get_training_manager() -> TrainingManager:
    """获取全局训练管理器"""
    global _global_manager
    if _global_manager is None:
        _global_manager = TrainingManager()
    return _global_manager


def shutdown_global_manager() -> bool:
    """控制面退出清理入口（F6：训练进程生命周期无僵尸）。

    只在全局实例已存在时执行 cleanup——训练栈从未被使用就不在退出路径上
    构造 TrainingManager（构造会扫描 workspace 并触发孤儿判定的写盘副作用，
    退出时不宜引入新副作用）。返回是否执行了清理，供 lifespan 接线方与测试确认。
    """
    if _global_manager is None:
        return False
    _global_manager.cleanup()
    return True


if __name__ == "__main__":
    # 测试
    from contracts.robot_contract_v2 import create_go2_contract

    manager = TrainingManager()

    # 创建任务
    contract = create_go2_contract()
    task_id = manager.create_task(
        contract=contract,
        config={
            "algorithm": "PPO",
            "num_envs": 64,
            "max_iterations": 5
        }
    )

    print(f"\nTask created: {task_id}")

    # 查看状态
    import time
    for i in range(10):
        status = manager.get_task_status(task_id)
        print(f"\nIteration {i}:")
        print(f"  Status: {status['status']}")
        print(f"  Progress: {status['progress'] * 100:.1f}%")
        print(f"  Reward: {status['reward']:.2f}")

        if status['status'] != 'running':
            break

        time.sleep(2)

    print("\nTest completed!")
