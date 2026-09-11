# tron1-rl-isaaclab — 参考资源

> **来源**：`00_open/tron1-rl-isaaclab/`　｜　**类型**：参考项目
> **关联机型**：limx_tron1_pf（逐际动力 TRON1-PF）、limx_tron1_sf（逐际动力 TRON1-SF）、limx_tron1_wf（逐际动力 TRON1-WF）
> **定位**：TRON1 IsaacLab RL 训练工程
> **收录**：80 个文件 / 310 KB（其中推理策略/模型文件 0 个）
> **已省略**：12 个文件 / 79.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **RL 训练工程**（3 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（3 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（42 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（32 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （5 个文件）
exts/  （45 个文件）
    bipedal_locomotion/
rsl_rl/  （27 个文件）
    (直接文件)/
    licenses/
    rsl_rl/
scripts/  （3 个文件）
    rsl_rl/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 53 |
| `.txt` | 11 |
| `(无扩展名)` | 7 |
| `.toml` | 3 |
| `.yaml` | 3 |
| `.md` | 2 |
| `.rst` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
LICENCE
README.md
README_cn.md
exts/bipedal_locomotion/bipedal_locomotion/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/assets/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/assets/config/pointfoot_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/assets/config/solefoot_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/assets/config/wheelfoot_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/assets/usd/.asset_hash
exts/bipedal_locomotion/bipedal_locomotion/assets/usd/PF_TRON1A/.asset_hash
exts/bipedal_locomotion/bipedal_locomotion/assets/usd/PF_TRON1A/config.yaml
exts/bipedal_locomotion/bipedal_locomotion/assets/usd/SF_TRON1A/.asset_hash
exts/bipedal_locomotion/bipedal_locomotion/assets/usd/SF_TRON1A/config.yaml
exts/bipedal_locomotion/bipedal_locomotion/assets/usd/WF_TRON1A/.asset_hash
exts/bipedal_locomotion/bipedal_locomotion/assets/usd/WF_TRON1A/config.yaml
exts/bipedal_locomotion/bipedal_locomotion/tasks/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/agents/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/agents/limx_rsl_rl_ppo_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/PF/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/PF/limx_base_env_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/PF/terrains_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/SF/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/SF/limx_base_env_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/SF/terrains_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/WF/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/WF/limx_base_env_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/WF/terrains_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/cfg/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/mdp/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/mdp/commands/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/mdp/commands/commands_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/mdp/commands/gait_command.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/mdp/curriculums.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/mdp/events.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/mdp/observations.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/mdp/rewards.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/robots/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/robots/limx_pointfoot_env_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/robots/limx_solefoot_env_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/tasks/locomotion/robots/limx_wheelfoot_env_cfg.py
exts/bipedal_locomotion/bipedal_locomotion/ui_extension_example.py
exts/bipedal_locomotion/bipedal_locomotion/utils/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/utils/wrappers/rsl_rl/__init__.py
exts/bipedal_locomotion/bipedal_locomotion/utils/wrappers/rsl_rl/rl_mlp_cfg.py
exts/bipedal_locomotion/config/extension.toml
exts/bipedal_locomotion/docs/CHANGELOG.rst
exts/bipedal_locomotion/setup.py
pyproject.toml
rsl_rl/.gitignore
rsl_rl/__init__.py
rsl_rl/licenses/dependencies/black-license.txt
rsl_rl/licenses/dependencies/codespell-license.txt
rsl_rl/licenses/dependencies/flake8-license.txt
rsl_rl/licenses/dependencies/isort-license.txt
rsl_rl/licenses/dependencies/numpy_license.txt
rsl_rl/licenses/dependencies/onnx-license.txt
rsl_rl/licenses/dependencies/pre-commit-hooks-license.txt
rsl_rl/licenses/dependencies/pre-commit-license.txt
rsl_rl/licenses/dependencies/pyright-license.txt
rsl_rl/licenses/dependencies/pyupgrade-license.txt
rsl_rl/licenses/dependencies/torch_license.txt
rsl_rl/pyproject.toml
rsl_rl/rsl_rl/__init__.py
rsl_rl/rsl_rl/algorithm/__init__.py
rsl_rl/rsl_rl/algorithm/ppo.py
rsl_rl/rsl_rl/env/__init__.py
rsl_rl/rsl_rl/env/vec_env.py
rsl_rl/rsl_rl/modules/__init__.py
rsl_rl/rsl_rl/modules/actor_critic.py
rsl_rl/rsl_rl/modules/mlp_encoder.py
rsl_rl/rsl_rl/runner/__init__.py
rsl_rl/rsl_rl/runner/on_policy_runner.py
rsl_rl/rsl_rl/storage/__init__.py
rsl_rl/rsl_rl/storage/rollout_storage.py
rsl_rl/setup.py
scripts/rsl_rl/cli_args.py
scripts/rsl_rl/play.py
scripts/rsl_rl/train.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `exts/bipedal_locomotion/bipedal_locomotion/assets/usd/PF_TRON1A` | 1 | 2 KB | [`exts/bipedal_locomotion/bipedal_locomotion/assets/usd/PF_TRON1A/_OMITTED.md`](./exts/bipedal_locomotion/bipedal_locomotion/assets/usd/PF_TRON1A/_OMITTED.md) |
| `exts/bipedal_locomotion/bipedal_locomotion/assets/usd/PF_TRON1A/configuration` | 3 | 24.7 MB | [`exts/bipedal_locomotion/bipedal_locomotion/assets/usd/PF_TRON1A/configuration/_OMITTED.md`](./exts/bipedal_locomotion/bipedal_locomotion/assets/usd/PF_TRON1A/configuration/_OMITTED.md) |
| `exts/bipedal_locomotion/bipedal_locomotion/assets/usd/SF_TRON1A` | 1 | 2 KB | [`exts/bipedal_locomotion/bipedal_locomotion/assets/usd/SF_TRON1A/_OMITTED.md`](./exts/bipedal_locomotion/bipedal_locomotion/assets/usd/SF_TRON1A/_OMITTED.md) |
| `exts/bipedal_locomotion/bipedal_locomotion/assets/usd/SF_TRON1A/configuration` | 3 | 26.7 MB | [`exts/bipedal_locomotion/bipedal_locomotion/assets/usd/SF_TRON1A/configuration/_OMITTED.md`](./exts/bipedal_locomotion/bipedal_locomotion/assets/usd/SF_TRON1A/configuration/_OMITTED.md) |
| `exts/bipedal_locomotion/bipedal_locomotion/assets/usd/WF_TRON1A` | 1 | 2 KB | [`exts/bipedal_locomotion/bipedal_locomotion/assets/usd/WF_TRON1A/_OMITTED.md`](./exts/bipedal_locomotion/bipedal_locomotion/assets/usd/WF_TRON1A/_OMITTED.md) |
| `exts/bipedal_locomotion/bipedal_locomotion/assets/usd/WF_TRON1A/configuration` | 3 | 27.6 MB | [`exts/bipedal_locomotion/bipedal_locomotion/assets/usd/WF_TRON1A/configuration/_OMITTED.md`](./exts/bipedal_locomotion/bipedal_locomotion/assets/usd/WF_TRON1A/configuration/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
