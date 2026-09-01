"""
MJLab Training Launcher
独立进程启动器（基于 RoboLab 的进程管理模式）
"""

import subprocess
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class TrainingLauncher:
    """训练启动器 - 独立进程管理"""

    def __init__(self, workspace_dir: str = "workspace"):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.processes = {}  # task_id -> subprocess.Popen

    def launch_training(
        self,
        contract_path: str,
        config: dict,
        task_id: Optional[str] = None
    ) -> str:
        """
        启动训练进程

        Args:
            contract_path: Contract JSON 文件路径
            config: 训练配置字典
            task_id: 任务 ID，None 自动生成

        Returns:
            task_id: 任务 ID
        """
        if task_id is None:
            task_id = self._generate_task_id()

        # 创建任务目录
        task_dir = self.workspace_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        # 保存配置
        config_path = task_dir / "training_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        # 准备命令
        mjlab_venv = self._find_mjlab_venv()
        python_exe = mjlab_venv / "Scripts" / "python.exe" if mjlab_venv else sys.executable

        worker_script = Path(__file__).parent / "train_worker.py"

        cmd = [
            str(python_exe),
            str(worker_script),
            "--contract", str(contract_path),
            "--config", str(config_path),
            "--output", str(task_dir),
            "--task-id", task_id
        ]

        # 启动进程
        log_file = task_dir / "training.log"
        log_handle = open(log_file, 'w', encoding='utf-8')

        process = subprocess.Popen(
            cmd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            cwd=Path(__file__).parent.parent.parent,
            env=self._prepare_env()
        )

        self.processes[task_id] = {
            "process": process,
            "log_file": log_file,
            "log_handle": log_handle,
            "task_dir": task_dir,
            "started_at": datetime.now()
        }
        self._write_status(task_dir, {"status": "running", "pid": process.pid, "exit_code": None})

        def finalize(child, directory=task_dir, identifier=task_id):
            code = child.returncode
            current = self._read_status(directory)
            if current.get("status") == "stopped":
                return
            self._write_status(directory, {
                **current,
                "status": "completed" if code == 0 else "failed",
                "pid": child.pid,
                "exit_code": code,
                "error": None if code == 0 else f"training worker exited with code {code}",
            })
            self.processes.pop(identifier, None)

        # Popen has no callback API; a lightweight watcher keeps status.json
        # authoritative without blocking the control-plane request.
        import threading
        threading.Thread(target=lambda: (process.wait(), finalize(process)), daemon=True).start()

        print(f"[Launcher] Training started: {task_id} (PID: {process.pid})")
        print(f"[Launcher] Log: {log_file}")

        return task_id

    def stop_training(self, task_id: str):
        """停止训练进程"""
        if task_id not in self.processes:
            raise ValueError(f"Task {task_id} not found")

        proc_info = self.processes[task_id]
        process = proc_info["process"]

        if process.poll() is None:  # 还在运行
            print(f"[Launcher] Stopping training: {task_id}")
            process.terminate()

            # 等待一会儿
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(f"[Launcher] Force killing: {task_id}")
                process.kill()

        # 关闭日志文件
        proc_info["log_handle"].close()

        print(f"[Launcher] Training stopped: {task_id}")

    def get_status(self, task_id: str) -> dict:
        """获取训练状态"""
        if task_id not in self.processes:
            raise ValueError(f"Task {task_id} not found")

        proc_info = self.processes[task_id]
        process = proc_info["process"]

        # 读取进度文件
        progress_file = proc_info["task_dir"] / "progress.json"
        progress = {}
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    progress = json.load(f)
            except Exception:
                pass

        status_info = self._read_status(proc_info["task_dir"])
        process_status = "running" if process.poll() is None else ("completed" if process.returncode == 0 else "failed")
        return {
            "task_id": task_id,
            "status": status_info.get("status", process_status),
            "pid": process.pid,
            "exit_code": process.poll(),
            "started_at": proc_info["started_at"].isoformat(),
            "progress": progress
        }

    @staticmethod
    def _read_status(task_dir: Path) -> dict:
        path = task_dir / "status.json"
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write_status(task_dir: Path, value: dict) -> None:
        (task_dir / "status.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def cleanup(self):
        """清理所有进程"""
        for task_id in list(self.processes.keys()):
            try:
                self.stop_training(task_id)
            except Exception as e:
                print(f"[Launcher] Error stopping {task_id}: {e}")

    def _generate_task_id(self) -> str:
        """生成任务 ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"train_{timestamp}"

    def _find_mjlab_venv(self) -> Optional[Path]:
        """查找 MJLab 虚拟环境"""
        project_root = Path(__file__).parent.parent.parent
        candidates = [
            Path(__file__).parent / ".venv",
            project_root / "adapters" / "mjlab" / ".venv",
        ]
        for mjlab_venv in candidates:
            if mjlab_venv.exists():
                return mjlab_venv
        return None

    def _prepare_env(self) -> dict:
        """准备环境变量"""
        import os
        env = os.environ.copy()

        # 添加项目路径
        project_root = Path(__file__).parent.parent.parent
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{project_root}{os.pathsep}{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = str(project_root)

        # UTF-8 编码
        env["PYTHONIOENCODING"] = "utf-8"

        return env


# ========== 便捷函数 ==========

def launch_training_from_contract(
    contract_path: str,
    algorithm: str = "PPO",
    num_envs: int = 4096,
    max_iterations: int = 1000,
    **kwargs
) -> str:
    """
    从 Contract 文件启动训练

    Args:
        contract_path: Contract JSON 路径
        algorithm: 算法名称
        num_envs: 环境数量
        max_iterations: 最大迭代数
        **kwargs: 其他训练参数

    Returns:
        task_id: 任务 ID
    """
    config = {
        "algorithm": algorithm,
        "num_envs": num_envs,
        "max_iterations": max_iterations,
        **kwargs
    }

    launcher = TrainingLauncher()
    task_id = launcher.launch_training(
        contract_path=contract_path,
        config=config
    )

    return task_id


if __name__ == "__main__":
    # 测试
    from contracts.robot_contract_v2 import create_go2_contract

    # 创建测试 Contract
    contract = create_go2_contract()
    contract_path = "outputs/test_contract.json"
    contract.to_json_file(contract_path)

    # 启动训练
    launcher = TrainingLauncher()

    task_id = launcher.launch_training(
        contract_path=contract_path,
        config={
            "algorithm": "PPO",
            "num_envs": 64,
            "max_iterations": 5
        }
    )

    print(f"\nTask started: {task_id}")
    print("Check status with:")
    print(f"  launcher.get_status('{task_id}')")

    # 等待完成
    import time
    while True:
        status = launcher.get_status(task_id)
        print(f"\nStatus: {status['status']}")
        if status['progress']:
            print(f"Progress: {status['progress']}")

        if status["status"] != "running":
            break

        time.sleep(2)

    print("\nTraining completed!")
