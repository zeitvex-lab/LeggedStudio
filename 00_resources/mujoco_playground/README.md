# mujoco_playground — 参考资源

> **来源**：`00_open/mujoco_playground/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）、unitree_g1（宇树 G1 人形）
> **定位**：DeepMind MuJoCo Playground：Go1/G1 环境与策略
> **收录**：244 个文件 / 6.7 MB（其中推理策略/模型文件 6 个）
> **已省略**：53 个文件 / 11.8 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（10 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（2 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（27 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（15 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（14 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（80 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（10 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（86 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （9 个文件）
.github/  （2 个文件）
    workflows/
learning/  （8 个文件）
    (直接文件)/
    notebooks/
mujoco_playground/  （225 个文件）
    (直接文件)/
    _src/
    config/
    experimental/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 116 |
| `.xml` | 71 |
| `.ipynb` | 22 |
| `.md` | 14 |
| `.onnx` | 6 |
| `.csv` | 5 |
| `(无扩展名)` | 3 |
| `.yml` | 2 |
| `.yaml` | 1 |
| `.cff` | 1 |
| `.toml` | 1 |
| `.typed` | 1 |
| `.sh` | 1 |

## 文件索引（项目内相对路径）

```text
.github/workflows/ci.yml
.github/workflows/pypi.yml
.gitignore
.pre-commit-config.yaml
CHANGELOG.md
CITATION.cff
CONTRIBUTING.md
LICENSE
README.md
learning/README.md
learning/__init__.py
learning/notebooks/dm_control_suite.ipynb
learning/notebooks/locomotion.ipynb
learning/notebooks/manipulation.ipynb
learning/notebooks/vision.ipynb
learning/train_jax_ppo.py
learning/train_rsl_rl.py
mujoco_playground/__init__.py
mujoco_playground/_src/__init__.py
mujoco_playground/_src/dm_control_suite/README.md
mujoco_playground/_src/dm_control_suite/__init__.py
mujoco_playground/_src/dm_control_suite/acrobot.py
mujoco_playground/_src/dm_control_suite/ball_in_cup.py
mujoco_playground/_src/dm_control_suite/cartpole.py
mujoco_playground/_src/dm_control_suite/cheetah.py
mujoco_playground/_src/dm_control_suite/common.py
mujoco_playground/_src/dm_control_suite/dm_control_suite_test.py
mujoco_playground/_src/dm_control_suite/finger.py
mujoco_playground/_src/dm_control_suite/fish.py
mujoco_playground/_src/dm_control_suite/hopper.py
mujoco_playground/_src/dm_control_suite/humanoid.py
mujoco_playground/_src/dm_control_suite/pendulum.py
mujoco_playground/_src/dm_control_suite/point_mass.py
mujoco_playground/_src/dm_control_suite/reacher.py
mujoco_playground/_src/dm_control_suite/swimmer.py
mujoco_playground/_src/dm_control_suite/walker.py
mujoco_playground/_src/dm_control_suite/xmls/README.md
mujoco_playground/_src/dm_control_suite/xmls/acrobot.xml
mujoco_playground/_src/dm_control_suite/xmls/ball_in_cup.xml
mujoco_playground/_src/dm_control_suite/xmls/cartpole.xml
mujoco_playground/_src/dm_control_suite/xmls/cheetah.xml
mujoco_playground/_src/dm_control_suite/xmls/common/materials.xml
mujoco_playground/_src/dm_control_suite/xmls/common/skybox.xml
mujoco_playground/_src/dm_control_suite/xmls/common/visual.xml
mujoco_playground/_src/dm_control_suite/xmls/finger.xml
mujoco_playground/_src/dm_control_suite/xmls/fish.xml
mujoco_playground/_src/dm_control_suite/xmls/hopper.xml
mujoco_playground/_src/dm_control_suite/xmls/humanoid.xml
mujoco_playground/_src/dm_control_suite/xmls/manipulator.xml
mujoco_playground/_src/dm_control_suite/xmls/pendulum.xml
mujoco_playground/_src/dm_control_suite/xmls/point_mass.xml
mujoco_playground/_src/dm_control_suite/xmls/reacher.xml
mujoco_playground/_src/dm_control_suite/xmls/swimmer.xml
mujoco_playground/_src/dm_control_suite/xmls/walker.xml
mujoco_playground/_src/gait.py
mujoco_playground/_src/locomotion/__init__.py
mujoco_playground/_src/locomotion/apollo/__init__.py
mujoco_playground/_src/locomotion/apollo/base.py
mujoco_playground/_src/locomotion/apollo/constants.py
mujoco_playground/_src/locomotion/apollo/joystick.py
mujoco_playground/_src/locomotion/apollo/xmls/apollo_mjx_feetonly.xml
mujoco_playground/_src/locomotion/apollo/xmls/scene_mjx_feetonly_flat_terrain.xml
mujoco_playground/_src/locomotion/barkour/__init__.py
mujoco_playground/_src/locomotion/barkour/joystick.py
mujoco_playground/_src/locomotion/berkeley_humanoid/__init__.py
mujoco_playground/_src/locomotion/berkeley_humanoid/base.py
mujoco_playground/_src/locomotion/berkeley_humanoid/berkeley_humanoid_constants.py
mujoco_playground/_src/locomotion/berkeley_humanoid/joystick.py
mujoco_playground/_src/locomotion/berkeley_humanoid/randomize.py
mujoco_playground/_src/locomotion/berkeley_humanoid/xmls/berkeley_humanoid_mjx_feetonly.xml
mujoco_playground/_src/locomotion/berkeley_humanoid/xmls/scene_mjx_feetonly_flat_terrain.xml
mujoco_playground/_src/locomotion/berkeley_humanoid/xmls/scene_mjx_feetonly_rough_terrain.xml
mujoco_playground/_src/locomotion/berkeley_humanoid/xmls/sensor.xml
mujoco_playground/_src/locomotion/g1/__init__.py
mujoco_playground/_src/locomotion/g1/base.py
mujoco_playground/_src/locomotion/g1/g1_constants.py
mujoco_playground/_src/locomotion/g1/joystick.py
mujoco_playground/_src/locomotion/g1/randomize.py
mujoco_playground/_src/locomotion/g1/xmls/g1_mjx_feetonly.xml
mujoco_playground/_src/locomotion/g1/xmls/g1_mjx_feetonly_restricted.xml
mujoco_playground/_src/locomotion/g1/xmls/scene_mjx_feetonly.xml
mujoco_playground/_src/locomotion/g1/xmls/scene_mjx_feetonly_flat_terrain.xml
mujoco_playground/_src/locomotion/g1/xmls/scene_mjx_feetonly_rough_terrain.xml
mujoco_playground/_src/locomotion/g1/xmls/sensor.xml
mujoco_playground/_src/locomotion/go1/README.md
mujoco_playground/_src/locomotion/go1/__init__.py
mujoco_playground/_src/locomotion/go1/base.py
mujoco_playground/_src/locomotion/go1/getup.py
mujoco_playground/_src/locomotion/go1/go1_constants.py
mujoco_playground/_src/locomotion/go1/handstand.py
mujoco_playground/_src/locomotion/go1/joystick.py
mujoco_playground/_src/locomotion/go1/randomize.py
mujoco_playground/_src/locomotion/go1/xmls/go1_mjx.xml
mujoco_playground/_src/locomotion/go1/xmls/go1_mjx_feetonly.xml
mujoco_playground/_src/locomotion/go1/xmls/go1_mjx_fullcollisions.xml
mujoco_playground/_src/locomotion/go1/xmls/scene_mjx_feetonly_bowl.xml
mujoco_playground/_src/locomotion/go1/xmls/scene_mjx_feetonly_flat_terrain.xml
mujoco_playground/_src/locomotion/go1/xmls/scene_mjx_feetonly_rough_terrain.xml
mujoco_playground/_src/locomotion/go1/xmls/scene_mjx_feetonly_stairs.xml
mujoco_playground/_src/locomotion/go1/xmls/scene_mjx_flat_terrain.xml
mujoco_playground/_src/locomotion/go1/xmls/scene_mjx_fullcollisions_flat_terrain.xml
mujoco_playground/_src/locomotion/go1/xmls/sensor_feet.xml
mujoco_playground/_src/locomotion/go1/xmls/sensor_fullcollision.xml
mujoco_playground/_src/locomotion/h1/__init__.py
mujoco_playground/_src/locomotion/h1/base.py
mujoco_playground/_src/locomotion/h1/h1_constants.py
mujoco_playground/_src/locomotion/h1/inplace_gait_tracking.py
mujoco_playground/_src/locomotion/h1/joystick.py
mujoco_playground/_src/locomotion/h1/joystick_gait_tracking.py
mujoco_playground/_src/locomotion/h1/xmls/h1_mjx_feetonly.xml
mujoco_playground/_src/locomotion/h1/xmls/scene_mjx_feetonly.xml
mujoco_playground/_src/locomotion/locomotion_test.py
mujoco_playground/_src/locomotion/op3/__init__.py
mujoco_playground/_src/locomotion/op3/base.py
mujoco_playground/_src/locomotion/op3/joystick.py
mujoco_playground/_src/locomotion/op3/op3_constants.py
mujoco_playground/_src/locomotion/op3/xmls/op3_mjx_feetonly.xml
mujoco_playground/_src/locomotion/op3/xmls/scene_mjx_feetonly.xml
mujoco_playground/_src/locomotion/spot/__init__.py
mujoco_playground/_src/locomotion/spot/base.py
mujoco_playground/_src/locomotion/spot/getup.py
mujoco_playground/_src/locomotion/spot/joystick.py
mujoco_playground/_src/locomotion/spot/joystick_gait_tracking.py
mujoco_playground/_src/locomotion/spot/spot_constants.py
mujoco_playground/_src/locomotion/spot/xmls/scene_mjx_feetonly_flat_terrain.xml
mujoco_playground/_src/locomotion/spot/xmls/scene_mjx_flat_terrain.xml
mujoco_playground/_src/locomotion/spot/xmls/sensor.xml
mujoco_playground/_src/locomotion/spot/xmls/spot_mjx.xml
mujoco_playground/_src/locomotion/spot/xmls/spot_mjx_feetonly.xml
mujoco_playground/_src/locomotion/t1/__init__.py
mujoco_playground/_src/locomotion/t1/base.py
mujoco_playground/_src/locomotion/t1/joystick.py
mujoco_playground/_src/locomotion/t1/randomize.py
mujoco_playground/_src/locomotion/t1/t1_constants.py
mujoco_playground/_src/locomotion/t1/xmls/scene_mjx_feetonly_flat_terrain.xml
mujoco_playground/_src/locomotion/t1/xmls/scene_mjx_feetonly_rough_terrain.xml
mujoco_playground/_src/locomotion/t1/xmls/sensor.xml
mujoco_playground/_src/locomotion/t1/xmls/t1_mjx_feetonly.xml
mujoco_playground/_src/manipulation/__init__.py
mujoco_playground/_src/manipulation/aero_hand/README.md
mujoco_playground/_src/manipulation/aero_hand/__init__.py
mujoco_playground/_src/manipulation/aero_hand/aero_hand_constants.py
mujoco_playground/_src/manipulation/aero_hand/base.py
mujoco_playground/_src/manipulation/aero_hand/rotate_z.py
mujoco_playground/_src/manipulation/aero_hand/xmls/reorientation_cube.xml
mujoco_playground/_src/manipulation/aero_hand/xmls/right_hand.xml
mujoco_playground/_src/manipulation/aero_hand/xmls/scene_mjx_cube.xml
mujoco_playground/_src/manipulation/aloha/__init__.py
mujoco_playground/_src/manipulation/aloha/aloha_constants.py
mujoco_playground/_src/manipulation/aloha/base.py
mujoco_playground/_src/manipulation/aloha/handover.py
mujoco_playground/_src/manipulation/aloha/single_peg_insertion.py
mujoco_playground/_src/manipulation/aloha/xmls/joint_position_actuators.xml
mujoco_playground/_src/manipulation/aloha/xmls/mjx_aloha.xml
mujoco_playground/_src/manipulation/aloha/xmls/mjx_hand_over.xml
mujoco_playground/_src/manipulation/aloha/xmls/mjx_scene.xml
mujoco_playground/_src/manipulation/aloha/xmls/mjx_single_peg_insertion.xml
mujoco_playground/_src/manipulation/franka_emika_panda/__init__.py
mujoco_playground/_src/manipulation/franka_emika_panda/open_cabinet.py
mujoco_playground/_src/manipulation/franka_emika_panda/panda.py
mujoco_playground/_src/manipulation/franka_emika_panda/panda_kinematics.py
mujoco_playground/_src/manipulation/franka_emika_panda/pick.py
mujoco_playground/_src/manipulation/franka_emika_panda/pick_cartesian.py
mujoco_playground/_src/manipulation/franka_emika_panda/randomize_vision.py
mujoco_playground/_src/manipulation/franka_emika_panda/xmls/mjx_cabinet.xml
mujoco_playground/_src/manipulation/franka_emika_panda/xmls/mjx_scene.xml
mujoco_playground/_src/manipulation/franka_emika_panda/xmls/mjx_single_cube.xml
mujoco_playground/_src/manipulation/franka_emika_panda/xmls/mjx_single_cube_camera.xml
mujoco_playground/_src/manipulation/franka_emika_panda/xmls/sensor.xml
mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/__init__.py
mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/panda_robotiq.py
mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/push_cube.py
mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/xmls/panda_updated_robotiq_2f85.xml
mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/xmls/scene_panda_robotiq_cube.xml
mujoco_playground/_src/manipulation/leap_hand/README.md
mujoco_playground/_src/manipulation/leap_hand/__init__.py
mujoco_playground/_src/manipulation/leap_hand/base.py
mujoco_playground/_src/manipulation/leap_hand/leap_hand_constants.py
mujoco_playground/_src/manipulation/leap_hand/reorient.py
mujoco_playground/_src/manipulation/leap_hand/rotate_z.py
mujoco_playground/_src/manipulation/leap_hand/xmls/leap_rh_mjx.xml
mujoco_playground/_src/manipulation/leap_hand/xmls/reorientation_cube.xml
mujoco_playground/_src/manipulation/leap_hand/xmls/scene_mjx_cube.xml
mujoco_playground/_src/manipulation/manipulation_test.py
mujoco_playground/_src/mjx_env.py
mujoco_playground/_src/registry.py
mujoco_playground/_src/registry_test.py
mujoco_playground/_src/reward.py
mujoco_playground/_src/wrapper.py
mujoco_playground/_src/wrapper_test.py
mujoco_playground/_src/wrapper_torch.py
mujoco_playground/config/README.md
mujoco_playground/config/__init__.py
mujoco_playground/config/dm_control_suite_params.py
mujoco_playground/config/locomotion_params.py
mujoco_playground/config/manipulation_params.py
mujoco_playground/experimental/brax_network_to_onnx.ipynb
mujoco_playground/experimental/learning/README.md
mujoco_playground/experimental/learning/ablate_device_topology.ipynb
mujoco_playground/experimental/learning/apollo_joystick.ipynb
mujoco_playground/experimental/learning/cube_reorient.ipynb
mujoco_playground/experimental/learning/cube_rotate.ipynb
mujoco_playground/experimental/learning/dm_control_suite.ipynb
mujoco_playground/experimental/learning/gait_tracking.ipynb
mujoco_playground/experimental/learning/getup.ipynb
mujoco_playground/experimental/learning/handstand.ipynb
mujoco_playground/experimental/learning/humanoid_joystick.ipynb
mujoco_playground/experimental/learning/humanoid_joystick_gait_tracking.ipynb
mujoco_playground/experimental/learning/inference.ipynb
mujoco_playground/experimental/learning/joystick.ipynb
mujoco_playground/experimental/learning/joystick_gait_tracking.ipynb
mujoco_playground/experimental/learning/open_cabinet.ipynb
mujoco_playground/experimental/learning/phase.ipynb
mujoco_playground/experimental/learning/position_cube.ipynb
mujoco_playground/experimental/learning/viz_sim_policies.ipynb
mujoco_playground/experimental/madrona_benchmarking/README.md
mujoco_playground/experimental/madrona_benchmarking/benchmark.py
mujoco_playground/experimental/madrona_benchmarking/data/madrona_mjx.csv
mujoco_playground/experimental/madrona_benchmarking/data/maniskill3/README.md
mujoco_playground/experimental/madrona_benchmarking/data/maniskill3/isaac_lab.csv
mujoco_playground/experimental/madrona_benchmarking/data/maniskill3/isaac_lab_state.csv
mujoco_playground/experimental/madrona_benchmarking/data/maniskill3/maniskill.csv
mujoco_playground/experimental/madrona_benchmarking/data/maniskill3/maniskill_state.csv
mujoco_playground/experimental/madrona_benchmarking/get_data.sh
mujoco_playground/experimental/madrona_benchmarking/make_plots.py
mujoco_playground/experimental/madrona_benchmarking/print_tables.py
mujoco_playground/experimental/sim2sim/README.md
mujoco_playground/experimental/sim2sim/gamepad_reader.py
mujoco_playground/experimental/sim2sim/onnx/apollo_policy.onnx
mujoco_playground/experimental/sim2sim/onnx/bh_policy.onnx
mujoco_playground/experimental/sim2sim/onnx/g1_policy.onnx
mujoco_playground/experimental/sim2sim/onnx/go1_policy.onnx
mujoco_playground/experimental/sim2sim/onnx/leap_reorient_policy.onnx
mujoco_playground/experimental/sim2sim/onnx/t1_policy.onnx
mujoco_playground/experimental/sim2sim/play_apollo_joystick.py
mujoco_playground/experimental/sim2sim/play_bh_joystick.py
mujoco_playground/experimental/sim2sim/play_g1_joystick.py
mujoco_playground/experimental/sim2sim/play_go1_joystick.py
mujoco_playground/experimental/sim2sim/play_leap_reorient.py
mujoco_playground/experimental/sim2sim/play_t1_joystick.py
mujoco_playground/experimental/utils/plotting.py
mujoco_playground/py.typed
pylintrc
pyproject.toml
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 749 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `assets` | 1 | 124 KB | [`assets/_OMITTED.md`](./assets/_OMITTED.md) |
| `mujoco_playground/_src/locomotion/berkeley_humanoid/xmls/assets` | 2 | 1.7 MB | [`mujoco_playground/_src/locomotion/berkeley_humanoid/xmls/assets/_OMITTED.md`](./mujoco_playground/_src/locomotion/berkeley_humanoid/xmls/assets/_OMITTED.md) |
| `mujoco_playground/_src/locomotion/g1/xmls/assets` | 2 | 1.7 MB | [`mujoco_playground/_src/locomotion/g1/xmls/assets/_OMITTED.md`](./mujoco_playground/_src/locomotion/g1/xmls/assets/_OMITTED.md) |
| `mujoco_playground/_src/locomotion/go1/xmls/assets` | 2 | 1.7 MB | [`mujoco_playground/_src/locomotion/go1/xmls/assets/_OMITTED.md`](./mujoco_playground/_src/locomotion/go1/xmls/assets/_OMITTED.md) |
| `mujoco_playground/_src/locomotion/t1/xmls/assets` | 2 | 1.7 MB | [`mujoco_playground/_src/locomotion/t1/xmls/assets/_OMITTED.md`](./mujoco_playground/_src/locomotion/t1/xmls/assets/_OMITTED.md) |
| `mujoco_playground/_src/manipulation/aero_hand/imgs` | 5 | 415 KB | [`mujoco_playground/_src/manipulation/aero_hand/imgs/_OMITTED.md`](./mujoco_playground/_src/manipulation/aero_hand/imgs/_OMITTED.md) |
| `mujoco_playground/_src/manipulation/aero_hand/xmls/reorientation_cube_textures` | 1 | 49 KB | [`mujoco_playground/_src/manipulation/aero_hand/xmls/reorientation_cube_textures/_OMITTED.md`](./mujoco_playground/_src/manipulation/aero_hand/xmls/reorientation_cube_textures/_OMITTED.md) |
| `mujoco_playground/_src/manipulation/aloha/xmls/assets` | 2 | 1 KB | [`mujoco_playground/_src/manipulation/aloha/xmls/assets/_OMITTED.md`](./mujoco_playground/_src/manipulation/aloha/xmls/assets/_OMITTED.md) |
| `mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/assets` | 12 | 9 KB | [`mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/assets/_OMITTED.md`](./mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/assets/_OMITTED.md) |
| `mujoco_playground/_src/manipulation/leap_hand/xmls/meshes` | 2 | 62 KB | [`mujoco_playground/_src/manipulation/leap_hand/xmls/meshes/_OMITTED.md`](./mujoco_playground/_src/manipulation/leap_hand/xmls/meshes/_OMITTED.md) |
| `mujoco_playground/_src/manipulation/leap_hand/xmls/reorientation_cube_textures` | 13 | 75 KB | [`mujoco_playground/_src/manipulation/leap_hand/xmls/reorientation_cube_textures/_OMITTED.md`](./mujoco_playground/_src/manipulation/leap_hand/xmls/reorientation_cube_textures/_OMITTED.md) |
| `mujoco_playground/experimental/madrona_benchmarking/figures` | 7 | 3.6 MB | [`mujoco_playground/experimental/madrona_benchmarking/figures/_OMITTED.md`](./mujoco_playground/experimental/madrona_benchmarking/figures/_OMITTED.md) |
| `mujoco_playground/experimental/sim2sim/assets` | 1 | 56 KB | [`mujoco_playground/experimental/sim2sim/assets/_OMITTED.md`](./mujoco_playground/experimental/sim2sim/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
