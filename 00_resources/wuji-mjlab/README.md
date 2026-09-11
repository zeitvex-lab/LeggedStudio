# wuji-mjlab — 参考资源

> **来源**：`00_open/wuji-mjlab/`　｜　**类型**：参考项目
> **关联机型**：wuji_hand（无极灵巧手）
> **定位**：无极灵巧手 mjlab 训练工程
> **收录**：187 个文件 / 1.1 MB（其中推理策略/模型文件 0 个）
> **已省略**：61 个文件 / 34.3 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（12 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（69 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（34 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（1 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（16 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（55 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （8 个文件）
.github/  （12 个文件）
    (直接文件)/
    scripts/
    workflows/
deploy/  （34 个文件）
    (直接文件)/
    reorient/
docs/  （16 个文件）
    external/
    sim2real/
scripts/  （4 个文件）
    (直接文件)/
    play/
    train/
src/  （113 个文件）
    wuji_mjlab/
    wuji_rl_libs/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 136 |
| `.mdx` | 12 |
| `.md` | 10 |
| `.sh` | 6 |
| `.yaml` | 5 |
| `.yml` | 5 |
| `(无扩展名)` | 4 |
| `.toml` | 3 |
| `.json` | 3 |
| `.xml` | 2 |
| `.txt` | 1 |

## 文件索引（项目内相对路径）

