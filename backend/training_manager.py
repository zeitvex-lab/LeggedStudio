"""
Training Manager
训练任务管理器
"""

from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import json
import os

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
                task.status = task.get_status_info().get("status", "completed" if (task_dir / "artifact.json").exists() else "pending")
                self.tasks[task.task_id] = task
            except Exception as exc:
                print(f"[Manager] Failed to recover {task_dir.name}: {exc}")

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
