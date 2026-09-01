"""
Training Manager
训练任务管理器
"""

from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import json
import os

from adapters.mjlab_new.launcher import TrainingLauncher
from contracts.robot_contract_v2 import RobotContractV2


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
        self._load_existing_tasks()

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

    def create_task(
        self,
        contract: RobotContractV2,
        config: dict
    ) -> str:
        """
        创建训练任务

        Args:
            contract: Robot Contract
            config: 训练配置

        Returns:
            task_id: 任务 ID
        """
        # 生成任务 ID
        task_id = self._generate_task_id(contract.contract_id)

        # 创建任务目录
        task_dir = self.workspace_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=False)

        # 保存 Contract
        contract_path = task_dir / "contract.json"
        contract.to_json_file(str(contract_path))

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
