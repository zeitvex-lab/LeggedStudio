# unitree_rl_mjlab — 参考资源

> **来源**：`00_open/unitree_rl_mjlab/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_g1（宇树 G1 人形）
> **定位**：宇树官方 mjlab 版 RL 工程：训练任务 + MuJoCo 部署（Go2/Go2W/G1）
> **收录**：403 个文件 / 22.4 MB（其中推理策略/模型文件 2 个）
> **已省略**：393 个文件 / 349.1 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（105 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（61 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（120 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（2 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（6 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（4 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（104 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （6 个文件）
deploy/  （120 个文件）
    include/
    robots/
    thirdparty/
doc/  （5 个文件）
    (直接文件)/
    license/
scripts/  （14 个文件）
    (直接文件)/
simulate/  （152 个文件）
    (直接文件)/
    mujoco/
    src/
src/  （106 个文件）
    (直接文件)/
    assets/
    tasks/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 103 |
| `.h` | 92 |
| `.xml` | 81 |
| `(无扩展名)` | 22 |
| `.cmake` | 22 |
| `.md` | 18 |
| `.cpp` | 17 |
| `.yaml` | 15 |
| `.cc` | 12 |
| `.txt` | 11 |
| `.onnx` | 2 |
| `.pc` | 2 |
| `.csv` | 2 |
| `.hpp` | 1 |
| `.data` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
AS2W_REFERENCE_24_40.md
LICENCE
README.md
README_zh.md
deploy/include/FSM/BaseState.h
deploy/include/FSM/CtrlFSM.h
deploy/include/FSM/FSMState.h
deploy/include/FSM/State_FixStand.h
deploy/include/FSM/State_Passive.h
deploy/include/FSM/State_RLBase.h
deploy/include/LinearInterpolator.h
deploy/include/isaaclab/algorithms/algorithms.h
deploy/include/isaaclab/assets/articulation/articulation.h
deploy/include/isaaclab/devices/keyboard/keyboard.h
deploy/include/isaaclab/envs/manager_based_rl_env.h
deploy/include/isaaclab/envs/mdp/actions/joint_actions.h
deploy/include/isaaclab/envs/mdp/observations/observations.h
deploy/include/isaaclab/envs/mdp/terminations.h
deploy/include/isaaclab/manager/action_manager.h
deploy/include/isaaclab/manager/manager_term_cfg.h
deploy/include/isaaclab/manager/observation_manager.h
deploy/include/isaaclab/utils/utils.h
deploy/include/param.h
deploy/include/unitree_articulation.h
deploy/include/unitree_joystick_dsl.hpp
deploy/robots/a2/CMakeLists.txt
deploy/robots/a2/config/config.yaml
deploy/robots/a2/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/a2/include/Types.h
deploy/robots/a2/main.cpp
deploy/robots/a2/src/State_RLBase.cpp
deploy/robots/g1/CMakeLists.txt
deploy/robots/g1/config/config.yaml
deploy/robots/g1/config/policy/mimic/dance1_subject2/exported/policy.onnx
deploy/robots/g1/config/policy/mimic/dance1_subject2/exported/policy.onnx.data
deploy/robots/g1/config/policy/mimic/dance1_subject2/params/dance1_subject2.npz
deploy/robots/g1/config/policy/mimic/dance1_subject2/params/deploy.yaml
deploy/robots/g1/config/policy/velocity/v0/exported/policy.onnx
deploy/robots/g1/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/g1/include/State_Mimic.h
deploy/robots/g1/include/Types.h
deploy/robots/g1/main.cpp
deploy/robots/g1/src/State_Mimic.cpp
deploy/robots/g1/src/State_RLBase.cpp
deploy/robots/g1_23dof/CMakeLists.txt
deploy/robots/g1_23dof/config/config.yaml
deploy/robots/g1_23dof/config/policy/mimic/dance1_subject2/params/deploy.yaml
deploy/robots/g1_23dof/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/g1_23dof/include/State_Mimic.h
deploy/robots/g1_23dof/include/Types.h
deploy/robots/g1_23dof/main.cpp
deploy/robots/g1_23dof/src/State_Mimic.cpp
deploy/robots/g1_23dof/src/State_RLBase.cpp
deploy/robots/go2/CMakeLists.txt
deploy/robots/go2/config/config.yaml
deploy/robots/go2/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/go2/include/Types.h
deploy/robots/go2/main.cpp
deploy/robots/go2/src/State_RLBase.cpp
deploy/robots/h1_2/CMakeLists.txt
deploy/robots/h1_2/config/config.yaml
deploy/robots/h1_2/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/h1_2/include/Types.h
deploy/robots/h1_2/main.cpp
deploy/robots/h1_2/src/State_RLBase.cpp
deploy/robots/r1/CMakeLists.txt
deploy/robots/r1/config/config.yaml
deploy/robots/r1/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/r1/include/Types.h
deploy/robots/r1/main.cpp
deploy/robots/r1/src/State_RLBase.cpp
deploy/thirdparty/cnpy/CMakeLists.txt
deploy/thirdparty/cnpy/LICENSE
deploy/thirdparty/cnpy/README.md
deploy/thirdparty/cnpy/cnpy.cpp
deploy/thirdparty/cnpy/cnpy.h
deploy/thirdparty/cnpy/example1.cpp
deploy/thirdparty/cnpy/mat2npz
deploy/thirdparty/cnpy/npy2mat
deploy/thirdparty/cnpy/npz2mat
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/GIT_COMMIT_ID
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/LICENSE
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/Privacy.md
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/README.md
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/ThirdPartyNotices.txt
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/VERSION_NUMBER
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/core/providers/custom_op_context.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/core/providers/resource.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/cpu_provider_factory.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_c_api.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_cxx_api.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_cxx_inline.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_float16.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_lite_custom_op.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_run_options_config_keys.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_session_options_config_keys.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/provider_options.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/cmake/onnxruntime/onnxruntimeConfig.cmake
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/cmake/onnxruntime/onnxruntimeConfigVersion.cmake
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/cmake/onnxruntime/onnxruntimeTargets-release.cmake
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/cmake/onnxruntime/onnxruntimeTargets.cmake
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/pkgconfig/libonnxruntime.pc
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/GIT_COMMIT_ID
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/LICENSE
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/Privacy.md
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/README.md
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/ThirdPartyNotices.txt
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/VERSION_NUMBER
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/core/providers/custom_op_context.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/core/providers/resource.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/cpu_provider_factory.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_c_api.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_cxx_api.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_cxx_inline.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_float16.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_lite_custom_op.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_run_options_config_keys.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_session_options_config_keys.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/provider_options.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/cmake/onnxruntime/onnxruntimeConfig.cmake
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/cmake/onnxruntime/onnxruntimeConfigVersion.cmake
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/cmake/onnxruntime/onnxruntimeTargets-release.cmake
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/cmake/onnxruntime/onnxruntimeTargets.cmake
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/pkgconfig/libonnxruntime.pc
doc/license/cnpy-license
doc/license/mjlab-license
doc/license/onnxruntime-license
doc/setup_en.md
doc/setup_zh.md
scripts/csv_to_npz.py
scripts/evaluate_go2w_aerial_rotation.py
scripts/evaluate_go2w_spin_stance.py
scripts/evaluate_go2w_stance_locomotion.py
scripts/evaluate_go2w_upright.py
scripts/list_envs.py
scripts/play.py
scripts/probe_go2w_aerial_envelope.py
scripts/record_go2w_aerial_rotation.py
scripts/record_go2w_spin_stance.py
scripts/record_go2w_stance_locomotion.py
scripts/record_go2w_upright.py
scripts/train.py
scripts/visualize_terrain.py
setup.py
simulate/CMakeLists.txt
simulate/config.yaml
simulate/mujoco/THIRD_PARTY_NOTICES
simulate/mujoco/bin/basic
simulate/mujoco/bin/compile
simulate/mujoco/bin/record
simulate/mujoco/bin/simulate
simulate/mujoco/bin/testspeed
simulate/mujoco/include/mujoco/experimental/usd/layer_sink.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/actuator.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/api.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/collisionAPI.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/imageableAPI.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/jointAPI.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/keyframe.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/materialAPI.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/meshCollisionAPI.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/sceneAPI.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/siteAPI.h
simulate/mujoco/include/mujoco/experimental/usd/mjcPhysics/tokens.h
simulate/mujoco/include/mujoco/experimental/usd/usd.h
simulate/mujoco/include/mujoco/experimental/usd/utils.h
simulate/mujoco/include/mujoco/experimental/usd/writer.h
simulate/mujoco/include/mujoco/mjdata.h
simulate/mujoco/include/mujoco/mjexport.h
simulate/mujoco/include/mujoco/mjmacro.h
simulate/mujoco/include/mujoco/mjmodel.h
simulate/mujoco/include/mujoco/mjplugin.h
simulate/mujoco/include/mujoco/mjrender.h
simulate/mujoco/include/mujoco/mjsan.h
simulate/mujoco/include/mujoco/mjspec.h
simulate/mujoco/include/mujoco/mjthread.h
simulate/mujoco/include/mujoco/mjtnum.h
simulate/mujoco/include/mujoco/mjui.h
simulate/mujoco/include/mujoco/mjvisualize.h
simulate/mujoco/include/mujoco/mjxmacro.h
simulate/mujoco/include/mujoco/mujoco.h
simulate/mujoco/model/adhesion/README.md
simulate/mujoco/model/adhesion/active_adhesion.xml
simulate/mujoco/model/balloons/balloons.xml
simulate/mujoco/model/car/car.xml
simulate/mujoco/model/cards/cards.xml
simulate/mujoco/model/cube/README.md
simulate/mujoco/model/cube/cube_3x3x3.xml
simulate/mujoco/model/flex/basket.xml
simulate/mujoco/model/flex/bunny.xml
simulate/mujoco/model/flex/bunny_with_uv.xml
simulate/mujoco/model/flex/flag.xml
simulate/mujoco/model/flex/floppy.xml
simulate/mujoco/model/flex/gripper.xml
simulate/mujoco/model/flex/gripper_trilinear.xml
simulate/mujoco/model/flex/jelly.xml
simulate/mujoco/model/flex/mannequin.xml
simulate/mujoco/model/flex/pancake.xml
simulate/mujoco/model/flex/plate.xml
simulate/mujoco/model/flex/poncho.xml
simulate/mujoco/model/flex/poncho_vertcollide.xml
simulate/mujoco/model/flex/press.xml
simulate/mujoco/model/flex/pulley.xml
simulate/mujoco/model/flex/scene.xml
simulate/mujoco/model/flex/softbox.xml
simulate/mujoco/model/flex/sphere_full.xml
simulate/mujoco/model/flex/sphere_passive.xml
simulate/mujoco/model/flex/sphere_radial.xml
simulate/mujoco/model/flex/sphere_trilinear.xml
simulate/mujoco/model/flex/trampoline.xml
simulate/mujoco/model/flex/trilinear.xml
simulate/mujoco/model/hammock/hammock.xml
simulate/mujoco/model/humanoid/100_humanoids.xml
simulate/mujoco/model/humanoid/22_humanoids.xml
simulate/mujoco/model/humanoid/README.md
simulate/mujoco/model/humanoid/humanoid.xml
simulate/mujoco/model/humanoid/humanoid100.xml
simulate/mujoco/model/mug/mug.xml
simulate/mujoco/model/plugin/actuator/pid.xml
simulate/mujoco/model/plugin/elasticity/belt.xml
simulate/mujoco/model/plugin/elasticity/cable.xml
simulate/mujoco/model/plugin/elasticity/coil.xml
simulate/mujoco/model/plugin/elasticity/scene.xml
simulate/mujoco/model/plugin/sdf/asset/README.md
simulate/mujoco/model/plugin/sdf/bowl.xml
simulate/mujoco/model/plugin/sdf/cow.xml
simulate/mujoco/model/plugin/sdf/gear.xml
simulate/mujoco/model/plugin/sdf/mesh.xml
simulate/mujoco/model/plugin/sdf/mug.xml
simulate/mujoco/model/plugin/sdf/nutbolt.xml
simulate/mujoco/model/plugin/sdf/primitives.xml
simulate/mujoco/model/plugin/sdf/scene.xml
simulate/mujoco/model/plugin/sdf/torus.xml
simulate/mujoco/model/plugin/sensor/touch_grid.xml
simulate/mujoco/model/replicate/README.md
simulate/mujoco/model/replicate/bowl.xml
simulate/mujoco/model/replicate/bunnies.xml
simulate/mujoco/model/replicate/container.xml
simulate/mujoco/model/replicate/cylinder.xml
simulate/mujoco/model/replicate/helix.xml
simulate/mujoco/model/replicate/leaves.xml
simulate/mujoco/model/replicate/newton_cradle.xml
simulate/mujoco/model/replicate/particle.xml
simulate/mujoco/model/replicate/particle_free.xml
simulate/mujoco/model/replicate/particle_free2d.xml
simulate/mujoco/model/replicate/scene.xml
simulate/mujoco/model/replicate/stonehenge.xml
simulate/mujoco/model/replicate/tendon.xml
simulate/mujoco/model/slider_crank/slider_crank.xml
simulate/mujoco/model/tactile/tactile.xml
simulate/mujoco/model/tendon_arm/arm26.xml
simulate/mujoco/sample/array_safety.h
simulate/mujoco/sample/basic.cc
simulate/mujoco/sample/cmake/CheckAvxSupport.cmake
simulate/mujoco/sample/cmake/FindOrFetch.cmake
simulate/mujoco/sample/cmake/MujocoHarden.cmake
simulate/mujoco/sample/cmake/MujocoLinkOptions.cmake
simulate/mujoco/sample/cmake/MujocoMacOS.cmake
simulate/mujoco/sample/cmake/SampleDependencies.cmake
simulate/mujoco/sample/cmake/SampleOptions.cmake
simulate/mujoco/sample/compile.cc
simulate/mujoco/sample/record.cc
simulate/mujoco/sample/testspeed.cc
simulate/mujoco/simulate/README.md
simulate/mujoco/simulate/array_safety.h
simulate/mujoco/simulate/cmake/CheckAvxSupport.cmake
simulate/mujoco/simulate/cmake/FindOrFetch.cmake
simulate/mujoco/simulate/cmake/MujocoHarden.cmake
simulate/mujoco/simulate/cmake/MujocoLinkOptions.cmake
simulate/mujoco/simulate/cmake/MujocoMacOS.cmake
simulate/mujoco/simulate/cmake/SimulateDependencies.cmake
simulate/mujoco/simulate/cmake/SimulateOptions.cmake
simulate/mujoco/simulate/glfw_adapter.cc
simulate/mujoco/simulate/glfw_adapter.h
simulate/mujoco/simulate/glfw_corevideo.h
simulate/mujoco/simulate/glfw_corevideo.mm
simulate/mujoco/simulate/glfw_dispatch.cc
simulate/mujoco/simulate/glfw_dispatch.h
simulate/mujoco/simulate/main.cc
simulate/mujoco/simulate/platform_ui_adapter.cc
simulate/mujoco/simulate/platform_ui_adapter.h
simulate/mujoco/simulate/simulate.cc
simulate/mujoco/simulate/simulate.h
simulate/src/joystick/LICENSE-2.0.txt
simulate/src/joystick/joystick.cc
simulate/src/joystick/joystick.h
simulate/src/joystick/jstest.cc
simulate/src/joystick/readme.md
simulate/src/lodepng/LICENSE
simulate/src/lodepng/README.md
simulate/src/lodepng/lodepng.cpp
simulate/src/lodepng/lodepng.h
simulate/src/main.cc
simulate/src/param.h
simulate/src/physics_joystick.h
simulate/src/unitree_sdk2_bridge.h
src/__init__.py
src/assets/__init__.py
src/assets/motions/__init__.py
src/assets/motions/g1/dance1_subject2.csv
src/assets/motions/g1_23dof/dance1_subject2.csv
src/assets/robots/__init__.py
src/assets/robots/unitree_a2/__init__.py
src/assets/robots/unitree_a2/a2_constants.py
src/assets/robots/unitree_a2/xmls/a2.xml
src/assets/robots/unitree_a2/xmls/scene_a2.xml
src/assets/robots/unitree_as2/__init__.py
src/assets/robots/unitree_as2/as2_constants.py
src/assets/robots/unitree_as2/xmls/as2.xml
src/assets/robots/unitree_g1/__init__.py
src/assets/robots/unitree_g1/g1_23dof_constants.py
src/assets/robots/unitree_g1/g1_constants.py
src/assets/robots/unitree_g1/xmls/g1.xml
src/assets/robots/unitree_g1/xmls/g1_23dof.xml
src/assets/robots/unitree_g1/xmls/scene_g1.xml
src/assets/robots/unitree_g1/xmls/scene_g1_23dof.xml
src/assets/robots/unitree_go2/__init__.py
src/assets/robots/unitree_go2/go2_constants.py
src/assets/robots/unitree_go2/xmls/go2.xml
src/assets/robots/unitree_go2/xmls/scene_go2.xml
src/assets/robots/unitree_go2w/__init__.py
src/assets/robots/unitree_go2w/go2w_constants.py
src/assets/robots/unitree_go2w/xmls/go2w.xml
src/assets/robots/unitree_go2w/xmls/scene.xml
src/assets/robots/unitree_go2w/xmls/scene_terrain.xml
src/assets/robots/unitree_h1_2/__init__.py
src/assets/robots/unitree_h1_2/h1_2_constants.py
src/assets/robots/unitree_h1_2/xmls/h1_2.xml
src/assets/robots/unitree_h1_2/xmls/scene_h1_2.xml
src/assets/robots/unitree_h2/__init__.py
src/assets/robots/unitree_h2/h2_constants.py
src/assets/robots/unitree_h2/xmls/h2.xml
src/assets/robots/unitree_r1/__init__.py
src/assets/robots/unitree_r1/r1_constants.py
src/assets/robots/unitree_r1/xmls/r1.xml
src/tasks/__init__.py
src/tasks/tracking/__init__.py
src/tasks/tracking/config/__init__.py
src/tasks/tracking/config/g1/__init__.py
src/tasks/tracking/config/g1/env_cfgs.py
src/tasks/tracking/config/g1/rl_cfg.py
src/tasks/tracking/config/g1_23dof/__init__.py
src/tasks/tracking/config/g1_23dof/env_cfgs.py
src/tasks/tracking/config/g1_23dof/rl_cfg.py
src/tasks/tracking/mdp/__init__.py
src/tasks/tracking/mdp/commands.py
src/tasks/tracking/mdp/metrics.py
src/tasks/tracking/mdp/observations.py
src/tasks/tracking/mdp/rewards.py
src/tasks/tracking/mdp/terminations.py
src/tasks/tracking/rl/__init__.py
src/tasks/tracking/rl/runner.py
src/tasks/tracking/tracking_env_cfg.py
src/tasks/velocity/__init__.py
src/tasks/velocity/config/__init__.py
src/tasks/velocity/config/a2/__init__.py
src/tasks/velocity/config/a2/env_cfgs.py
src/tasks/velocity/config/a2/rl_cfg.py
src/tasks/velocity/config/as2/__init__.py
src/tasks/velocity/config/as2/env_cfgs.py
src/tasks/velocity/config/as2/rl_cfg.py
src/tasks/velocity/config/g1/__init__.py
src/tasks/velocity/config/g1/env_cfgs.py
src/tasks/velocity/config/g1/rl_cfg.py
src/tasks/velocity/config/g1_23dof/__init__.py
src/tasks/velocity/config/g1_23dof/env_cfgs.py
src/tasks/velocity/config/g1_23dof/rl_cfg.py
src/tasks/velocity/config/go2/__init__.py
src/tasks/velocity/config/go2/env_cfgs.py
src/tasks/velocity/config/go2/rl_cfg.py
src/tasks/velocity/config/go2w/__init__.py
src/tasks/velocity/config/go2w/env_cfgs.py
src/tasks/velocity/config/go2w/rl_cfg.py
src/tasks/velocity/config/go2w_tricks/__init__.py
src/tasks/velocity/config/go2w_tricks/aerial_env_cfg.py
src/tasks/velocity/config/go2w_tricks/common_env_cfg.py
src/tasks/velocity/config/go2w_tricks/env_cfgs.py
src/tasks/velocity/config/go2w_tricks/ground_env_cfg.py
src/tasks/velocity/config/go2w_tricks/rl_cfg.py
src/tasks/velocity/config/h1_2/__init__.py
src/tasks/velocity/config/h1_2/env_cfgs.py
src/tasks/velocity/config/h1_2/rl_cfg.py
src/tasks/velocity/config/h2/__init__.py
src/tasks/velocity/config/h2/env_cfgs.py
src/tasks/velocity/config/h2/rl_cfg.py
src/tasks/velocity/config/r1/__init__.py
src/tasks/velocity/config/r1/env_cfgs.py
src/tasks/velocity/config/r1/rl_cfg.py
src/tasks/velocity/mdp/__init__.py
src/tasks/velocity/mdp/actions.py
src/tasks/velocity/mdp/curriculums.py
src/tasks/velocity/mdp/observations.py
src/tasks/velocity/mdp/rewards.py
src/tasks/velocity/mdp/terminations.py
src/tasks/velocity/mdp/trick_commands.py
src/tasks/velocity/mdp/trick_curriculums.py
src/tasks/velocity/mdp/trick_distributions.py
src/tasks/velocity/mdp/trick_rewards.py
src/tasks/velocity/mdp/velocity_command.py
src/tasks/velocity/rl/__init__.py
src/tasks/velocity/rl/runner.py
src/tasks/velocity/velocity_env_cfg.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib` | 4 | 17.0 MB | [`deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/_OMITTED.md`](./deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/_OMITTED.md) |
| `deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib` | 2 | 20.1 MB | [`deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/_OMITTED.md`](./deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/_OMITTED.md) |
| `doc/gif` | 8 | 38.7 MB | [`doc/gif/_OMITTED.md`](./doc/gif/_OMITTED.md) |
| `simulate/mujoco/bin/mujoco_plugin` | 4 | 1.6 MB | [`simulate/mujoco/bin/mujoco_plugin/_OMITTED.md`](./simulate/mujoco/bin/mujoco_plugin/_OMITTED.md) |
| `simulate/mujoco/lib` | 2 | 4.8 MB | [`simulate/mujoco/lib/_OMITTED.md`](./simulate/mujoco/lib/_OMITTED.md) |
| `simulate/mujoco/model/cards/assets` | 55 | 7.2 MB | [`simulate/mujoco/model/cards/assets/_OMITTED.md`](./simulate/mujoco/model/cards/assets/_OMITTED.md) |
| `simulate/mujoco/model/cube/assets` | 27 | 89 KB | [`simulate/mujoco/model/cube/assets/_OMITTED.md`](./simulate/mujoco/model/cube/assets/_OMITTED.md) |
| `simulate/mujoco/model/flex/asset` | 4 | 1.3 MB | [`simulate/mujoco/model/flex/asset/_OMITTED.md`](./simulate/mujoco/model/flex/asset/_OMITTED.md) |
| `simulate/mujoco/model/humanoid` | 1 | 388 KB | [`simulate/mujoco/model/humanoid/_OMITTED.md`](./simulate/mujoco/model/humanoid/_OMITTED.md) |
| `simulate/mujoco/model/mug` | 2 | 2.2 MB | [`simulate/mujoco/model/mug/_OMITTED.md`](./simulate/mujoco/model/mug/_OMITTED.md) |
| `simulate/mujoco/model/plugin/sdf/asset` | 3 | 421 KB | [`simulate/mujoco/model/plugin/sdf/asset/_OMITTED.md`](./simulate/mujoco/model/plugin/sdf/asset/_OMITTED.md) |
| `simulate/mujoco/model/plugin/sensor` | 1 | 195 B | [`simulate/mujoco/model/plugin/sensor/_OMITTED.md`](./simulate/mujoco/model/plugin/sensor/_OMITTED.md) |
| `simulate/mujoco/model/replicate` | 1 | 201 KB | [`simulate/mujoco/model/replicate/_OMITTED.md`](./simulate/mujoco/model/replicate/_OMITTED.md) |
| `simulate/mujoco/model/replicate/asset` | 1 | 311 KB | [`simulate/mujoco/model/replicate/asset/_OMITTED.md`](./simulate/mujoco/model/replicate/asset/_OMITTED.md) |
| `src/assets/robots/unitree_a2/xmls/assets` | 17 | 14.1 MB | [`src/assets/robots/unitree_a2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_a2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_as2/xmls/assets` | 18 | 65.5 MB | [`src/assets/robots/unitree_as2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_as2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_g1/xmls/assets` | 38 | 32.9 MB | [`src/assets/robots/unitree_g1/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_g1/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_go2/xmls/assets` | 16 | 27.8 MB | [`src/assets/robots/unitree_go2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_go2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_go2w/xmls` | 2 | 19 KB | [`src/assets/robots/unitree_go2w/xmls/_OMITTED.md`](./src/assets/robots/unitree_go2w/xmls/_OMITTED.md) |
| `src/assets/robots/unitree_go2w/xmls/assets` | 22 | 32.7 MB | [`src/assets/robots/unitree_go2w/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_go2w/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_h1_2/xmls/assets` | 90 | 47.9 MB | [`src/assets/robots/unitree_h1_2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_h1_2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_h2/xmls/assets` | 32 | 12.4 MB | [`src/assets/robots/unitree_h2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_h2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_r1/xmls/assets` | 43 | 21.6 MB | [`src/assets/robots/unitree_r1/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_r1/xmls/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
