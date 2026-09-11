# UFO — 参考资源

> **来源**：`00_open/UFO/`　｜　**类型**：参考项目
> **关联机型**：unitree_g1（宇树 G1 人形）
> **定位**：UFO：G1 人形工程
> **收录**：155 个文件 / 1.2 MB（其中推理策略/模型文件 0 个）
> **已省略**：39 个文件 / 68.1 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（9 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（44 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（6 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（2 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（24 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（15 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（55 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （10 个文件）
configs/  （4 个文件）
    data/
    robots/
docs/  （4 个文件）
    (直接文件)/
humanoidverse/  （123 个文件）
    (直接文件)/
    agents/
    config/
    data/
    envs/
    export/
    tools/
    training/
    utils/
scripts/  （2 个文件）
    (直接文件)/
tests/  （11 个文件）
    (直接文件)/
tools/  （1 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 113 |
| `.yaml` | 24 |
| `.md` | 7 |
| `(无扩展名)` | 3 |
| `.sh` | 3 |
| `.html` | 1 |
| `.toml` | 1 |
| `.csv` | 1 |
| `.json` | 1 |
| `.xml` | 1 |

## 文件索引（项目内相对路径）

```text
.gitattributes
.gitignore
CHANGELOG.md
LICENSE
README.md
README_zh-CN.md
configs/data/example_mix.yaml
configs/data/example_robot_state_auto_build.yaml
configs/data/lafan_cartwheel_mix.yaml
configs/robots/g1_29dof.yaml
docs/TRAIN_INFERENCE.md
docs/import_wizard.md
docs/motion_list_lafan.md
docs/robot_config_training.md
humanoidverse/__init__.py
humanoidverse/agents/__init__.py
humanoidverse/agents/base.py
humanoidverse/agents/base_model.py
humanoidverse/agents/buffers/trajectory.py
humanoidverse/agents/buffers/transition.py
humanoidverse/agents/envs/expert_motion_loader.py
humanoidverse/agents/envs/humanoidverse_mjlab.py
humanoidverse/agents/envs/utils/gym_spaces.py
humanoidverse/agents/envs/utils/history_handler.py
humanoidverse/agents/evaluations/base.py
humanoidverse/agents/evaluations/humanoidverse_mjlab.py
humanoidverse/agents/fb/__init__.py
humanoidverse/agents/fb/agent.py
humanoidverse/agents/fb/model.py
humanoidverse/agents/fb_cpr/__init__.py
humanoidverse/agents/fb_cpr/agent.py
humanoidverse/agents/fb_cpr/configs.py
humanoidverse/agents/fb_cpr/model.py
humanoidverse/agents/fb_cpr_aux/__init__.py
humanoidverse/agents/fb_cpr_aux/agent.py
humanoidverse/agents/fb_cpr_aux/model.py
humanoidverse/agents/gcr_rl/__init__.py
humanoidverse/agents/gcr_rl/agent.py
humanoidverse/agents/gcr_rl/model.py
humanoidverse/agents/gcr_rl_dist/__init__.py
humanoidverse/agents/gcr_rl_dist/agent.py
humanoidverse/agents/gcr_rl_dist/model.py
humanoidverse/agents/gcr_rl_dist_aux/__init__.py
humanoidverse/agents/gcr_rl_dist_aux/agent.py
humanoidverse/agents/gcr_rl_dist_aux/model.py
humanoidverse/agents/load_utils.py
humanoidverse/agents/misc/__init__.py
humanoidverse/agents/misc/loggers.py
humanoidverse/agents/misc/zbuffer.py
humanoidverse/agents/nn_filter_models.py
humanoidverse/agents/nn_filters.py
humanoidverse/agents/nn_models.py
humanoidverse/agents/normalizers.py
humanoidverse/agents/presets/__init__.py
humanoidverse/agents/presets/fb.py
humanoidverse/agents/presets/tldr.py
humanoidverse/agents/pytree_utils.py
humanoidverse/agents/tldr_dist_aux/__init__.py
humanoidverse/agents/tldr_dist_aux/agent.py
humanoidverse/agents/utils.py
humanoidverse/config/base.yaml
humanoidverse/config/base/fabric.yaml
humanoidverse/config/base/hydra.yaml
humanoidverse/config/base/structure.yaml
humanoidverse/config/base_eval.yaml
humanoidverse/config/callbacks/autoresume.yaml
humanoidverse/config/callbacks/im_eval.yaml
humanoidverse/config/callbacks/model_save.yaml
humanoidverse/config/domain_rand/domain_rand.yaml
humanoidverse/config/env/base_task.yaml
humanoidverse/config/env/legged_base.yaml
humanoidverse/config/env/legged_motions.yaml
humanoidverse/config/exp/bfm_zero/bfm_zero.yaml
humanoidverse/config/obs/bfm_zero_obs.yaml
humanoidverse/config/rewards/reward_bfm_zero.yaml
humanoidverse/config/robot/g1/g1_29dof_hard_waist.yaml
humanoidverse/config/robot/robot_base.yaml
humanoidverse/config/simulator/mujoco.yaml
humanoidverse/config/terrain/terrain_base.yaml
humanoidverse/config/terrain/terrain_locomotion_plane.yaml
humanoidverse/data/examples/g1_robot_state_sample.csv
humanoidverse/data/robots/g1/goal_frames_lafan29dof.json
humanoidverse/data/robots/g1_mjlab/g1_29dof.xml
humanoidverse/distributed.py
humanoidverse/envs/__init__.py
humanoidverse/envs/env_utils/__init__.py
humanoidverse/envs/env_utils/history_handler.py
humanoidverse/envs/g1_env_helper/__init__.py
humanoidverse/envs/g1_env_helper/rewards.py
humanoidverse/envs/motion_observations.py
humanoidverse/export/__init__.py
humanoidverse/export/backward_encoder.py
humanoidverse/goal_inference.py
humanoidverse/mjlab_inference_utils.py
humanoidverse/mjlab_reward_relabel.py
humanoidverse/reward_inference.py
humanoidverse/tools/__init__.py
humanoidverse/tools/data_build.py
humanoidverse/tools/data_inspect.py
humanoidverse/tools/eval_goal_joint_mae.py
humanoidverse/tools/eval_joint_mae_dataset.py
humanoidverse/tools/robot_inspect.py
humanoidverse/tracking_inference.py
humanoidverse/train.py
humanoidverse/train_mjlab.py
humanoidverse/training/__init__.py
humanoidverse/training/workspace.py
humanoidverse/utils/__init__.py
humanoidverse/utils/helpers.py
humanoidverse/utils/logging.py
humanoidverse/utils/math.py
humanoidverse/utils/motion_data/__init__.py
humanoidverse/utils/motion_data/adapters.py
humanoidverse/utils/motion_data/clip.py
humanoidverse/utils/motion_data/manifest.py
humanoidverse/utils/motion_data/paths.py
humanoidverse/utils/motion_data/robot_state.py
humanoidverse/utils/motion_data/robot_state_convert.py
humanoidverse/utils/motion_data/robot_state_readers.py
humanoidverse/utils/motion_data/schema.py
humanoidverse/utils/motion_lib/__init__.py
humanoidverse/utils/motion_lib/motion_lib_base.py
humanoidverse/utils/motion_lib/motion_lib_robot.py
humanoidverse/utils/motion_lib/motion_utils/__init__.py
humanoidverse/utils/motion_lib/motion_utils/flags.py
humanoidverse/utils/motion_lib/motion_utils/rotation_conversions.py
humanoidverse/utils/motion_lib/skeleton.py
humanoidverse/utils/motion_lib/torch_humanoid_batch.py
humanoidverse/utils/reference_observations.py
humanoidverse/utils/robot_spec/__init__.py
humanoidverse/utils/robot_spec/mujoco_parser.py
humanoidverse/utils/robot_spec/robot_spec.py
humanoidverse/utils/robot_spec/training_spec.py
humanoidverse/utils/robot_spec/urdf_training_infer.py
humanoidverse/utils/robot_spec/validate.py
humanoidverse/utils/robot_spec/xml_training_infer.py
humanoidverse/utils/torch_utils.py
index.html
pyproject.toml
run_train.sh
scripts/download_data.sh
scripts/smoke_release.sh
show_help.py
tests/test_agent_aliases.py
tests/test_humanoidverse_mjlab_metrics.py
tests/test_import_tools.py
tests/test_motion_data_adapter.py
tests/test_reference_observations.py
tests/test_robot_config_goal_reward_inference.py
tests/test_robot_config_onnx_export.py
tests/test_robot_config_training.py
tests/test_robot_xml_hydra_generation.py
tests/test_update_z_cli.py
tests/test_urdf_assisted_robot_inspect.py
tools/export_backward_encoder_onnx.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 273 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `assets` | 3 | 47.3 MB | [`assets/_OMITTED.md`](./assets/_OMITTED.md) |
| `humanoidverse/data/robots/g1_mjlab/meshes` | 35 | 20.5 MB | [`humanoidverse/data/robots/g1_mjlab/meshes/_OMITTED.md`](./humanoidverse/data/robots/g1_mjlab/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
