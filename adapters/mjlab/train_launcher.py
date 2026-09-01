"""
训练启动器 - MJLab Adapter
用于启动 MJLab 训练任务
"""

import subprocess
import sys
import os
from pathlib import Path


ADAPTER_ROOT = Path(__file__).parent
VENV_PYTHON = ADAPTER_ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def check_environment():
    """检查环境是否就绪"""
    if not VENV_PYTHON.exists():
        print("ERROR: MJLab adapter environment not found")
        print(f"Expected: {VENV_PYTHON}")
        print("\nPlease run: uv sync --project adapters/mjlab --python 3.12 --extra cu128")
        return False

    print("OK: MJLab adapter environment exists")
    return True


def run_smoke_test():
    """
    运行 smoke test（最小训练验证）
    参考：Microduck AGENTS.md
    """
    print("\n" + "=" * 60)
    print("MJLab Smoke Test")
    print("=" * 60)

    cmd = [
        str(VENV_PYTHON),
        "-c",
        """
import sys
print(f'Python: {sys.version}')

try:
    import mjlab
    print('OK: MJLab imported successfully')
except ImportError as e:
    print(f'ERROR: MJLab import failed: {e}')
    sys.exit(1)

try:
    import torch
    print(f'OK: PyTorch {torch.__version__}')
    print(f'OK: CUDA available: {torch.cuda.is_available()}')
except ImportError as e:
    print(f'ERROR: PyTorch import failed: {e}')
    sys.exit(1)

try:
    import warp as wp
    print('OK: Warp imported successfully')
except ImportError as e:
    print(f'ERROR: Warp import failed: {e}')
    sys.exit(1)

print('\\nOK: Smoke test passed')
"""
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    return result.returncode == 0


def start_training(config_path: str, **kwargs):
    """
    启动训练

    参数：
        config_path: 训练配置文件路径
        **kwargs: 其他训练参数
    """
    print("\n" + "=" * 60)
    print("Starting Training")
    print("=" * 60)

    # TODO: 根据 MJLab 实际接口实现
    # 参考 Microduck 的训练命令

    cmd = [
        str(VENV_PYTHON),
        "-m", "mjlab.train",  # 假设的入口
        "--config", config_path,
    ]

    # 添加额外参数
    for key, value in kwargs.items():
        cmd.extend([f"--{key}", str(value)])

    print(f"Command: {' '.join(cmd)}")
    print()

    # 执行
    result = subprocess.run(cmd, encoding='utf-8', errors='replace')
    return result.returncode


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MJLab Training Launcher")
    parser.add_argument("--check", action="store_true", help="Check environment")
    parser.add_argument("--smoke-test", action="store_true", help="Run smoke test")
    parser.add_argument("--train", type=str, help="Start training (config file path)")
    parser.add_argument("--num-envs", type=int, default=64, help="Number of environments")
    parser.add_argument("--max-iterations", type=int, default=1000, help="Max iterations")

    args = parser.parse_args()

    if args.check:
        if check_environment():
            sys.exit(0)
        else:
            sys.exit(1)

    elif args.smoke_test:
        if not check_environment():
            sys.exit(1)

        if run_smoke_test():
            print("\nOK: Smoke test successful")
            sys.exit(0)
        else:
            print("\nERROR: Smoke test failed")
            sys.exit(1)

    elif args.train:
        if not check_environment():
            sys.exit(1)

        exit_code = start_training(
            args.train,
            num_envs=args.num_envs,
            max_iterations=args.max_iterations
        )
        sys.exit(exit_code)

    else:
        parser.print_help()
