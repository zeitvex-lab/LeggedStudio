# Installation Guide

## System Requirements

- **Operating System**: Ubuntu 22.04 recommended
- **GPU**: NVIDIA GPU recommended for training
- **Driver Version**: 550 or later recommended

## 1. Create A Python Environment

It is recommended to run training and deployment tools inside a virtual
environment. Conda is the easiest option.

If Conda is already installed on your machine, skip the MiniConda installation
step and create the environment directly.

### 1.1 Install MiniConda

```bash
mkdir -p ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
rm ~/miniconda3/miniconda.sh
~/miniconda3/bin/conda init --all
source ~/.bashrc
```

### 1.2 Create And Activate The Environment

```bash
conda create -n unitree_rl_mjlab python=3.11
conda activate unitree_rl_mjlab
```

## 2. Clone The Repository

Clone this repository and enter the workspace:

```bash
git clone https://github.com/koki67/unitree_rl_mjlab_go2w.git
cd unitree_rl_mjlab_go2w
```

## 3. Install System Dependencies

Install the required C++ and system libraries:

```bash
sudo apt install -y libyaml-cpp-dev libboost-all-dev libeigen3-dev libspdlog-dev libfmt-dev
```

## 4. Install Python Dependencies

Install the repository in editable mode:

```bash
pip install -e .
```

This installs the Python dependencies declared by this repository, including
MuJoCo, Warp, and `mujoco-warp`.

If you want, upgrade `pip` first:

```bash
pip install --upgrade pip
```

## 5. Sanity Checks

After installation, verify that the task registry and CLI are available:

```bash
python scripts/list_envs.py
python scripts/train.py go2w-flat --help
python scripts/play.py go2w-flat --help
```

If these commands work, the Python side of the installation is ready.

## 6. Notes

- Training normally assumes GPU-backed execution.
- Deployment has additional dependencies under `deploy/` and may require
  `cyclonedds` and `unitree_sdk2` depending on your target robot and workflow.
- Motion-tracking workflows also use `scripts/csv_to_npz.py` to convert source
  motion files into the expected `.npz` format.

## Summary

After these steps, the repository is ready for:

- task development
- short training and play smoke tests
- longer RL experiments
- policy export and deployment work
