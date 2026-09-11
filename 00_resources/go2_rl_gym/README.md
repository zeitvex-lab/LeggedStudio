# go2_rl_gym — 参考资源

> **来源**：`00_open/go2_rl_gym/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：Go2 的 legged_gym + rsl_rl 训练/回放工程（IsaacGym 系）
> **收录**：87 个文件 / 12.3 MB（其中推理策略/模型文件 3 个）
> **已省略**：29 个文件 / 53.5 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（4 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（13 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（12 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（4 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **文档与其它**（54 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （7 个文件）
deploy/  （12 个文件）
    deploy_mujoco/
    deploy_real/
    pre_train/
doc/  （2 个文件）
    (直接文件)/
legged_gym/  （22 个文件）
    (直接文件)/
    envs/
    scripts/
    utils/
resources/  （7 个文件）
    robots/
rsl_rl/  （35 个文件）
    (直接文件)/
    licenses/
    rsl_rl/
tools/  （2 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 61 |
| `.md` | 7 |
| `.xml` | 6 |
| `(无扩展名)` | 5 |
| `.pt` | 3 |
| `.yaml` | 2 |
| `.txt` | 2 |
| `.urdf` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
LICENSE
README.md
README_zh.md
UPDATE.md
cmd.md
deploy/deploy_mujoco/configs/go2.yaml
deploy/deploy_mujoco/deploy_go2.py
deploy/deploy_mujoco/utils.py
deploy/deploy_real/common/command_helper.py
deploy/deploy_real/common/remote_controller.py
deploy/deploy_real/common/rotation_helper.py
deploy/deploy_real/config_go2.py
deploy/deploy_real/configs/go2.yaml
deploy/deploy_real/deploy_real_go2.py
deploy/pre_train/go2/go2_cts_150k.pt
deploy/pre_train/go2/go2_moe_cts_137k_0.6739.pt
deploy/pre_train/go2/go2_moe_cts_high_slope_thre_164k_0.6715.pt
doc/setup_en.md
doc/setup_zh.md
legged_gym/LICENSE
legged_gym/__init__.py
legged_gym/envs/__init__.py
legged_gym/envs/base/base_config.py
legged_gym/envs/base/base_task.py
legged_gym/envs/base/legged_robot.py
legged_gym/envs/base/legged_robot_config.py
legged_gym/envs/go2/go2_config.py
legged_gym/envs/go2/go2_config_fast_flat_move.py
legged_gym/envs/go2/go2_config_vanilla.py
legged_gym/envs/go2/go2_config_vanilla_with_dynamic_cmd.py
legged_gym/envs/go2/go2_env.py
legged_gym/scripts/play.py
legged_gym/scripts/train.py
legged_gym/utils/__init__.py
legged_gym/utils/exporter.py
legged_gym/utils/helpers.py
legged_gym/utils/isaacgym_utils.py
legged_gym/utils/logger.py
legged_gym/utils/math.py
legged_gym/utils/task_registry.py
legged_gym/utils/terrain.py
resources/robots/go2/cross_slope.xml
resources/robots/go2/cross_stairs.xml
resources/robots/go2/flat.xml
resources/robots/go2/go2.xml
resources/robots/go2/race_track.xml
resources/robots/go2/stairs.xml
resources/robots/go2/urdf/go2.urdf
rsl_rl/.gitignore
rsl_rl/LICENSE
rsl_rl/README.md
rsl_rl/licenses/dependencies/numpy_license.txt
rsl_rl/licenses/dependencies/torch_license.txt
rsl_rl/rsl_rl/__init__.py
rsl_rl/rsl_rl/algorithms/__init__.py
rsl_rl/rsl_rl/algorithms/ac_moe_cts.py
rsl_rl/rsl_rl/algorithms/cts.py
rsl_rl/rsl_rl/algorithms/dual_moe_cts.py
rsl_rl/rsl_rl/algorithms/mcp_cts.py
rsl_rl/rsl_rl/algorithms/moe_cts.py
rsl_rl/rsl_rl/algorithms/moe_ng_cts.py
rsl_rl/rsl_rl/algorithms/ppo.py
rsl_rl/rsl_rl/env/__init__.py
rsl_rl/rsl_rl/env/vec_env.py
rsl_rl/rsl_rl/modules/__init__.py
rsl_rl/rsl_rl/modules/actor_critic.py
rsl_rl/rsl_rl/modules/actor_critic_ac_moe_cts.py
rsl_rl/rsl_rl/modules/actor_critic_cts.py
rsl_rl/rsl_rl/modules/actor_critic_dual_moe_cts.py
rsl_rl/rsl_rl/modules/actor_critic_mcp_cts.py
rsl_rl/rsl_rl/modules/actor_critic_moe_cts.py
rsl_rl/rsl_rl/modules/actor_critic_moe_ng_cts.py
rsl_rl/rsl_rl/modules/actor_critic_recurrent.py
rsl_rl/rsl_rl/modules/utils.py
rsl_rl/rsl_rl/runners/__init__.py
rsl_rl/rsl_rl/runners/on_policy_runner.py
rsl_rl/rsl_rl/runners/on_policy_runner_cts.py
rsl_rl/rsl_rl/storage/__init__.py
rsl_rl/rsl_rl/storage/rollout_storage.py
rsl_rl/rsl_rl/storage/rollout_storage_cts.py
rsl_rl/rsl_rl/utils/__init__.py
rsl_rl/rsl_rl/utils/utils.py
rsl_rl/setup.py
setup.py
tools/logs_compress.py
tools/logs_merge.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `resources/robots/go2/assets` | 18 | 28.7 MB | [`resources/robots/go2/assets/_OMITTED.md`](./resources/robots/go2/assets/_OMITTED.md) |
| `resources/robots/go2/dae` | 7 | 24.7 MB | [`resources/robots/go2/dae/_OMITTED.md`](./resources/robots/go2/dae/_OMITTED.md) |
| `resources/robots/go2/imgs` | 4 | 9 KB | [`resources/robots/go2/imgs/_OMITTED.md`](./resources/robots/go2/imgs/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
