# Gymnasium — 参考资源

> **来源**：`00_open/Gymnasium/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）、unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_b2（宇树 B2 四足）、unitree_b2w（宇树 B2W 轮足）、unitree_g1（宇树 G1 人形）、deeprobotics_lite3（云深处 Lite3 四足）、deeprobotics_m20（云深处 M20 轮足）、limx_tron1_pf（逐际动力 TRON1-PF）、limx_tron1_sf（逐际动力 TRON1-SF）、limx_tron1_wf（逐际动力 TRON1-WF）、microduck（MicroDuck 双足）、wuji_hand（无极灵巧手）、zex-w（ZEX-W 轮足）
> **定位**：Farama RL 环境标准 API（Env/Space/Wrapper/Vector）——训练适配器协议与环境接口设计参考
> **收录**：458 个文件 / 2.8 MB（其中推理策略/模型文件 0 个）
> **已省略**：255 个文件 / 121.4 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（1 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（90 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **动作与运动数据**（2 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（100 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（264 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （9 个文件）
.github/  （15 个文件）
    (直接文件)/
    ISSUE_TEMPLATE/
    workflows/
bin/  （3 个文件）
    (直接文件)/
docs/  （171 个文件）
    (直接文件)/
    _scripts/
    api/
    environments/
    gym_release_notes/
    gymnasium_release_notes/
    introduction/
    tutorials/
gymnasium/  （136 个文件）
    (直接文件)/
    envs/
    experimental/
    spaces/
    utils/
    vector/
    wrappers/
tests/  （124 个文件）
    (直接文件)/
    envs/
    functional/
    spaces/
    utils/
    vector/
    wrappers/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 262 |
| `.md` | 144 |
| `.xml` | 15 |
| `.yml` | 14 |
| `(无扩展名)` | 11 |
| `.rst` | 4 |
| `.dockerfile` | 2 |
| `.yaml` | 1 |
| `.cff` | 1 |
| `.toml` | 1 |
| `.bat` | 1 |
| `.txt` | 1 |
| `.typed` | 1 |

## 文件索引（项目内相对路径）

```text
.github/FUNDING.yml
.github/ISSUE_TEMPLATE/bug.yml
.github/ISSUE_TEMPLATE/proposal.yml
.github/ISSUE_TEMPLATE/question.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/dependabot.yml
.github/stale.yml
.github/workflows/docs-build-dev.yml
.github/workflows/docs-build-release.yml
.github/workflows/docs-manual-build.yml
.github/workflows/linkcheck.yml
.github/workflows/pypi-publish.yml
.github/workflows/run-pre-commit.yml
.github/workflows/run-pytest.yml
.github/workflows/run-tutorial.yml
.gitignore
.pre-commit-config.yaml
CITATION.cff
CODE_OF_CONDUCT.rst
CONTRIBUTING.md
LICENSE
README.md
bin/all-py.Dockerfile
bin/docker_entrypoint
bin/necessary-py.Dockerfile
docs/.gitignore
docs/404.md
docs/Makefile
docs/README.md
docs/_scripts/gen_envs_display.py
docs/_scripts/gen_gifs.py
docs/_scripts/gen_mds.py
docs/_scripts/gen_wrapper_table.py
docs/_scripts/linkcheck.py
docs/_scripts/move_404.py
docs/_scripts/utils.py
docs/api/env.md
docs/api/functional.md
docs/api/registry.md
docs/api/spaces.md
docs/api/spaces/composite.md
docs/api/spaces/fundamental.md
docs/api/spaces/utils.md
docs/api/utils.md
docs/api/vector.md
docs/api/vector/async_vector_env.md
docs/api/vector/sync_vector_env.md
docs/api/vector/utils.md
docs/api/vector/wrappers.md
docs/api/wrappers.md
docs/api/wrappers/action_wrappers.md
docs/api/wrappers/misc_wrappers.md
docs/api/wrappers/observation_wrappers.md
docs/api/wrappers/reward_wrappers.md
docs/api/wrappers/table.md
docs/conf.py
docs/environments/atari.md
docs/environments/atari/adventure.md
docs/environments/atari/air_raid.md
docs/environments/atari/alien.md
docs/environments/atari/amidar.md
docs/environments/atari/assault.md
docs/environments/atari/asterix.md
docs/environments/atari/asteroids.md
docs/environments/atari/atlantis.md
docs/environments/atari/atlantis2.md
docs/environments/atari/backgammon.md
docs/environments/atari/bank_heist.md
docs/environments/atari/basic_math.md
docs/environments/atari/battle_zone.md
docs/environments/atari/beam_rider.md
docs/environments/atari/berzerk.md
docs/environments/atari/blackjack.md
docs/environments/atari/bowling.md
docs/environments/atari/boxing.md
docs/environments/atari/breakout.md
docs/environments/atari/carnival.md
docs/environments/atari/casino.md
docs/environments/atari/centipede.md
docs/environments/atari/chopper_command.md
docs/environments/atari/crazy_climber.md
docs/environments/atari/crossbow.md
docs/environments/atari/darkchambers.md
docs/environments/atari/defender.md
docs/environments/atari/demon_attack.md
docs/environments/atari/donkey_kong.md
docs/environments/atari/double_dunk.md
docs/environments/atari/earthworld.md
docs/environments/atari/elevator_action.md
docs/environments/atari/enduro.md
docs/environments/atari/entombed.md
docs/environments/atari/et.md
docs/environments/atari/fishing_derby.md
docs/environments/atari/flag_capture.md
docs/environments/atari/freeway.md
docs/environments/atari/frogger.md
docs/environments/atari/frostbite.md
docs/environments/atari/galaxian.md
docs/environments/atari/gopher.md
docs/environments/atari/gravitar.md
docs/environments/atari/hangman.md
docs/environments/atari/haunted_house.md
docs/environments/atari/hero.md
docs/environments/atari/human_cannonball.md
docs/environments/atari/ice_hockey.md
docs/environments/atari/jamesbond.md
docs/environments/atari/journey_escape.md
docs/environments/atari/kaboom.md
docs/environments/atari/kangaroo.md
docs/environments/atari/keystone_kapers.md
docs/environments/atari/king_kong.md
docs/environments/atari/klax.md
docs/environments/atari/koolaid.md
docs/environments/atari/krull.md
docs/environments/atari/kung_fu_master.md
docs/environments/atari/laser_gates.md
docs/environments/atari/lost_luggage.md
docs/environments/atari/mario_bros.md
docs/environments/atari/miniature_golf.md
docs/environments/atari/montezuma_revenge.md
docs/environments/atari/mr_do.md
docs/environments/atari/ms_pacman.md
docs/environments/atari/name_this_game.md
docs/environments/atari/othello.md
docs/environments/atari/pacman.md
docs/environments/atari/phoenix.md
docs/environments/atari/pitfall.md
docs/environments/atari/pitfall2.md
docs/environments/atari/pong.md
docs/environments/atari/pooyan.md
docs/environments/atari/private_eye.md
docs/environments/atari/qbert.md
docs/environments/atari/riverraid.md
docs/environments/atari/road_runner.md
docs/environments/atari/robotank.md
docs/environments/atari/seaquest.md
docs/environments/atari/sir_lancelot.md
docs/environments/atari/skiing.md
docs/environments/atari/solaris.md
docs/environments/atari/space_invaders.md
docs/environments/atari/space_war.md
docs/environments/atari/star_gunner.md
docs/environments/atari/superman.md
docs/environments/atari/surround.md
docs/environments/atari/tennis.md
docs/environments/atari/tetris.md
docs/environments/atari/tic_tac_toe_3d.md
docs/environments/atari/time_pilot.md
docs/environments/atari/trondead.md
docs/environments/atari/turmoil.md
docs/environments/atari/tutankham.md
docs/environments/atari/up_n_down.md
docs/environments/atari/venture.md
docs/environments/atari/video_checkers.md
docs/environments/atari/video_chess.md
docs/environments/atari/video_cube.md
docs/environments/atari/video_pinball.md
docs/environments/atari/wizard_of_wor.md
docs/environments/atari/word_zapper.md
docs/environments/atari/yars_revenge.md
docs/environments/atari/zaxxon.md
docs/environments/box2d.md
docs/environments/box2d/.gitkeep
docs/environments/classic_control.md
docs/environments/classic_control/.gitkeep
docs/environments/mujoco.md
docs/environments/mujoco/.gitkeep
docs/environments/mujoco/action_space_figures/credits
docs/environments/third_party_environments.md
docs/environments/toy_text.md
docs/environments/toy_text/.gitkeep
docs/gym_release_notes/index.md
docs/gymnasium_release_notes/index.md
docs/index.md
docs/introduction/.gitkeep
docs/introduction/basic_usage.md
docs/introduction/create_custom_env.md
docs/introduction/migration_guide.md
docs/introduction/record_agent.md
docs/introduction/speed_up_env.md
docs/introduction/train_agent.md
docs/make.bat
docs/requirements.txt
docs/tutorials/README.rst
docs/tutorials/gymnasium_basics/README.rst
docs/tutorials/gymnasium_basics/environment_creation.py
docs/tutorials/gymnasium_basics/handling_time_limits.py
docs/tutorials/gymnasium_basics/implementing_custom_wrappers.py
docs/tutorials/gymnasium_basics/load_quadruped_model.py
docs/tutorials/third-party-tutorials.md
docs/tutorials/training_agents/README.rst
docs/tutorials/training_agents/action_masking_taxi.py
docs/tutorials/training_agents/blackjack_q_learning.py
docs/tutorials/training_agents/frozenlake_q_learning.py
docs/tutorials/training_agents/mujoco_reinforce.py
docs/tutorials/training_agents/vector_a2c.py
gymnasium/__init__.py
gymnasium/core.py
gymnasium/envs/__init__.py
gymnasium/envs/box2d/__init__.py
gymnasium/envs/box2d/bipedal_walker.py
gymnasium/envs/box2d/car_dynamics.py
gymnasium/envs/box2d/car_racing.py
gymnasium/envs/box2d/lunar_lander.py
gymnasium/envs/classic_control/__init__.py
gymnasium/envs/classic_control/acrobot.py
gymnasium/envs/classic_control/cartpole.py
gymnasium/envs/classic_control/continuous_mountain_car.py
gymnasium/envs/classic_control/mountain_car.py
gymnasium/envs/classic_control/pendulum.py
gymnasium/envs/classic_control/utils.py
gymnasium/envs/functional_jax_env.py
gymnasium/envs/mujoco/__init__.py
gymnasium/envs/mujoco/ant_v4.py
gymnasium/envs/mujoco/ant_v5.py
gymnasium/envs/mujoco/assets/ant.xml
gymnasium/envs/mujoco/assets/half_cheetah.xml
gymnasium/envs/mujoco/assets/hopper.xml
gymnasium/envs/mujoco/assets/humanoid.xml
gymnasium/envs/mujoco/assets/humanoidstandup.xml
gymnasium/envs/mujoco/assets/inverted_double_pendulum.xml
gymnasium/envs/mujoco/assets/inverted_pendulum.xml
gymnasium/envs/mujoco/assets/point.xml
gymnasium/envs/mujoco/assets/pusher.xml
gymnasium/envs/mujoco/assets/pusher_v5.xml
gymnasium/envs/mujoco/assets/reacher.xml
gymnasium/envs/mujoco/assets/swimmer.xml
gymnasium/envs/mujoco/assets/walker2d.xml
gymnasium/envs/mujoco/assets/walker2d_v5.xml
gymnasium/envs/mujoco/half_cheetah_v4.py
gymnasium/envs/mujoco/half_cheetah_v5.py
gymnasium/envs/mujoco/hopper_v4.py
gymnasium/envs/mujoco/hopper_v5.py
gymnasium/envs/mujoco/humanoid_v4.py
gymnasium/envs/mujoco/humanoid_v5.py
gymnasium/envs/mujoco/humanoidstandup_v4.py
gymnasium/envs/mujoco/humanoidstandup_v5.py
gymnasium/envs/mujoco/inverted_double_pendulum_v4.py
gymnasium/envs/mujoco/inverted_double_pendulum_v5.py
gymnasium/envs/mujoco/inverted_pendulum_v4.py
gymnasium/envs/mujoco/inverted_pendulum_v5.py
gymnasium/envs/mujoco/mujoco_env.py
gymnasium/envs/mujoco/mujoco_py_env.py
gymnasium/envs/mujoco/mujoco_rendering.py
gymnasium/envs/mujoco/pusher_v4.py
gymnasium/envs/mujoco/pusher_v5.py
gymnasium/envs/mujoco/reacher_v4.py
gymnasium/envs/mujoco/reacher_v5.py
gymnasium/envs/mujoco/swimmer_v4.py
gymnasium/envs/mujoco/swimmer_v5.py
gymnasium/envs/mujoco/utils.py
gymnasium/envs/mujoco/walker2d_v4.py
gymnasium/envs/mujoco/walker2d_v5.py
gymnasium/envs/phys2d/__init__.py
gymnasium/envs/phys2d/cartpole.py
gymnasium/envs/phys2d/pendulum.py
gymnasium/envs/registration.py
gymnasium/envs/tabular/__init__.py
gymnasium/envs/tabular/blackjack.py
gymnasium/envs/tabular/cliffwalking.py
gymnasium/envs/toy_text/__init__.py
gymnasium/envs/toy_text/blackjack.py
gymnasium/envs/toy_text/cliffwalking.py
gymnasium/envs/toy_text/frozen_lake.py
gymnasium/envs/toy_text/taxi.py
gymnasium/envs/toy_text/utils.py
gymnasium/error.py
gymnasium/experimental/__init__.py
gymnasium/experimental/functional.py
gymnasium/logger.py
gymnasium/py.typed
gymnasium/spaces/__init__.py
gymnasium/spaces/box.py
gymnasium/spaces/dict.py
gymnasium/spaces/discrete.py
gymnasium/spaces/graph.py
gymnasium/spaces/multi_binary.py
gymnasium/spaces/multi_discrete.py
gymnasium/spaces/oneof.py
gymnasium/spaces/sequence.py
gymnasium/spaces/space.py
gymnasium/spaces/text.py
gymnasium/spaces/tuple.py
gymnasium/spaces/utils.py
gymnasium/utils/__init__.py
gymnasium/utils/colorize.py
gymnasium/utils/env_checker.py
gymnasium/utils/env_match.py
gymnasium/utils/ezpickle.py
gymnasium/utils/passive_env_checker.py
gymnasium/utils/performance.py
gymnasium/utils/play.py
gymnasium/utils/record_constructor.py
gymnasium/utils/save_video.py
gymnasium/utils/seeding.py
gymnasium/utils/step_api_compatibility.py
gymnasium/vector/__init__.py
gymnasium/vector/async_vector_env.py
gymnasium/vector/sync_vector_env.py
gymnasium/vector/utils/__init__.py
gymnasium/vector/utils/misc.py
gymnasium/vector/utils/shared_memory.py
gymnasium/vector/utils/space_utils.py
gymnasium/vector/vector_env.py
gymnasium/wrappers/__init__.py
gymnasium/wrappers/array_conversion.py
gymnasium/wrappers/atari_preprocessing.py
gymnasium/wrappers/common.py
gymnasium/wrappers/jax_to_numpy.py
gymnasium/wrappers/jax_to_torch.py
gymnasium/wrappers/numpy_to_torch.py
gymnasium/wrappers/rendering.py
gymnasium/wrappers/stateful_action.py
gymnasium/wrappers/stateful_observation.py
gymnasium/wrappers/stateful_reward.py
gymnasium/wrappers/transform_action.py
gymnasium/wrappers/transform_observation.py
gymnasium/wrappers/transform_reward.py
gymnasium/wrappers/utils.py
gymnasium/wrappers/vector/__init__.py
gymnasium/wrappers/vector/array_conversion.py
gymnasium/wrappers/vector/common.py
gymnasium/wrappers/vector/dict_info_to_list.py
gymnasium/wrappers/vector/jax_to_numpy.py
gymnasium/wrappers/vector/jax_to_torch.py
gymnasium/wrappers/vector/numpy_to_torch.py
gymnasium/wrappers/vector/rendering.py
gymnasium/wrappers/vector/stateful_observation.py
gymnasium/wrappers/vector/stateful_reward.py
gymnasium/wrappers/vector/vectorize_action.py
gymnasium/wrappers/vector/vectorize_observation.py
gymnasium/wrappers/vector/vectorize_reward.py
pyproject.toml
setup.py
tests/__init__.py
tests/envs/__init__.py
tests/envs/functional/__init__.py
tests/envs/functional/test_core.py
tests/envs/functional/test_jax.py
tests/envs/mujoco/__init__.py
tests/envs/mujoco/assets/walker2d_v5_uneven_feet.xml
tests/envs/mujoco/test_mujoco_custom_env.py
tests/envs/mujoco/test_mujoco_rendering.py
tests/envs/mujoco/test_mujoco_v3.py
tests/envs/mujoco/test_mujoco_v5.py
tests/envs/registration/__init__.py
tests/envs/registration/test_env_spec.py
tests/envs/registration/test_make.py
tests/envs/registration/test_make_vec.py
tests/envs/registration/test_pprint_registry.py
tests/envs/registration/test_register.py
tests/envs/registration/test_spec.py
tests/envs/registration/utils_envs.py
tests/envs/registration/utils_unregistered_env.py
tests/envs/test_action_dim_check.py
tests/envs/test_env_implementation.py
tests/envs/test_envs.py
tests/envs/test_rendering.py
tests/envs/toy_text/__init__.py
tests/envs/toy_text/test_taxi.py
tests/envs/utils.py
tests/functional/__init__.py
tests/functional/test_func_jax_env.py
tests/functional/test_functional.py
tests/functional/test_jax_blackjack.py
tests/functional/test_jax_cliffwalking.py
tests/spaces/__init__.py
tests/spaces/test_box.py
tests/spaces/test_dict.py
tests/spaces/test_discrete.py
tests/spaces/test_graph.py
tests/spaces/test_multibinary.py
tests/spaces/test_multidiscrete.py
tests/spaces/test_oneof.py
tests/spaces/test_sequence.py
tests/spaces/test_space.py
tests/spaces/test_spaces.py
tests/spaces/test_text.py
tests/spaces/test_tuple.py
tests/spaces/test_utils.py
tests/spaces/utils.py
tests/test_core.py
tests/testing_env.py
tests/utils/__init__.py
tests/utils/test_env_checker.py
tests/utils/test_env_checker_with_gym.py
tests/utils/test_passive_env_checker.py
tests/utils/test_performance.py
tests/utils/test_play.py
tests/utils/test_save_video.py
tests/utils/test_seeding.py
tests/utils/test_step_api_compatibility.py
tests/vector/__init__.py
tests/vector/test_async_vector_env.py
tests/vector/test_autoreset_mode.py
tests/vector/test_observation_mode.py
tests/vector/test_sync_vector_env.py
tests/vector/test_vector_env.py
tests/vector/test_vector_env_info.py
tests/vector/test_vector_wrapper.py
tests/vector/testing_utils.py
tests/vector/utils/__init__.py
tests/vector/utils/test_shared_memory.py
tests/vector/utils/test_space_utils.py
tests/vector/utils/utils.py
tests/wrappers/__init__.py
tests/wrappers/test_action_repeat.py
tests/wrappers/test_add_render_observation.py
tests/wrappers/test_array_conversion.py
tests/wrappers/test_atari_preprocessing.py
tests/wrappers/test_autoreset.py
tests/wrappers/test_clip_action.py
tests/wrappers/test_clip_reward.py
tests/wrappers/test_delay_observation.py
tests/wrappers/test_discretize_action.py
tests/wrappers/test_discretize_observation.py
tests/wrappers/test_dtype_observation.py
tests/wrappers/test_filter_observation.py
tests/wrappers/test_flatten_observation.py
tests/wrappers/test_frame_stack_observation.py
tests/wrappers/test_gray_scale_observation.py
tests/wrappers/test_human_rendering.py
tests/wrappers/test_import_wrappers.py
tests/wrappers/test_jax_to_numpy.py
tests/wrappers/test_jax_to_torch.py
tests/wrappers/test_lambda_action.py
tests/wrappers/test_lambda_observation.py
tests/wrappers/test_lambda_reward.py
tests/wrappers/test_max_and_skip_observation.py
tests/wrappers/test_normalize_observation.py
tests/wrappers/test_normalize_reward.py
tests/wrappers/test_numpy_to_torch.py
tests/wrappers/test_order_enforcing.py
tests/wrappers/test_passive_env_checker.py
tests/wrappers/test_record_constructor_args.py
tests/wrappers/test_record_episode_statistics.py
tests/wrappers/test_record_video.py
tests/wrappers/test_rescale_action.py
tests/wrappers/test_rescale_observation.py
tests/wrappers/test_reshape_observation.py
tests/wrappers/test_resize_observation.py
tests/wrappers/test_sticky_action.py
tests/wrappers/test_time_aware_observation.py
tests/wrappers/test_time_limit.py
tests/wrappers/test_white_noise_rendering.py
tests/wrappers/utils.py
tests/wrappers/vector/__init__.py
tests/wrappers/vector/test_array_conversion.py
tests/wrappers/vector/test_dict_info_to_list.py
tests/wrappers/vector/test_human_rendering.py
tests/wrappers/vector/test_normalize_observation.py
tests/wrappers/vector/test_normalize_reward.py
tests/wrappers/vector/test_record_episode_statistics.py
tests/wrappers/vector/test_record_video.py
tests/wrappers/vector/test_transform_action.py
tests/wrappers/vector/test_transform_observation.py
tests/wrappers/vector/test_vector_wrappers.py
tests/wrappers/vector/test_vectorize_transform.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 137 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `assets` | 1 | 3 KB | [`assets/_OMITTED.md`](./assets/_OMITTED.md) |
| `docs/_static/diagrams` | 3 | 707 KB | [`docs/_static/diagrams/_OMITTED.md`](./docs/_static/diagrams/_OMITTED.md) |
| `docs/_static/img` | 6 | 395 KB | [`docs/_static/img/_OMITTED.md`](./docs/_static/img/_OMITTED.md) |
| `docs/_static/img/tutorials` | 23 | 3.5 MB | [`docs/_static/img/tutorials/_OMITTED.md`](./docs/_static/img/tutorials/_OMITTED.md) |
| `docs/_static/videos` | 1 | 9.4 MB | [`docs/_static/videos/_OMITTED.md`](./docs/_static/videos/_OMITTED.md) |
| `docs/_static/videos/atari` | 104 | 13.4 MB | [`docs/_static/videos/atari/_OMITTED.md`](./docs/_static/videos/atari/_OMITTED.md) |
| `docs/_static/videos/box2d` | 3 | 5.5 MB | [`docs/_static/videos/box2d/_OMITTED.md`](./docs/_static/videos/box2d/_OMITTED.md) |
| `docs/_static/videos/classic_control` | 5 | 2.3 MB | [`docs/_static/videos/classic_control/_OMITTED.md`](./docs/_static/videos/classic_control/_OMITTED.md) |
| `docs/_static/videos/mujoco` | 11 | 68.7 MB | [`docs/_static/videos/mujoco/_OMITTED.md`](./docs/_static/videos/mujoco/_OMITTED.md) |
| `docs/_static/videos/toy_text` | 4 | 16.9 MB | [`docs/_static/videos/toy_text/_OMITTED.md`](./docs/_static/videos/toy_text/_OMITTED.md) |
| `docs/_static/videos/tutorials` | 1 | 40 KB | [`docs/_static/videos/tutorials/_OMITTED.md`](./docs/_static/videos/tutorials/_OMITTED.md) |
| `docs/environments/mujoco/action_space_figures` | 8 | 197 KB | [`docs/environments/mujoco/action_space_figures/_OMITTED.md`](./docs/environments/mujoco/action_space_figures/_OMITTED.md) |
| `gymnasium/envs/classic_control/assets` | 1 | 7 KB | [`gymnasium/envs/classic_control/assets/_OMITTED.md`](./gymnasium/envs/classic_control/assets/_OMITTED.md) |
| `gymnasium/envs/phys2d/assets` | 1 | 7 KB | [`gymnasium/envs/phys2d/assets/_OMITTED.md`](./gymnasium/envs/phys2d/assets/_OMITTED.md) |
| `gymnasium/envs/toy_text/font` | 1 | 14 KB | [`gymnasium/envs/toy_text/font/_OMITTED.md`](./gymnasium/envs/toy_text/font/_OMITTED.md) |
| `gymnasium/envs/toy_text/img` | 81 | 178 KB | [`gymnasium/envs/toy_text/img/_OMITTED.md`](./gymnasium/envs/toy_text/img/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
