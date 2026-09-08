# tools/ 工具链

机器人资产与训练配置的开发期工具（不进入运行时/发布包）。

## 全量训练验证器（重点）

`validate_training_smoke.py` 批量校验所有机器人训练 profile——逐个以独立子进程构建环境并做 rollout，确认 env 能建、观测/动作/奖励/终止完整、奖励有限。

```bash
# 默认：128 并行环境 × 30 步 rollout，校验全部 55 个 profile
python tools/validate_training_smoke.py --num-envs 128 --rollout-steps 30 --report workspace/validation/report.json

# 短训练 sanity check（验证 PPO 能跑、loss 有限）
python tools/validate_training_smoke.py --mode train --iters 30
```

关键设计：**子进程隔离**（`_smoke_one.py`）——不同包源码的 `sys.path` 不互相污染，避免模块名冲突（如多个 `velocity_env_cfg` 解析到错误的文件）。每个 profile 独立 python 子进程，进程内构造 `ManagerBasedRlEnv`（注意 mjlab 1.6 需 `device=` 参数、`env.step(action)` 签名）。

配套：每日 4:00 定时任务自动跑全量验证 + 读报告修失败项（见 workspace 配置），修复后以 `[auto-fix]` 前缀提交。

## 模型转换

- `urdf_to_mjcf.py`：URDF → MJCF 转换（MjSpec）。
- `convert_raw_motion_pkls.py`：动作库 raw 变体 pkl 转换（按关键体名选列 + 有限差分补速度，输出 tracking-loader 兼容 schema）。

## 地形生成（rough 场景可再生产物）

```bash
# MjSpec 程序化地形（平地+box 障碍），桌面 Python：
python -c "
import sys; sys.path.insert(0, 'adapters/mjlab')
from scene_builder import build_flat_scene, add_box_obstacles
..."
```

复杂 hfield 地形参照 unitree_rl_mjlab `scene_terrain.xml` + `visualize_terrain.py`（生成脚本待引入）。
