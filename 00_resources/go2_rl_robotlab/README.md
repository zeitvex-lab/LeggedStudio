# go2_rl_robotlab — 参考资源

> **来源**：`00_open/go2_rl_robotlab/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：基于 robot_lab 的 Go2 训练工程（IsaacLab）
> **收录**：104 个文件 / 12.8 MB（其中推理策略/模型文件 2 个）
> **已省略**：27 个文件 / 56.3 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（6 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（16 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（5 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（3 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **评测与测试**（3 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（71 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
deploy/  （5 个文件）
    deploy_mujoco/
    pre_train/
resources/  （6 个文件）
    go2/
scripts/  （8 个文件）
    rsl_rl/
    tools/
source/  （81 个文件）
    robot_lab/
    rsl_rl/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 70 |
| `.txt` | 10 |
| `(无扩展名)` | 5 |
| `.xml` | 5 |
| `.toml` | 4 |
| `.md` | 3 |
| `.yaml` | 3 |
| `.onnx` | 1 |
| `.pt` | 1 |
| `.urdf` | 1 |
| `.cff` | 1 |

## 文件索引（项目内相对路径）

```text
.flake8
.gitignore
LICENSE
README.md
deploy/deploy_mujoco/configs/go2.yaml
deploy/deploy_mujoco/deploy_go2.py
deploy/deploy_mujoco/utils.py
deploy/pre_train/go2/go2_moe_cts_176k_0.6984.onnx
deploy/pre_train/go2/go2_moe_cts_176k_0.6984.pt
resources/go2/boxes.xml
resources/go2/flat.xml
resources/go2/go2.xml
resources/go2/stairs.xml
resources/go2/stairs_and_slope.xml
resources/go2/urdf/go2.urdf
scripts/rsl_rl/cli_args.py
scripts/rsl_rl/play.py
scripts/rsl_rl/train.py
scripts/rsl_rl/utils.py
scripts/tools/clean_trash.py
scripts/tools/convert_mjcf.py
scripts/tools/convert_urdf.py
scripts/tools/list_envs.py
source/robot_lab/config/extension.toml
source/robot_lab/pyproject.toml
source/robot_lab/robot_lab/__init__.py
source/robot_lab/robot_lab/assets/__init__.py
source/robot_lab/robot_lab/assets/unitree.py
source/robot_lab/robot_lab/assets/unitree_actuator.py
source/robot_lab/robot_lab/tasks/__init__.py
source/robot_lab/robot_lab/tasks/go2/__init__.py
source/robot_lab/robot_lab/tasks/go2/env/go2_env.py
source/robot_lab/robot_lab/tasks/go2/env_cfg.py
source/robot_lab/robot_lab/tasks/go2/manager/action_manager.py
source/robot_lab/robot_lab/tasks/go2/mdp/__init__.py
source/robot_lab/robot_lab/tasks/go2/mdp/commands.py
source/robot_lab/robot_lab/tasks/go2/mdp/curriculums.py
source/robot_lab/robot_lab/tasks/go2/mdp/events.py
source/robot_lab/robot_lab/tasks/go2/mdp/observations.py
source/robot_lab/robot_lab/tasks/go2/mdp/rewards.py
source/robot_lab/robot_lab/tasks/go2/mdp/terrains.py
source/robot_lab/robot_lab/tasks/go2/mdp/utils.py
source/robot_lab/robot_lab/tasks/go2/rsl_rl_cfg.py
source/robot_lab/robot_lab/ui_extension_example.py
source/robot_lab/setup.py
source/rsl_rl/.gitignore
source/rsl_rl/.pre-commit-config.yaml
source/rsl_rl/CITATION.cff
source/rsl_rl/CONTRIBUTORS.md
source/rsl_rl/LICENSE
source/rsl_rl/README.md
source/rsl_rl/config/example_config.yaml
source/rsl_rl/licenses/dependencies/codespell-license.txt
source/rsl_rl/licenses/dependencies/numpy-license.txt
source/rsl_rl/licenses/dependencies/onnx-license.txt
source/rsl_rl/licenses/dependencies/onnxscript-license.txt
source/rsl_rl/licenses/dependencies/pre-commit-hooks-license.txt
source/rsl_rl/licenses/dependencies/pre-commit-license.txt
source/rsl_rl/licenses/dependencies/pyright-license.txt
source/rsl_rl/licenses/dependencies/ruff-license.txt
source/rsl_rl/licenses/dependencies/tensordict-license.txt
source/rsl_rl/licenses/dependencies/torch-license.txt
source/rsl_rl/pyproject.toml
source/rsl_rl/rsl_rl/__init__.py
source/rsl_rl/rsl_rl/algorithms/__init__.py
source/rsl_rl/rsl_rl/algorithms/distillation.py
source/rsl_rl/rsl_rl/algorithms/moe_cts.py
source/rsl_rl/rsl_rl/algorithms/ppo.py
source/rsl_rl/rsl_rl/env/__init__.py
source/rsl_rl/rsl_rl/env/vec_env.py
source/rsl_rl/rsl_rl/modules/__init__.py
source/rsl_rl/rsl_rl/modules/actor_critic.py
source/rsl_rl/rsl_rl/modules/actor_critic_cnn.py
source/rsl_rl/rsl_rl/modules/actor_critic_moe_cts.py
source/rsl_rl/rsl_rl/modules/actor_critic_recurrent.py
source/rsl_rl/rsl_rl/modules/rnd.py
source/rsl_rl/rsl_rl/modules/student_teacher.py
source/rsl_rl/rsl_rl/modules/student_teacher_recurrent.py
source/rsl_rl/rsl_rl/modules/symmetry.py
source/rsl_rl/rsl_rl/networks/__init__.py
source/rsl_rl/rsl_rl/networks/cnn.py
source/rsl_rl/rsl_rl/networks/memory.py
source/rsl_rl/rsl_rl/networks/mlp.py
source/rsl_rl/rsl_rl/networks/moe.py
source/rsl_rl/rsl_rl/networks/normalization.py
source/rsl_rl/rsl_rl/runners/__init__.py
source/rsl_rl/rsl_rl/runners/distillation_runner.py
source/rsl_rl/rsl_rl/runners/on_policy_runner.py
source/rsl_rl/rsl_rl/runners/on_policy_runner_cts.py
source/rsl_rl/rsl_rl/storage/__init__.py
source/rsl_rl/rsl_rl/storage/rollout_storage.py
source/rsl_rl/rsl_rl/storage/rollout_storage_cts.py
source/rsl_rl/rsl_rl/utils/__init__.py
source/rsl_rl/rsl_rl/utils/exporter_cts.py
source/rsl_rl/rsl_rl/utils/logger.py
source/rsl_rl/rsl_rl/utils/logger_cts.py
source/rsl_rl/rsl_rl/utils/neptune_utils.py
source/rsl_rl/rsl_rl/utils/utils.py
source/rsl_rl/rsl_rl/utils/wandb_utils.py
source/rsl_rl/ruff.toml
source/rsl_rl/setup.py
source/rsl_rl/tests/__init__.py
source/rsl_rl/tests/utils/__init__.py
source/rsl_rl/tests/utils/test_resolve_callable.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `resources/go2/assets` | 18 | 28.7 MB | [`resources/go2/assets/_OMITTED.md`](./resources/go2/assets/_OMITTED.md) |
| `resources/go2/meshes` | 7 | 24.7 MB | [`resources/go2/meshes/_OMITTED.md`](./resources/go2/meshes/_OMITTED.md) |
| `resources/results` | 2 | 2.8 MB | [`resources/results/_OMITTED.md`](./resources/results/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
