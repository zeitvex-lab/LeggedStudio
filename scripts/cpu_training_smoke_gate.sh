#!/usr/bin/env bash
#
# CPU 训练冒烟门禁（CI 与本地共用）。
#
# 为什么要有这条门禁：
#   控制面测试全绿 ≠ 训练链路能跑。历史上"训练创建入口调不通"就是靠单测
#   盲区漏过去的（见 PR #32）。这条门禁用**真实 PPO 回路**守住三件事：
#     1. 训练栈（torch/mjlab/warp）在纯 CPU 上可导入并真的建起 env；
#     2. rollout 的 reward 有限（不 NaN/不恒 0），即接口是通的；
#     3. 跑 N 轮 PPO 更新（权重在动、loss 有限），即"训练"而不是"只 reset"。
#
# 判据来源：tools/validate_training_smoke.py --mode train 的 JSON 报告。
# 设备：显式要求 cuda 不可用（否则门禁语义随 runner 漂移，见下方断言）。
#
# 用法：
#   bash scripts/cpu_training_smoke_gate.sh
# 环境变量：
#   LEGGED_STUDIO_MJLAB_VENV   训练 venv 落点（默认 adapters/mjlab/.venv）
#   SMOKE_PROFILE              聚焦 profile（默认 go2-velocity-flat）
#   SMOKE_ROBOT                聚焦 robot（默认 unitree_go2）
#   SMOKE_NUM_ENVS             并行环境数（默认 16）
#   SMOKE_ITERS                PPO 轮数（默认 5）
#
# 规模默认值取"判据强度不变、墙钟最短"档：门禁只守回路通不通（可导入 /
# reward 有限 / 权重在动 / time_outs 已接线），这三件事在 16x5 上就能验到。
# 需要更长冒烟时本地覆盖：SMOKE_NUM_ENVS=64 SMOKE_ITERS=20 bash <此脚本>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR="${LEGGED_STUDIO_MJLAB_VENV:-$ROOT/adapters/mjlab/.venv}"
PY="$VENV_DIR/bin/python"
ROBOT="${SMOKE_ROBOT:-unitree_go2}"
PROFILE="${SMOKE_PROFILE:-go2-velocity-flat}"
NUM_ENVS="${SMOKE_NUM_ENVS:-16}"
ITERS="${SMOKE_ITERS:-5}"
REPORT="${SMOKE_REPORT:-workspace/validation/cpu-training-smoke.json}"

# 无显示环境下 MuJoCo 不需要 GL 上下文：显式关掉，避免容器缺 EGL/OSMesa 时报错。
export MUJOCO_GL="${MUJOCO_GL:-disabled}"

echo "== 训练栈形态自检 =="
if [ ! -x "$PY" ]; then
    echo "::error::CPU 训练 venv 缺失：$VENV_DIR（先跑 scripts/provision_cpu_training.sh）"
    exit 1
fi
"$PY" - <<'PY'
import torch, mjlab, warp, mujoco_warp  # noqa: F401

cuda = torch.cuda.is_available()
print(f"torch={torch.__version__} cuda_available={cuda} MUJOCO_GL=disabled")
# 门禁必须在纯 CPU 上跑：否则"CPU 链路可用"这个结论会被 GPU 掩盖。
assert not cuda, "本门禁要求纯 CPU（CUDA 可用会让判据失去意义）"
PY

echo "== 训练栈适配器测试（adapters/mjlab，纯 CPU、1~2 环境） =="
# 为什么把这几条显式列进来：`backend` 的 discover 扫不到 `adapters/`，
# 而 `.cnb.yml` 里原先只登记了 adapters.github —— 于是**族架构的核心不变量
# （动作接口序 = 契约动作序）与族级技能工厂的回归锁一直"存在但 CI 看不见"**，
# 正是 B16 记过的那个坑。这里随训练栈一起跑（它们只用 cpu device + 1~2 环境，
# 不依赖 GPU）。新增族级技能时把对应 test 模块补进这一行。
"$PY" -m unittest \
    adapters.mjlab.test_action_order_matches_contract \
    adapters.mjlab.test_joint_actions \
    adapters.mjlab.test_family_skill_assembly \
    adapters.mjlab.test_quadruped_velocity_skill \
    adapters.mjlab.test_quadruped_stance_skill \
    adapters.mjlab.test_wheel_leg_velocity_skill

echo "== 真实 CPU 训练冒烟：${NUM_ENVS} envs x ${ITERS} iters PPO =="
# 用训练 venv 的解释器跑工具：它同时具备控制面依赖与训练栈（本地/CI 一致）。
"$PY" tools/validate_training_smoke.py \
    --robot "$ROBOT" \
    --profile "$PROFILE" \
    --mode train \
    --num-envs "$NUM_ENVS" \
    --rollout-steps 10 \
    --iters "$ITERS" \
    --report "$REPORT"

echo "== 断言冒烟报告 =="
SMOKE_REPORT="$REPORT" "$PY" - <<'PY'
import json
import os
import pathlib
import sys

report_path = pathlib.Path(os.environ["SMOKE_REPORT"])
report = json.loads(report_path.read_text(encoding="utf-8"))
results = report.get("results") or []
if not results:
    sys.exit("::error::冒烟报告没有 profile 结果——命令被静默跳过？")
bad = [r for r in results if r.get("status") != "ok"]
if bad:
    sys.exit("::error::CPU 训练冒烟失败: " + json.dumps(bad, ensure_ascii=False)[:800])
rewards = [r.get("rewards") for r in results if r.get("rewards") is not None]
if not rewards:
    sys.exit("::error::冒烟未产出 rewards——没跑到真实训练回路")
if any(r.get("time_outs_wired") is not True for r in results if r.get("iters")):
    sys.exit("::error::time_outs 未接线：GAE 会把超时当终止，critic 会系统性低估长 episode")
print(f"CPU 训练冒烟通过：{len(results)} profile, rewards={rewards}")
PY
