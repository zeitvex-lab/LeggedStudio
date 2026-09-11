# AMP_mjlab — 参考资源

> **来源**：`00_open/AMP_mjlab/`　｜　**类型**：参考项目
> **关联机型**：unitree_g1（宇树 G1 人形）
> **定位**：AMP 动作先验训练（mjlab，G1）
> **收录**：142 个文件 / 23.5 MB（其中推理策略/模型文件 0 个）
> **已省略**：39 个文件 / 33.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（11 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（15 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（2 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（57 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（57 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
mjlab_patch/  （1 个文件）
    mjlab/
motion_data_csv/  （17 个文件）
    amp/
rsl_rl/  （44 个文件）
    (直接文件)/
    algorithms/
    config/
    env/
    licenses/
    modules/
    networks/
    runners/
    storage/
    utils/
scripts/  （6 个文件）
    (直接文件)/
src/  （65 个文件）
    (直接文件)/
    assets/
    tasks/
wbc_mjlab.egg-info/  （5 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 80 |
| `.npz` | 18 |
| `.csv` | 17 |
| `.txt` | 15 |
| `(无扩展名)` | 4 |
| `.xml` | 4 |
| `.md` | 2 |
| `.toml` | 1 |
| `.yaml` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
README.md
README_zh.md
mjlab_patch/mjlab/managers/observation_manager.py
motion_data_csv/amp/arc_jog_left_loop_002__A029.csv
motion_data_csv/amp/arc_walk_left_loop_001__A029.csv
motion_data_csv/amp/idle_turn_270_001__A048.csv
motion_data_csv/amp/idle_turn_360_001__A047.csv
motion_data_csv/amp/jog_arc_cw_loop_004__A045.csv
motion_data_csv/amp/jog_backward_loop_002__A022.csv
motion_data_csv/amp/jog_backward_loop_003__A023.csv
motion_data_csv/amp/jog_forward_loop_003__A021.csv
motion_data_csv/amp/jog_forward_loop_003__A022.csv
motion_data_csv/amp/step_rotate_idle_000_002__A026.csv
motion_data_csv/amp/walk_arc_cw_loop_002__A046.csv
motion_data_csv/amp/walk_backward_loop_001__A022.csv
motion_data_csv/amp/walk_backward_loop_001__A024.csv
motion_data_csv/amp/walk_forward_loop_002__A022.csv
motion_data_csv/amp/walk_forward_loop_002__A024.csv
motion_data_csv/amp/walk_sideway_left_loop_002__A021.csv
motion_data_csv/amp/walk_sideway_right_loop_001__A022.csv
rsl_rl/.flake8
rsl_rl/.gitignore
rsl_rl/__init__.py
rsl_rl/algorithms/__init__.py
rsl_rl/algorithms/amp_ppo.py
rsl_rl/algorithms/distillation.py
rsl_rl/algorithms/ppo.py
rsl_rl/config/dummy_config.yaml
rsl_rl/env/__init__.py
rsl_rl/env/vec_env.py
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
rsl_rl/modules/__init__.py
rsl_rl/modules/actor_critic.py
rsl_rl/modules/actor_critic_recurrent.py
rsl_rl/modules/discriminator.py
rsl_rl/modules/normalizer.py
rsl_rl/modules/rnd.py
rsl_rl/modules/student_teacher.py
rsl_rl/modules/student_teacher_recurrent.py
rsl_rl/networks/__init__.py
rsl_rl/networks/memory.py
rsl_rl/pyproject.toml
rsl_rl/runners/__init__.py
rsl_rl/runners/amp_on_policy_runner.py
rsl_rl/runners/on_policy_runner.py
rsl_rl/setup.py
rsl_rl/storage/__init__.py
rsl_rl/storage/replay_buffer.py
rsl_rl/storage/rollout_storage.py
rsl_rl/utils/__init__.py
rsl_rl/utils/motion_loader.py
rsl_rl/utils/neptune_utils.py
rsl_rl/utils/utils.py
rsl_rl/utils/wandb_utils.py
scripts/analyze_base_motion.py
scripts/csv_to_npz.py
scripts/list_envs.py
scripts/play.py
scripts/train.py
scripts/visualize_terrain.py
setup.py
src/__init__.py
src/assets/__init__.py
src/assets/motions/__init__.py
src/assets/motions/g1/amp/Recovery/fallAndGetUp1_subject1.npz
src/assets/motions/g1/amp/WalkandRun/arc_jog_left_loop_002__A029.npz
src/assets/motions/g1/amp/WalkandRun/arc_walk_left_loop_001__A029.npz
src/assets/motions/g1/amp/WalkandRun/idle_turn_270_001__A048.npz
src/assets/motions/g1/amp/WalkandRun/idle_turn_360_001__A047.npz
src/assets/motions/g1/amp/WalkandRun/jog_arc_cw_loop_004__A045.npz
src/assets/motions/g1/amp/WalkandRun/jog_backward_loop_002__A022.npz
src/assets/motions/g1/amp/WalkandRun/jog_backward_loop_003__A023.npz
src/assets/motions/g1/amp/WalkandRun/jog_forward_loop_003__A021.npz
src/assets/motions/g1/amp/WalkandRun/jog_forward_loop_003__A022.npz
src/assets/motions/g1/amp/WalkandRun/step_rotate_idle_000_002__A026.npz
src/assets/motions/g1/amp/WalkandRun/walk_arc_cw_loop_002__A046.npz
src/assets/motions/g1/amp/WalkandRun/walk_backward_loop_001__A022.npz
src/assets/motions/g1/amp/WalkandRun/walk_backward_loop_001__A024.npz
src/assets/motions/g1/amp/WalkandRun/walk_forward_loop_002__A022.npz
src/assets/motions/g1/amp/WalkandRun/walk_forward_loop_002__A024.npz
src/assets/motions/g1/amp/WalkandRun/walk_sideway_left_loop_002__A021.npz
src/assets/motions/g1/amp/WalkandRun/walk_sideway_right_loop_001__A022.npz
src/assets/robots/__init__.py
src/assets/robots/unitree_g1/__init__.py
src/assets/robots/unitree_g1/g1_23dof_constants.py
src/assets/robots/unitree_g1/g1_constants.py
src/assets/robots/unitree_g1/g1_constants_bp.py
src/assets/robots/unitree_g1/unitree_actuators.py
src/assets/robots/unitree_g1/xmls/g1.xml
src/assets/robots/unitree_g1/xmls/g1_23dof.xml
src/assets/robots/unitree_g1/xmls/scene_g1.xml
src/assets/robots/unitree_g1/xmls/scene_g1_23dof.xml
src/mjlab_compat.py
src/tasks/__init__.py
src/tasks/amp_loco/__init__.py
src/tasks/amp_loco/amp_env_cfg.py
src/tasks/amp_loco/ampmotion_loader.py
src/tasks/amp_loco/config/__init__.py
src/tasks/amp_loco/config/g1/__init__.py
src/tasks/amp_loco/config/g1/env_cfgs.py
src/tasks/amp_loco/config/g1/rl_cfg.py
src/tasks/amp_loco/mdp/__init__.py
src/tasks/amp_loco/mdp/command.py
src/tasks/amp_loco/mdp/events.py
src/tasks/amp_loco/mdp/metrics.py
src/tasks/amp_loco/mdp/observations.py
src/tasks/amp_loco/mdp/rewards.py
src/tasks/amp_loco/mdp/terminations.py
src/tasks/amp_loco/mdp/terrain.py
src/tasks/amp_loco/rl/__init__.py
src/tasks/amp_loco/rl/runner.py
src/tasks/amp_loco/rl/wrapper.py
src/tasks/velocity/__init__.py
src/tasks/velocity/config/__init__.py
src/tasks/velocity/config/g1/__init__.py
src/tasks/velocity/config/g1/env_cfgs.py
src/tasks/velocity/config/g1/rl_cfg.py
src/tasks/velocity/mdp/__init__.py
src/tasks/velocity/mdp/curriculums.py
src/tasks/velocity/mdp/observations.py
src/tasks/velocity/mdp/rewards.py
src/tasks/velocity/mdp/terminations.py
src/tasks/velocity/mdp/velocity_command.py
src/tasks/velocity/rl/__init__.py
src/tasks/velocity/rl/runner.py
src/tasks/velocity/velocity_env_cfg.py
wbc_mjlab.egg-info/PKG-INFO
wbc_mjlab.egg-info/SOURCES.txt
wbc_mjlab.egg-info/dependency_links.txt
wbc_mjlab.egg-info/requires.txt
wbc_mjlab.egg-info/top_level.txt
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 137 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `src/assets/robots/unitree_g1/xmls/assets` | 38 | 32.9 MB | [`src/assets/robots/unitree_g1/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_g1/xmls/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
