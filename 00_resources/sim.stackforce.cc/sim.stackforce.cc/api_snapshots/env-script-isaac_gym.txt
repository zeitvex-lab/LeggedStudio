#!/usr/bin/env bash
set -euo pipefail

# StackForce SimReady Isaac Gym / legged_gym environment bootstrap.
# Tested target: Isaac Gym Preview 4 / 1.0rc4, Python 3.8, Torch 2.4.1 cu121.
# NVIDIA Isaac Gym must be downloaded manually because NVIDIA gates the package behind its license/login.
# Set ISAAC_GYM_ROOT=/path/to/isaacgym before running if it is not in a common folder.

ENV_NAME="${ENV_NAME:-env_isaacgym}"
LEGGED_GYM_EX_DIR="${LEGGED_GYM_EX_DIR:-$HOME/leggedgymex/LeggedGym-Ex}"
ISAAC_GYM_ROOT="${ISAAC_GYM_ROOT:-}"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda was not found. Install Miniconda/Anaconda first, then rerun this script." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git was not found. Install git first, then rerun this script." >&2
  exit 1
fi

if [ -z "$ISAAC_GYM_ROOT" ]; then
  for candidate in "$HOME/isaacgym" "$HOME/IsaacGym" "$HOME/Downloads/isaacgym" "$HOME/Downloads/IsaacGym_Preview_4_Package/isaacgym"; do
    if [ -d "$candidate/python" ]; then
      ISAAC_GYM_ROOT="$candidate"
      break
    fi
  done
fi

if [ -z "$ISAAC_GYM_ROOT" ] || [ ! -d "$ISAAC_GYM_ROOT/python" ]; then
  echo "Isaac Gym was not found." >&2
  echo "Download Isaac Gym Preview 4 from NVIDIA, extract it, then rerun:" >&2
  echo "  ISAAC_GYM_ROOT=/path/to/isaacgym $0" >&2
  exit 2
fi

CONDA_BASE="$(conda info --base)"
source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -n "$ENV_NAME" python=3.8 -y
fi
conda activate "$ENV_NAME"

python -m pip install --upgrade pip setuptools wheel
python -m pip install torch==2.4.1+cu121 torchvision==0.19.1+cu121 --index-url https://download.pytorch.org/whl/cu121
python -m pip install numpy==1.24.1 pandas==2.0.3 scipy==1.10.1 matplotlib==3.7.5 tensorboard tqdm xlsxwriter wandb trimesh pygame "fsspec<=2025.3.0" onnx
python -m pip install -e "$ISAAC_GYM_ROOT/python"

if [ ! -d "$LEGGED_GYM_EX_DIR/.git" ]; then
  mkdir -p "$(dirname "$LEGGED_GYM_EX_DIR")"
  git clone https://github.com/lupinjia/LeggedGym-Ex.git "$LEGGED_GYM_EX_DIR"
fi

python -m pip install -e "$LEGGED_GYM_EX_DIR" --no-deps

python - <<'PY'
import sys
import torch
import isaacgym
import legged_gym
import rsl_rl

print("StackForce Isaac Gym environment is ready.")
print("python:", sys.version.split()[0])
print("torch:", torch.__version__)
print("isaacgym path:", isaacgym.__file__)
print("legged_gym path:", legged_gym.__file__)
print("rsl_rl path:", rsl_rl.__file__)
PY

echo ""
echo "Next step for a SimReady export:"
echo "  conda activate $ENV_NAME"
echo "  cd <exported_project>"
echo "  python -m pip install -e source/<package_name>"
echo "  python scripts/list_envs.py"
echo "  python scripts/train.py --task stackforce_<task_name> --headless --num_envs 64 --max_iterations 100"