```text
.github/docs-sync-public-packages.txt
.github/scripts/docs-followup/docs-followup-comment.sh
.github/scripts/docs-followup/docs-followup-prompt.sh
.github/scripts/docs-followup/feishu-dm.sh
.github/scripts/docs-followup/feishu-sign.sh
.github/scripts/docs-followup/force-followup-discover.sh
.github/scripts/docs-followup/public-packages-discover.sh
.github/workflows/ci.yml
.github/workflows/docs-followup-callback.yml
.github/workflows/docs-followup.yml
.github/workflows/docs-notify.yml
.github/workflows/docs-prerelease-sync.yml
.gitignore
.pre-commit-config.yaml
CHANGELOG.md
LICENSE
NOTICE
README.md
deploy/__init__.py
deploy/reorient/README.md
deploy/reorient/README_zh.md
deploy/reorient/__init__.py
deploy/reorient/config/camera.yaml
deploy/reorient/config/control.yaml
deploy/reorient/config/cube_calibration.yaml
deploy/reorient/config/cube_tags.json
deploy/reorient/config/observer.yaml
deploy/reorient/lib/__init__.py
deploy/reorient/lib/_paths.py
deploy/reorient/lib/camera_config.py
deploy/reorient/lib/config_loader.py
deploy/reorient/lib/cube_geom.py
deploy/reorient/lib/external_goal_command.py
deploy/reorient/lib/frame_transform.py
deploy/reorient/lib/hand_driver.py
deploy/reorient/lib/interpolator.py
deploy/reorient/lib/joint_data.py
deploy/reorient/lib/onnx_policy.py
deploy/reorient/lib/ood_diagnostics.py
deploy/reorient/lib/real_hand_env.py
deploy/reorient/lib/real_hand_env_cfg.py
deploy/reorient/lib/real_hand_obs.py
deploy/reorient/lib/viewer_sync.py
deploy/reorient/lib/zmq_bridge.py
deploy/reorient/scripts/cube_world_observer.py
deploy/reorient/scripts/hand_utils.py
deploy/reorient/scripts/play_real.py
deploy/reorient/scripts/toreal_viewer.py
deploy/reorient/tools/__init__.py
deploy/reorient/tools/calib_check.py
deploy/reorient/tools/camera_calibrate.py
deploy/reorient/tools/view_release_cube.py
docs/external/en/architecture.mdx
docs/external/en/hardware.mdx
docs/external/en/installation.mdx
docs/external/en/introduction.mdx
docs/external/en/meta.json
docs/external/en/sim2real.mdx
docs/external/en/training.mdx
docs/external/zh/architecture.mdx
docs/external/zh/hardware.mdx
docs/external/zh/installation.mdx
docs/external/zh/introduction.mdx
docs/external/zh/meta.json
docs/external/zh/sim2real.mdx
docs/external/zh/training.mdx
docs/sim2real/setup.md
docs/sim2real/setup_zh.md
pixi.toml
pyproject.toml
scripts/list_envs.py
scripts/play/play_rsl_rl.py
scripts/record_video.py
scripts/train/train_rsl_rl.py
src/wuji_mjlab/__init__.py
src/wuji_mjlab/assets/README.md
src/wuji_mjlab/assets/__init__.py
src/wuji_mjlab/assets/object_lib/__init__.py
src/wuji_mjlab/assets/object_lib/discovery.py
src/wuji_mjlab/assets/object_lib/object_lib.py
src/wuji_mjlab/assets/objects/__init__.py
src/wuji_mjlab/assets/objects/inhand_object/__init__.py
src/wuji_mjlab/assets/objects/inhand_object/inhand_object_cfg.py
src/wuji_mjlab/assets/objects/inhand_object/object_cfg.py
src/wuji_mjlab/assets/objects/inhand_object/xmls/cube.xml
src/wuji_mjlab/assets/robots/__init__.py
src/wuji_mjlab/assets/robots/wuji_hand/__init__.py
src/wuji_mjlab/assets/robots/wuji_hand/mjcf/right_mjlab.xml
src/wuji_mjlab/assets/robots/wuji_hand/wuji_hand_cfg.py
src/wuji_mjlab/rl/__init__.py
src/wuji_mjlab/rl/runner.py
src/wuji_mjlab/tasks/__init__.py
src/wuji_mjlab/tasks/reorient/README.md
src/wuji_mjlab/tasks/reorient/README_zh.md
src/wuji_mjlab/tasks/reorient/__init__.py
src/wuji_mjlab/tasks/reorient/config/__init__.py
src/wuji_mjlab/tasks/reorient/config/wuji_hand/__init__.py
src/wuji_mjlab/tasks/reorient/config/wuji_hand/env_cfgs.py
src/wuji_mjlab/tasks/reorient/config/wuji_hand/rsl_rl/__init__.py
src/wuji_mjlab/tasks/reorient/config/wuji_hand/rsl_rl/ppo.py
src/wuji_mjlab/tasks/reorient/mdp/__init__.py
src/wuji_mjlab/tasks/reorient/mdp/actions.py
src/wuji_mjlab/tasks/reorient/mdp/cage.py
src/wuji_mjlab/tasks/reorient/mdp/command_visualization.py
src/wuji_mjlab/tasks/reorient/mdp/commands.py
src/wuji_mjlab/tasks/reorient/mdp/curriculums.py
src/wuji_mjlab/tasks/reorient/mdp/event_impl/__init__.py
src/wuji_mjlab/tasks/reorient/mdp/event_impl/curriculum.py
src/wuji_mjlab/tasks/reorient/mdp/event_impl/episode.py
src/wuji_mjlab/tasks/reorient/mdp/event_impl/joint_reset.py
src/wuji_mjlab/tasks/reorient/mdp/event_impl/randomization.py
src/wuji_mjlab/tasks/reorient/mdp/event_impl/state.py
src/wuji_mjlab/tasks/reorient/mdp/event_utils.py
src/wuji_mjlab/tasks/reorient/mdp/events.py
src/wuji_mjlab/tasks/reorient/mdp/metrics.py
src/wuji_mjlab/tasks/reorient/mdp/observations.py
src/wuji_mjlab/tasks/reorient/mdp/rewards.py
src/wuji_mjlab/tasks/reorient/mdp/terminations.py
src/wuji_mjlab/tasks/reorient/mdp/types.py
src/wuji_mjlab/tasks/reorient/reorient_constants.py
src/wuji_mjlab/tasks/reorient/reorient_env_cfg.py
src/wuji_mjlab/tasks/reorient/reorient_terms.py
src/wuji_mjlab/tasks/reorient/scripts/eval_success_rate.py
src/wuji_mjlab/tasks/reorient/scripts/export_onnx.py
src/wuji_mjlab/tasks/reorient/scripts/view_task.py
src/wuji_mjlab/tasks/reorient/scripts/visualize_frames_viewer.py
src/wuji_mjlab/tasks/reorient/tests/conftest.py
src/wuji_mjlab/tasks/reorient/tests/fakes.py
src/wuji_mjlab/tasks/reorient/tests/test_cage_counter_contract.py
src/wuji_mjlab/tasks/reorient/tests/test_event_episode_contract.py
src/wuji_mjlab/tasks/reorient/tests/test_event_joint_reset.py
src/wuji_mjlab/tasks/reorient/tests/test_event_randomization_contract.py
src/wuji_mjlab/tasks/reorient/tests/test_event_state_contract.py
src/wuji_mjlab/tasks/reorient/tests/test_export_onnx.py
src/wuji_mjlab/tasks/reorient/tests/test_goal_visualization.py
src/wuji_mjlab/tasks/reorient/tests/test_pipeline_invariants.py
src/wuji_mjlab/tasks/reorient/tests/test_public_naming.py
src/wuji_mjlab/tasks/reorient/tests/test_reorient_rl_cfg.py
src/wuji_mjlab/tasks/reorient/tooling/__init__.py
src/wuji_mjlab/tasks/reorient/tooling/eval_core.py
src/wuji_mjlab/tasks/reorient/tooling/eval_display.py
src/wuji_mjlab/tasks/reorient/tooling/onnx_export_core.py
src/wuji_mjlab/tasks/reorient/tooling/scene_builder.py
src/wuji_mjlab/utils/__init__.py
src/wuji_mjlab/utils/cli_override_utils.py
src/wuji_mjlab/utils/curriculum.py
src/wuji_mjlab/utils/math.py
src/wuji_mjlab/utils/override_utils.py
src/wuji_mjlab/utils/play_runner.py
src/wuji_mjlab/utils/reward_decorators.py
src/wuji_mjlab/utils/task_cfg_utils.py
src/wuji_rl_libs/rsl_rl/LICENSE
src/wuji_rl_libs/rsl_rl/pyproject.toml
src/wuji_rl_libs/rsl_rl/rsl_rl/ENV_INTERFACE.md
src/wuji_rl_libs/rsl_rl/rsl_rl/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/algorithms/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/algorithms/amp_ppo.py
src/wuji_rl_libs/rsl_rl/rsl_rl/algorithms/distillation.py
src/wuji_rl_libs/rsl_rl/rsl_rl/algorithms/ppo.py
src/wuji_rl_libs/rsl_rl/rsl_rl/env/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/env/vec_env.py
src/wuji_rl_libs/rsl_rl/rsl_rl/extensions/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/extensions/rnd.py
src/wuji_rl_libs/rsl_rl/rsl_rl/extensions/symmetry.py
src/wuji_rl_libs/rsl_rl/rsl_rl/models/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/models/cnn_model.py
src/wuji_rl_libs/rsl_rl/rsl_rl/models/mlp_model.py
src/wuji_rl_libs/rsl_rl/rsl_rl/models/rnn_model.py
src/wuji_rl_libs/rsl_rl/rsl_rl/modules/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/modules/cnn.py
src/wuji_rl_libs/rsl_rl/rsl_rl/modules/discriminator.py
src/wuji_rl_libs/rsl_rl/rsl_rl/modules/distribution.py
src/wuji_rl_libs/rsl_rl/rsl_rl/modules/mlp.py
src/wuji_rl_libs/rsl_rl/rsl_rl/modules/normalization.py
src/wuji_rl_libs/rsl_rl/rsl_rl/modules/rnn.py
src/wuji_rl_libs/rsl_rl/rsl_rl/runners/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/runners/distillation_runner.py
src/wuji_rl_libs/rsl_rl/rsl_rl/runners/on_policy_runner.py
src/wuji_rl_libs/rsl_rl/rsl_rl/storage/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/storage/replay_buffer.py
src/wuji_rl_libs/rsl_rl/rsl_rl/storage/rollout_storage.py
src/wuji_rl_libs/rsl_rl/rsl_rl/utils/__init__.py
src/wuji_rl_libs/rsl_rl/rsl_rl/utils/logger.py
src/wuji_rl_libs/rsl_rl/rsl_rl/utils/neptune_utils.py
src/wuji_rl_libs/rsl_rl/rsl_rl/utils/normalizer.py
src/wuji_rl_libs/rsl_rl/rsl_rl/utils/utils.py
src/wuji_rl_libs/rsl_rl/rsl_rl/utils/wandb_utils.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 152 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `docs/assets` | 3 | 10.3 MB | [`docs/assets/_OMITTED.md`](./docs/assets/_OMITTED.md) |
| `docs/external/en/images` | 4 | 7.5 MB | [`docs/external/en/images/_OMITTED.md`](./docs/external/en/images/_OMITTED.md) |
| `docs/external/zh/images` | 4 | 7.5 MB | [`docs/external/zh/images/_OMITTED.md`](./docs/external/zh/images/_OMITTED.md) |
| `docs/sim2real/images` | 1 | 50 KB | [`docs/sim2real/images/_OMITTED.md`](./docs/sim2real/images/_OMITTED.md) |
| `src/wuji_mjlab/assets/objects/inhand_object/meshes` | 1 | 1 KB | [`src/wuji_mjlab/assets/objects/inhand_object/meshes/_OMITTED.md`](./src/wuji_mjlab/assets/objects/inhand_object/meshes/_OMITTED.md) |
| `src/wuji_mjlab/assets/objects/inhand_object/textures` | 13 | 75 KB | [`src/wuji_mjlab/assets/objects/inhand_object/textures/_OMITTED.md`](./src/wuji_mjlab/assets/objects/inhand_object/textures/_OMITTED.md) |
| `src/wuji_mjlab/assets/robots/wuji_hand/meshes/right` | 34 | 8.7 MB | [`src/wuji_mjlab/assets/robots/wuji_hand/meshes/right/_OMITTED.md`](./src/wuji_mjlab/assets/robots/wuji_hand/meshes/right/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
