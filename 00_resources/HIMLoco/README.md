# HIMLoco — 参考资源

> **来源**：`00_open/HIMLoco/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）
> **定位**：InternRobotics HIMLoco：四足高动态运动/越障 RL 训练工程（legged_gym + rsl_rl）
> **收录**：74 个文件 / 11.2 MB（其中推理策略/模型文件 0 个）
> **已省略**：92 个文件 / 62.9 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（16 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（11 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（1 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（1 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（1 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（44 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
assets/  （5 个文件）
    (直接文件)/
legged_gym/  （38 个文件）
    (直接文件)/
    legged_gym/
    licenses/
    resources/
projects/  （2 个文件）
    h_infinity/
    himloco/
rsl_rl/  （25 个文件）
    (直接文件)/
    licenses/
    rsl_rl/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 39 |
| `.txt` | 12 |
| `(无扩展名)` | 6 |
| `.urdf` | 6 |
| `.md` | 5 |
| `.pdf` | 4 |
| `.origin` | 1 |
| `.xml` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
LICENSE
README.md
assets/.DS_Store
assets/HIMLocomotion.pdf
assets/imc.pdf
assets/overview.pdf
assets/teaser_modify_arxiv.pdf
legged_gym/LICENSE
legged_gym/README.md
legged_gym/legged_gym/__init__.py
legged_gym/legged_gym/envs/__init__.py
legged_gym/legged_gym/envs/a1/a1_config.py
legged_gym/legged_gym/envs/aliengo/aliengo_config.py
legged_gym/legged_gym/envs/base/base_config.py
legged_gym/legged_gym/envs/base/base_task.py
legged_gym/legged_gym/envs/base/legged_robot.py
legged_gym/legged_gym/envs/base/legged_robot_config.py
legged_gym/legged_gym/envs/go1/go1_config.py
legged_gym/legged_gym/scripts/play.py
legged_gym/legged_gym/scripts/train.py
legged_gym/legged_gym/tests/test_env.py
legged_gym/legged_gym/utils/__init__.py
legged_gym/legged_gym/utils/helpers.py
legged_gym/legged_gym/utils/logger.py
legged_gym/legged_gym/utils/math.py
legged_gym/legged_gym/utils/task_registry.py
legged_gym/legged_gym/utils/terrain.py
legged_gym/licenses/assets/ANYmal_b_license.txt
legged_gym/licenses/assets/ANYmal_c_license.txt
legged_gym/licenses/assets/a1_license.txt
legged_gym/licenses/assets/cassie_license.txt
legged_gym/licenses/dependencies/matplotlib_license.txt
legged_gym/resources/robots/a1/a1_license.txt
legged_gym/resources/robots/a1/urdf/a1.urdf
legged_gym/resources/robots/a1/urdf/a1.urdf.origin
legged_gym/resources/robots/aliengo/urdf/aliengo.urdf
legged_gym/resources/robots/anymal_b/ANYmal_b_license.txt
legged_gym/resources/robots/anymal_b/urdf/anymal_b.urdf
legged_gym/resources/robots/anymal_c/ANYmal_c_license.txt
legged_gym/resources/robots/anymal_c/urdf/anymal_c.urdf
legged_gym/resources/robots/cassie/cassie_license.txt
legged_gym/resources/robots/cassie/urdf/cassie.urdf
legged_gym/resources/robots/go1/urdf/go1.urdf
legged_gym/resources/robots/go1/xml/go1.xml
legged_gym/setup.py
projects/h_infinity/README.md
projects/himloco/README.md
requirements.txt
rsl_rl/.gitignore
rsl_rl/LICENSE
rsl_rl/README.md
rsl_rl/licenses/dependencies/numpy_license.txt
rsl_rl/licenses/dependencies/torch_license.txt
rsl_rl/rsl_rl/__init__.py
rsl_rl/rsl_rl/algorithms/__init__.py
rsl_rl/rsl_rl/algorithms/him_ppo.py
rsl_rl/rsl_rl/algorithms/ppo.py
rsl_rl/rsl_rl/env/__init__.py
rsl_rl/rsl_rl/env/vec_env.py
rsl_rl/rsl_rl/modules/__init__.py
rsl_rl/rsl_rl/modules/actor_critic.py
rsl_rl/rsl_rl/modules/actor_critic_recurrent.py
rsl_rl/rsl_rl/modules/him_actor_critic.py
rsl_rl/rsl_rl/modules/him_estimator.py
rsl_rl/rsl_rl/runners/__init__.py
rsl_rl/rsl_rl/runners/him_on_policy_runner.py
rsl_rl/rsl_rl/runners/on_policy_runner.py
rsl_rl/rsl_rl/storage/__init__.py
rsl_rl/rsl_rl/storage/him_rollout_storage.py
rsl_rl/rsl_rl/storage/rollout_storage.py
rsl_rl/rsl_rl/utils/__init__.py
rsl_rl/rsl_rl/utils/utils.py
rsl_rl/setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `assets` | 8 | 6.2 MB | [`assets/_OMITTED.md`](./assets/_OMITTED.md) |
| `legged_gym/resources/robots/a1/meshes` | 6 | 8.7 MB | [`legged_gym/resources/robots/a1/meshes/_OMITTED.md`](./legged_gym/resources/robots/a1/meshes/_OMITTED.md) |
| `legged_gym/resources/robots/aliengo/meshes` | 6 | 6.0 MB | [`legged_gym/resources/robots/aliengo/meshes/_OMITTED.md`](./legged_gym/resources/robots/aliengo/meshes/_OMITTED.md) |
| `legged_gym/resources/robots/anymal_b/meshes` | 10 | 21.0 MB | [`legged_gym/resources/robots/anymal_b/meshes/_OMITTED.md`](./legged_gym/resources/robots/anymal_b/meshes/_OMITTED.md) |
| `legged_gym/resources/robots/anymal_c/meshes` | 36 | 7.9 MB | [`legged_gym/resources/robots/anymal_c/meshes/_OMITTED.md`](./legged_gym/resources/robots/anymal_c/meshes/_OMITTED.md) |
| `legged_gym/resources/robots/cassie/meshes` | 21 | 3.3 MB | [`legged_gym/resources/robots/cassie/meshes/_OMITTED.md`](./legged_gym/resources/robots/cassie/meshes/_OMITTED.md) |
| `legged_gym/resources/robots/go1/meshes` | 5 | 9.8 MB | [`legged_gym/resources/robots/go1/meshes/_OMITTED.md`](./legged_gym/resources/robots/go1/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
