# robosuite_new — 参考资源

> **来源**：`00_open/robosuite_new/`　｜　**类型**：参考项目
> **关联机型**：wuji_hand（无极灵巧手）、unitree_g1（宇树 G1 人形）
> **定位**：robosuite：MuJoCo 操作仿真框架（arenas/robots/objects/tasks 模块化 MJCF 组合 + OSC 控制器 + 遥操作）——wuji 灵巧手操作任务与资源组合模型参考
> **收录**：536 个文件 / 10.3 MB（其中推理策略/模型文件 0 个）
> **已省略**：806 个文件 / 624.1 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（299 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（6 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（62 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（1 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（17 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（150 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （11 个文件）
.github/  （7 个文件）
    (直接文件)/
    ISSUE_TEMPLATE/
    workflows/
docs/  （69 个文件）
    (直接文件)/
    _static/
    algorithms/
    images/
    modeling/
    modules/
    simulation/
    source/
    tutorials/
robosuite/  （432 个文件）
    (直接文件)/
    controllers/
    demos/
    devices/
    environments/
    examples/
    models/
    renderers/
    robots/
    scripts/
    utils/
    wrappers/
tests/  （17 个文件）
    test_controllers/
    test_environments/
    test_grippers/
    test_renderers/
    test_robots/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 233 |
| `.mtl` | 107 |
| `.xml` | 59 |
| `.rst` | 44 |
| `.json` | 27 |
| `.md` | 21 |
| `.msh` | 8 |
| `.yaml` | 7 |
| `(无扩展名)` | 5 |
| `.urdf` | 5 |
| `.xacro` | 5 |
| `.txt` | 4 |
| `.yml` | 2 |
| `.css` | 2 |
| `.in` | 1 |

## 文件索引（项目内相对路径）

```text
.github/ISSUE_TEMPLATE/bug-report.yml
.github/ISSUE_TEMPLATE/feature-request.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/workflows/pre-commit.yaml
.github/workflows/run-tests.yaml
.github/workflows/update-docs.yaml
.github/workflows/update-pypi.yaml
.gitignore
.pre-commit-config.yaml
AUTHORS
CONTRIBUTING.md
LICENSE
MANIFEST.in
README.md
docs/.gitignore
docs/Makefile
docs/_static/css/theme.css
docs/_static/js/custom.js
docs/_static/theme_overrides.css
docs/acknowledgement.md
docs/algorithms/benchmarking.md
docs/algorithms/demonstrations.md
docs/algorithms/sim2real.md
docs/basicusage.md
docs/changelog.md
docs/conf.py
docs/demos.md
docs/images/figures.pptx
docs/index.rst
docs/installation.md
docs/modeling/arena.rst
docs/modeling/mujoco_model.rst
docs/modeling/object_model.rst
docs/modeling/robot_model.rst
docs/modeling/task.rst
docs/modules/controllers.rst
docs/modules/devices.md
docs/modules/environments.md
docs/modules/objects.md
docs/modules/overview.md
docs/modules/renderers.md
docs/modules/robots.rst
docs/modules/sensors.md
docs/overview.md
docs/references.md
docs/simulation/controller.rst
docs/simulation/device.rst
docs/simulation/environment.rst
docs/simulation/robot.rst
docs/source/robosuite.controllers.composite.rst
docs/source/robosuite.controllers.interpolators.rst
docs/source/robosuite.controllers.parts.arm.rst
docs/source/robosuite.controllers.parts.generic.rst
docs/source/robosuite.controllers.parts.gripper.rst
docs/source/robosuite.controllers.parts.mobile_base.rst
docs/source/robosuite.controllers.parts.rst
docs/source/robosuite.controllers.rst
docs/source/robosuite.devices.rst
docs/source/robosuite.environments.manipulation.rst
docs/source/robosuite.environments.rst
docs/source/robosuite.models.arenas.rst
docs/source/robosuite.models.bases.rst
docs/source/robosuite.models.grippers.rst
docs/source/robosuite.models.mounts.rst
docs/source/robosuite.models.objects.composite.rst
docs/source/robosuite.models.objects.composite_body.rst
docs/source/robosuite.models.objects.group.rst
docs/source/robosuite.models.objects.primitive.rst
docs/source/robosuite.models.objects.rst
docs/source/robosuite.models.robots.manipulators.rst
docs/source/robosuite.models.robots.rst
docs/source/robosuite.models.rst
docs/source/robosuite.models.tasks.rst
docs/source/robosuite.renderers.context.rst
docs/source/robosuite.renderers.mjviewer.rst
docs/source/robosuite.renderers.mujoco.rst
docs/source/robosuite.renderers.rst
docs/source/robosuite.robots.rst
docs/source/robosuite.rst
docs/source/robosuite.utils.rst
docs/source/robosuite.wrappers.rst
docs/tutorials/add_controller.md
docs/tutorials/add_environment.md
pyproject.toml
requirements-extra.txt
requirements.txt
robosuite/__init__.py
robosuite/controllers/__init__.py
robosuite/controllers/composite/__init__.py
robosuite/controllers/composite/composite_controller.py
robosuite/controllers/composite/composite_controller_factory.py
robosuite/controllers/config/default/composite/basic.json
robosuite/controllers/config/default/composite/hybrid_mobile_base.json
robosuite/controllers/config/default/composite/whole_body_ik.json
robosuite/controllers/config/default/composite/whole_body_mink_ik.json
robosuite/controllers/config/default/parts/ik_pose.json
robosuite/controllers/config/default/parts/joint_position.json
robosuite/controllers/config/default/parts/joint_torque.json
robosuite/controllers/config/default/parts/joint_velocity.json
robosuite/controllers/config/default/parts/osc_pose.json
robosuite/controllers/config/default/parts/osc_position.json
robosuite/controllers/config/robots/default_baxter.json
robosuite/controllers/config/robots/default_gr1.json
robosuite/controllers/config/robots/default_gr1_fixed_lower_body.json
robosuite/controllers/config/robots/default_gr1_floating_body.json
robosuite/controllers/config/robots/default_iiwa.json
robosuite/controllers/config/robots/default_kinova3.json
robosuite/controllers/config/robots/default_panda.json
robosuite/controllers/config/robots/default_panda_dex.json
robosuite/controllers/config/robots/default_pandaomron.json
robosuite/controllers/config/robots/default_pandaomron_whole_body_ik.json
robosuite/controllers/config/robots/default_sawyer.json
robosuite/controllers/config/robots/default_spotwitharm.json
robosuite/controllers/config/robots/default_tiago.json
robosuite/controllers/config/robots/default_tiago_whole_body_ik.json
robosuite/controllers/config/robots/default_ur5e.json
robosuite/controllers/parts/__init__.py
robosuite/controllers/parts/arm/__init__.py
robosuite/controllers/parts/arm/ik.py
robosuite/controllers/parts/arm/osc.py
robosuite/controllers/parts/controller.py
robosuite/controllers/parts/controller_factory.py
robosuite/controllers/parts/generic/__init__.py
robosuite/controllers/parts/generic/joint_pos.py
robosuite/controllers/parts/generic/joint_tor.py
robosuite/controllers/parts/generic/joint_vel.py
robosuite/controllers/parts/gripper/__init__.py
robosuite/controllers/parts/gripper/gripper_controller.py
robosuite/controllers/parts/gripper/simple_grip.py
robosuite/controllers/parts/mobile_base/__init__.py
robosuite/controllers/parts/mobile_base/joint_vel.py
robosuite/controllers/parts/mobile_base/mobile_base_controller.py
robosuite/demos/demo_collect_and_playback_data.py
robosuite/demos/demo_composite_robot.py
robosuite/demos/demo_control.py
robosuite/demos/demo_device_control.py
robosuite/demos/demo_domain_randomization.py
robosuite/demos/demo_gripper_interaction.py
robosuite/demos/demo_gripper_selection.py
robosuite/demos/demo_gym_functionality.py
robosuite/demos/demo_multi_camera.py
robosuite/demos/demo_random_action.py
robosuite/demos/demo_renderers.py
robosuite/demos/demo_segmentation.py
robosuite/demos/demo_sensor_corruption.py
robosuite/demos/demo_usd_export.py
robosuite/demos/demo_video_recording.py
robosuite/devices/__init__.py
robosuite/devices/device.py
robosuite/devices/dualsense.py
robosuite/devices/keyboard.py
robosuite/devices/mjgui.py
robosuite/devices/spacemouse.py
robosuite/environments/__init__.py
robosuite/environments/base.py
robosuite/environments/manipulation/__init__.py
robosuite/environments/manipulation/door.py
robosuite/environments/manipulation/lift.py
robosuite/environments/manipulation/manipulation_env.py
robosuite/environments/manipulation/nut_assembly.py
robosuite/environments/manipulation/pick_place.py
robosuite/environments/manipulation/stack.py
robosuite/environments/manipulation/tool_hang.py
robosuite/environments/manipulation/two_arm_env.py
robosuite/environments/manipulation/two_arm_handover.py
robosuite/environments/manipulation/two_arm_lift.py
robosuite/environments/manipulation/two_arm_peg_in_hole.py
robosuite/environments/manipulation/two_arm_transport.py
robosuite/environments/manipulation/wipe.py
robosuite/environments/robot_env.py
robosuite/examples/third_party_controller/default_mink_ik_gr1.json
robosuite/examples/third_party_controller/mink_controller.py
robosuite/examples/third_party_controller/teleop_mink.py
robosuite/macros.py
robosuite/models/__init__.py
robosuite/models/arenas/__init__.py
robosuite/models/arenas/arena.py
robosuite/models/arenas/bins_arena.py
robosuite/models/arenas/empty_arena.py
robosuite/models/arenas/multi_table_arena.py
robosuite/models/arenas/pegs_arena.py
robosuite/models/arenas/table_arena.py
robosuite/models/arenas/wipe_arena.py
robosuite/models/assets/arenas/bins_arena.xml
robosuite/models/assets/arenas/empty_arena.xml
robosuite/models/assets/arenas/multi_table_arena.xml
robosuite/models/assets/arenas/pegs_arena.xml
robosuite/models/assets/arenas/table_arena.xml
robosuite/models/assets/base.xml
robosuite/models/assets/bases/floating_legged_base.xml
robosuite/models/assets/bases/meshes/rethink_minimal_mount/pedestal_collision.mtl
robosuite/models/assets/bases/meshes/rethink_minimal_mount/pedestal_vis.mtl
robosuite/models/assets/bases/meshes/rethink_mount/pedestal.mtl
robosuite/models/assets/bases/no_actuation_base.xml
robosuite/models/assets/bases/null_base.xml
robosuite/models/assets/bases/null_mobile_base.xml
robosuite/models/assets/bases/null_mount.xml
robosuite/models/assets/bases/omron_mobile_base.xml
robosuite/models/assets/bases/rethink_minimal_mount.xml
robosuite/models/assets/bases/rethink_mount.xml
robosuite/models/assets/bullet_data/baxter_description/urdf/baxter_arm.urdf
robosuite/models/assets/bullet_data/panda_description/CMakeLists.txt
robosuite/models/assets/bullet_data/panda_description/mainpage.dox
robosuite/models/assets/bullet_data/panda_description/package.xml
robosuite/models/assets/bullet_data/panda_description/rosdoc.yaml
robosuite/models/assets/bullet_data/panda_description/urdf/hand.urdf
robosuite/models/assets/bullet_data/panda_description/urdf/hand.urdf.xacro
robosuite/models/assets/bullet_data/panda_description/urdf/hand.xacro
robosuite/models/assets/bullet_data/panda_description/urdf/panda_arm.urdf
robosuite/models/assets/bullet_data/panda_description/urdf/panda_arm.urdf.xacro
robosuite/models/assets/bullet_data/panda_description/urdf/panda_arm.xacro
robosuite/models/assets/bullet_data/panda_description/urdf/panda_arm_hand.urdf
robosuite/models/assets/bullet_data/panda_description/urdf/panda_arm_hand.urdf.xacro
robosuite/models/assets/bullet_data/sawyer_description/CMakeLists.txt
robosuite/models/assets/bullet_data/sawyer_description/config/sawyer.rviz
robosuite/models/assets/bullet_data/sawyer_description/launch/test_sawyer_description.launch.test
robosuite/models/assets/bullet_data/sawyer_description/package.xml
robosuite/models/assets/bullet_data/sawyer_description/params/named_poses.yaml
robosuite/models/assets/bullet_data/sawyer_description/urdf/sawyer_arm.urdf
robosuite/models/assets/grippers/bd_gripper.xml
robosuite/models/assets/grippers/fourier_left_hand.xml
robosuite/models/assets/grippers/fourier_right_hand.xml
robosuite/models/assets/grippers/inspire_left_hand.xml
robosuite/models/assets/grippers/inspire_right_hand.xml
robosuite/models/assets/grippers/jaco_three_finger_gripper.xml
robosuite/models/assets/grippers/meshes/jaco_three_finger_gripper/finger_distal.mtl
robosuite/models/assets/grippers/meshes/jaco_three_finger_gripper/finger_proximal.mtl
robosuite/models/assets/grippers/meshes/jaco_three_finger_gripper/hand_3finger.mtl
robosuite/models/assets/grippers/meshes/jaco_three_finger_gripper/ring_small.mtl
robosuite/models/assets/grippers/meshes/panda_gripper/finger_vis.mtl
robosuite/models/assets/grippers/meshes/panda_gripper/hand_vis.mtl
robosuite/models/assets/grippers/meshes/rethink_gripper/connector_plate.mtl
robosuite/models/assets/grippers/meshes/rethink_gripper/electric_gripper_base.mtl
robosuite/models/assets/grippers/meshes/rethink_gripper/half_round_tip.mtl
robosuite/models/assets/grippers/meshes/rethink_gripper/standard_narrow.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_85_inner_finger.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_85_inner_finger_vis.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_85_inner_knuckle.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_85_inner_knuckle_vis.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_85_outer_finger.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_85_outer_finger_vis.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_85_outer_knuckle.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_85_outer_knuckle_vis.mtl
robosuite/models/assets/grippers/meshes/robotiq_85_gripper/robotiq_arg2f_base_link.mtl
robosuite/models/assets/grippers/meshes/robotiq_s_gripper/link_0_vis.mtl
robosuite/models/assets/grippers/meshes/robotiq_s_gripper/link_1_vis.mtl
robosuite/models/assets/grippers/meshes/robotiq_s_gripper/link_2_vis.mtl
robosuite/models/assets/grippers/meshes/robotiq_s_gripper/link_3_vis.mtl
robosuite/models/assets/grippers/meshes/robotiq_s_gripper/palm_vis.mtl
robosuite/models/assets/grippers/null_gripper.xml
robosuite/models/assets/grippers/obj_meshes/rethink_gripper/connector_plate.mtl
robosuite/models/assets/grippers/obj_meshes/rethink_gripper/connector_plate/connector_plate.xml
robosuite/models/assets/grippers/obj_meshes/rethink_gripper/electric_gripper_base.mtl
robosuite/models/assets/grippers/panda_gripper.xml
robosuite/models/assets/grippers/rethink_gripper.xml
robosuite/models/assets/grippers/robotiq_gripper_140.xml
robosuite/models/assets/grippers/robotiq_gripper_85.xml
robosuite/models/assets/grippers/robotiq_gripper_s.xml
robosuite/models/assets/grippers/suction_gripper.xml
robosuite/models/assets/grippers/wiping_gripper.xml
robosuite/models/assets/grippers/xarm7_gripper.xml
robosuite/models/assets/objects/bottle.xml
robosuite/models/assets/objects/bread-visual.xml
robosuite/models/assets/objects/bread.xml
robosuite/models/assets/objects/can-visual.xml
robosuite/models/assets/objects/can.xml
robosuite/models/assets/objects/cereal-visual.xml
robosuite/models/assets/objects/cereal.xml
robosuite/models/assets/objects/door.xml
robosuite/models/assets/objects/door_lock.xml
robosuite/models/assets/objects/lemon.xml
robosuite/models/assets/objects/meshes/bottle.msh
robosuite/models/assets/objects/meshes/bottle.mtl
robosuite/models/assets/objects/meshes/bread.msh
robosuite/models/assets/objects/meshes/bread.mtl
robosuite/models/assets/objects/meshes/can.msh
robosuite/models/assets/objects/meshes/can.mtl
robosuite/models/assets/objects/meshes/cereal.msh
robosuite/models/assets/objects/meshes/cereal.mtl
robosuite/models/assets/objects/meshes/cylinder.msh
robosuite/models/assets/objects/meshes/handles.msh
robosuite/models/assets/objects/meshes/handles.mtl
robosuite/models/assets/objects/meshes/lemon.msh
robosuite/models/assets/objects/meshes/lemon.mtl
robosuite/models/assets/objects/meshes/milk.msh
robosuite/models/assets/objects/meshes/milk.mtl
robosuite/models/assets/objects/milk-visual.xml
robosuite/models/assets/objects/milk.xml
robosuite/models/assets/objects/plate-with-hole.xml
robosuite/models/assets/objects/round-nut.xml
robosuite/models/assets/objects/square-nut.xml
robosuite/models/assets/robots/baxter/obj_meshes/head/H0.mtl
robosuite/models/assets/robots/baxter/obj_meshes/head/H1.mtl
robosuite/models/assets/robots/baxter/obj_meshes/lower_elbow/E1.mtl
robosuite/models/assets/robots/baxter/obj_meshes/lower_forearm/W1.mtl
robosuite/models/assets/robots/baxter/obj_meshes/lower_shoulder/S1.mtl
robosuite/models/assets/robots/baxter/obj_meshes/torso/base_link.mtl
robosuite/models/assets/robots/baxter/obj_meshes/torso/base_link_collision.mtl
robosuite/models/assets/robots/baxter/obj_meshes/upper_elbow/E0.mtl
robosuite/models/assets/robots/baxter/obj_meshes/upper_forearm/W0.mtl
robosuite/models/assets/robots/baxter/obj_meshes/upper_shoulder/S0.mtl
robosuite/models/assets/robots/baxter/obj_meshes/wrist/W2.mtl
robosuite/models/assets/robots/baxter/robot.xml
robosuite/models/assets/robots/gr1/robot.xml
robosuite/models/assets/robots/iiwa/meshes/link_0_vis.mtl
robosuite/models/assets/robots/iiwa/meshes/link_1_vis.mtl
robosuite/models/assets/robots/iiwa/meshes/link_2_vis.mtl
robosuite/models/assets/robots/iiwa/meshes/link_3_vis.mtl
robosuite/models/assets/robots/iiwa/meshes/link_4_vis.mtl
robosuite/models/assets/robots/iiwa/meshes/link_5_vis.mtl
robosuite/models/assets/robots/iiwa/meshes/link_6_vis.mtl
robosuite/models/assets/robots/iiwa/meshes/link_7_vis.mtl
robosuite/models/assets/robots/iiwa/meshes/pedestal.mtl
robosuite/models/assets/robots/iiwa/robot.xml
robosuite/models/assets/robots/jaco/meshes/arm_half_1.mtl
robosuite/models/assets/robots/jaco/meshes/arm_half_2.mtl
robosuite/models/assets/robots/jaco/meshes/base.mtl
robosuite/models/assets/robots/jaco/meshes/forearm.mtl
robosuite/models/assets/robots/jaco/meshes/pedestal.mtl
robosuite/models/assets/robots/jaco/meshes/ring_big.mtl
robosuite/models/assets/robots/jaco/meshes/ring_small.mtl
robosuite/models/assets/robots/jaco/meshes/shoulder.mtl
robosuite/models/assets/robots/jaco/meshes/wrist_spherical_1.mtl
robosuite/models/assets/robots/jaco/meshes/wrist_spherical_2.mtl
robosuite/models/assets/robots/jaco/robot.xml
robosuite/models/assets/robots/kinova3/meshes/base_link.mtl
robosuite/models/assets/robots/kinova3/meshes/bracelet_no_vision_link.mtl
robosuite/models/assets/robots/kinova3/meshes/bracelet_with_vision_link.mtl
robosuite/models/assets/robots/kinova3/meshes/end_effector_link.mtl
robosuite/models/assets/robots/kinova3/meshes/forearm_link.mtl
robosuite/models/assets/robots/kinova3/meshes/half_arm_1_link.mtl
robosuite/models/assets/robots/kinova3/meshes/half_arm_2_link.mtl
robosuite/models/assets/robots/kinova3/meshes/pedestal.mtl
robosuite/models/assets/robots/kinova3/meshes/shoulder_link.mtl
robosuite/models/assets/robots/kinova3/meshes/spherical_wrist_1_link.mtl
robosuite/models/assets/robots/kinova3/meshes/spherical_wrist_2_link.mtl
robosuite/models/assets/robots/kinova3/robot.xml
robosuite/models/assets/robots/panda/robot.xml
robosuite/models/assets/robots/sawyer/obj_meshes/base.mtl
robosuite/models/assets/robots/sawyer/obj_meshes/head.mtl
robosuite/models/assets/robots/sawyer/obj_meshes/l0.mtl
robosuite/models/assets/robots/sawyer/obj_meshes/l1.mtl
robosuite/models/assets/robots/sawyer/obj_meshes/l2.mtl
robosuite/models/assets/robots/sawyer/obj_meshes/l3.mtl
robosuite/models/assets/robots/sawyer/obj_meshes/l4.mtl
robosuite/models/assets/robots/sawyer/obj_meshes/l5.mtl
robosuite/models/assets/robots/sawyer/obj_meshes/l6.mtl
robosuite/models/assets/robots/sawyer/robot.xml
robosuite/models/assets/robots/spot/robot.xml
robosuite/models/assets/robots/spot_arm/robot.xml
robosuite/models/assets/robots/tiago/meshes/arm/arm_1.mtl
robosuite/models/assets/robots/tiago/meshes/arm/arm_2.mtl
robosuite/models/assets/robots/tiago/meshes/arm/arm_3.mtl
robosuite/models/assets/robots/tiago/meshes/arm/arm_4.mtl
robosuite/models/assets/robots/tiago/meshes/arm/arm_6-wrist-2017.mtl
robosuite/models/assets/robots/tiago/meshes/grippers/gripper_finger_link.mtl
robosuite/models/assets/robots/tiago/meshes/grippers/gripper_link.mtl
robosuite/models/assets/robots/tiago/meshes/wheels/caster_1.mtl
robosuite/models/assets/robots/tiago/meshes/wheels/caster_2.mtl
robosuite/models/assets/robots/tiago/meshes/wheels/suspension_front_link.mtl
robosuite/models/assets/robots/tiago/meshes/wheels/suspension_rear_link.mtl
robosuite/models/assets/robots/tiago/meshes/wheels/wheel.mtl
robosuite/models/assets/robots/tiago/meshes/wheels/wheel_link.mtl
robosuite/models/assets/robots/tiago/robot.xml
robosuite/models/assets/robots/ur5e/meshes/base_vis.mtl
robosuite/models/assets/robots/ur5e/meshes/forearm_vis.mtl
robosuite/models/assets/robots/ur5e/meshes/pedestal.mtl
robosuite/models/assets/robots/ur5e/meshes/shoulder_vis.mtl
robosuite/models/assets/robots/ur5e/meshes/upperarm_vis.mtl
robosuite/models/assets/robots/ur5e/meshes/wrist1_vis.mtl
robosuite/models/assets/robots/ur5e/meshes/wrist2_vis.mtl
robosuite/models/assets/robots/ur5e/meshes/wrist3_vis.mtl
robosuite/models/assets/robots/ur5e/robot.xml
robosuite/models/assets/robots/xarm7/robot.xml
robosuite/models/base.py
robosuite/models/bases/__init__.py
robosuite/models/bases/floating_legged_base.py
robosuite/models/bases/leg_base_model.py
robosuite/models/bases/mobile_base_model.py
robosuite/models/bases/mount_model.py
robosuite/models/bases/no_actuation_base.py
robosuite/models/bases/null_base.py
robosuite/models/bases/null_base_model.py
robosuite/models/bases/null_mobile_base.py
robosuite/models/bases/null_mount.py
robosuite/models/bases/omron_mobile_base.py
robosuite/models/bases/rethink_minimal_mount.py
robosuite/models/bases/rethink_mount.py
robosuite/models/bases/robot_base_factory.py
robosuite/models/bases/robot_base_model.py
robosuite/models/bases/spot_base.py
robosuite/models/grippers/__init__.py
robosuite/models/grippers/bd_gripper.py
robosuite/models/grippers/fourier_hands.py
robosuite/models/grippers/gripper_factory.py
robosuite/models/grippers/gripper_model.py
robosuite/models/grippers/gripper_tester.py
robosuite/models/grippers/inspire_hands.py
robosuite/models/grippers/jaco_three_finger_gripper.py
robosuite/models/grippers/null_gripper.py
robosuite/models/grippers/panda_gripper.py
robosuite/models/grippers/rethink_gripper.py
robosuite/models/grippers/robotiq_140_gripper.py
robosuite/models/grippers/robotiq_85_gripper.py
robosuite/models/grippers/robotiq_three_finger_gripper.py
robosuite/models/grippers/suction_gripper.py
robosuite/models/grippers/wiping_gripper.py
robosuite/models/grippers/xarm7_gripper.py
robosuite/models/objects/__init__.py
robosuite/models/objects/composite/__init__.py
robosuite/models/objects/composite/bin.py
robosuite/models/objects/composite/cone.py
robosuite/models/objects/composite/hammer.py
robosuite/models/objects/composite/hollow_cylinder.py
robosuite/models/objects/composite/hook_frame.py
robosuite/models/objects/composite/lid.py
robosuite/models/objects/composite/pot_with_handles.py
robosuite/models/objects/composite/stand_with_mount.py
robosuite/models/objects/composite_body/__init__.py
robosuite/models/objects/composite_body/hinged_box.py
robosuite/models/objects/composite_body/ratcheting_wrench.py
robosuite/models/objects/generated_objects.py
robosuite/models/objects/group/__init__.py
robosuite/models/objects/group/transport.py
robosuite/models/objects/object_groups.py
robosuite/models/objects/objects.py
robosuite/models/objects/primitive/__init__.py
robosuite/models/objects/primitive/ball.py
robosuite/models/objects/primitive/box.py
robosuite/models/objects/primitive/capsule.py
robosuite/models/objects/primitive/cylinder.py
robosuite/models/objects/xml_objects.py
robosuite/models/robots/__init__.py
robosuite/models/robots/compositional.py
robosuite/models/robots/manipulators/__init__.py
robosuite/models/robots/manipulators/baxter_robot.py
robosuite/models/robots/manipulators/gr1_robot.py
robosuite/models/robots/manipulators/humanoid_model.py
robosuite/models/robots/manipulators/humanoid_upperbody_model.py
robosuite/models/robots/manipulators/iiwa_robot.py
robosuite/models/robots/manipulators/jaco_robot.py
robosuite/models/robots/manipulators/kinova3_robot.py
robosuite/models/robots/manipulators/legged_manipulator_model.py
robosuite/models/robots/manipulators/manipulator_model.py
robosuite/models/robots/manipulators/panda_robot.py
robosuite/models/robots/manipulators/sawyer_robot.py
robosuite/models/robots/manipulators/spot_arm.py
robosuite/models/robots/manipulators/tiago_robot.py
robosuite/models/robots/manipulators/ur5e_robot.py
robosuite/models/robots/manipulators/xarm7_robot.py
robosuite/models/robots/robot_model.py
robosuite/models/tasks/__init__.py
robosuite/models/tasks/manipulation_task.py
robosuite/models/tasks/task.py
robosuite/models/world.py
robosuite/renderers/__init__.py
robosuite/renderers/base.py
robosuite/renderers/base_parser.py
robosuite/renderers/config/nvisii_config.json
robosuite/renderers/context/__init__.py
robosuite/renderers/context/egl_context.py
robosuite/renderers/context/glfw_context.py
robosuite/renderers/context/osmesa_context.py
robosuite/renderers/viewer/__init__.py
robosuite/renderers/viewer/mjviewer_renderer.py
robosuite/renderers/viewer/opencv_renderer.py
robosuite/robots/__init__.py
robosuite/robots/fixed_base_robot.py
robosuite/robots/legged_robot.py
robosuite/robots/mobile_robot.py
robosuite/robots/robot.py
robosuite/robots/wheeled_robot.py
robosuite/scripts/browse_mjcf_model.py
robosuite/scripts/check_custom_robot_model.py
robosuite/scripts/collect_human_demonstrations.py
robosuite/scripts/compile_mjcf_model.py
robosuite/scripts/internal/view_robot_initialization.py
robosuite/scripts/make_reset_video.py
robosuite/scripts/playback_demonstrations_from_hdf5.py
robosuite/scripts/print_robosuite_info.py
robosuite/scripts/print_robot_action_info.py
robosuite/scripts/render_dataset_with_omniverse.py
robosuite/scripts/setup_macros.py
robosuite/scripts/tune_camera.py
robosuite/scripts/tune_joints.py
robosuite/utils/__init__.py
robosuite/utils/binding_utils.py
robosuite/utils/buffers.py
robosuite/utils/camera_utils.py
robosuite/utils/control_utils.py
robosuite/utils/errors.py
robosuite/utils/ik_utils.py
robosuite/utils/input_utils.py
robosuite/utils/log_utils.py
robosuite/utils/mjcf_utils.py
robosuite/utils/mjmod.py
robosuite/utils/numba.py
robosuite/utils/observables.py
robosuite/utils/placement_samplers.py
robosuite/utils/robot_composition_utils.py
robosuite/utils/robot_utils.py
robosuite/utils/sim_utils.py
robosuite/utils/traj_utils.py
robosuite/utils/transform_utils.py
robosuite/utils/usd/camera.py
robosuite/utils/usd/demo.py
robosuite/utils/usd/exporter.py
robosuite/utils/usd/lights.py
robosuite/utils/usd/objects.py
robosuite/utils/usd/shapes.py
robosuite/utils/usd/utils.py
robosuite/wrappers/__init__.py
robosuite/wrappers/data_collection_wrapper.py
robosuite/wrappers/demo_sampler_wrapper.py
robosuite/wrappers/domain_randomization_wrapper.py
robosuite/wrappers/gym_wrapper.py
robosuite/wrappers/visualization_wrapper.py
robosuite/wrappers/wrapper.py
setup.py
tests/test_controllers/test_composite_controllers.py
tests/test_controllers/test_linear_interpolator.py
tests/test_controllers/test_variable_impedance.py
tests/test_environments/test_action_playback.py
tests/test_environments/test_all_environments.py
tests/test_environments/test_camera_transforms.py
tests/test_environments/test_env_determinism.py
tests/test_grippers/test_all_grippers.py
tests/test_grippers/test_jaco_threefinger.py
tests/test_grippers/test_panda_gripper.py
tests/test_grippers/test_rethink_gripper.py
tests/test_grippers/test_robotiq_140.py
tests/test_grippers/test_robotiq_85.py
tests/test_grippers/test_robotiq_threefinger.py
tests/test_renderers/test_all_renderers.py
tests/test_robots/test_all_robots.py
tests/test_robots/test_composite_robots.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `docs` | 1 | 153 KB | [`docs/_OMITTED.md`](./docs/_OMITTED.md) |
| `docs/images` | 19 | 20.0 MB | [`docs/images/_OMITTED.md`](./docs/images/_OMITTED.md) |
| `docs/images/benchmarking` | 1 | 111 KB | [`docs/images/benchmarking/_OMITTED.md`](./docs/images/benchmarking/_OMITTED.md) |
| `docs/images/models` | 30 | 61.7 MB | [`docs/images/models/_OMITTED.md`](./docs/images/models/_OMITTED.md) |
| `docs/images/renderers` | 3 | 11.7 MB | [`docs/images/renderers/_OMITTED.md`](./docs/images/renderers/_OMITTED.md) |
| `robosuite/models/assets/bases/meshes/omron_mobile_base` | 8 | 15.1 MB | [`robosuite/models/assets/bases/meshes/omron_mobile_base/_OMITTED.md`](./robosuite/models/assets/bases/meshes/omron_mobile_base/_OMITTED.md) |
| `robosuite/models/assets/bases/meshes/rethink_minimal_mount` | 4 | 1.6 MB | [`robosuite/models/assets/bases/meshes/rethink_minimal_mount/_OMITTED.md`](./robosuite/models/assets/bases/meshes/rethink_minimal_mount/_OMITTED.md) |
| `robosuite/models/assets/bases/meshes/rethink_mount` | 3 | 8.1 MB | [`robosuite/models/assets/bases/meshes/rethink_mount/_OMITTED.md`](./robosuite/models/assets/bases/meshes/rethink_mount/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/base` | 4 | 9.5 MB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/base/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/base/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/head` | 4 | 980 KB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/head/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/head/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/lower_elbow` | 2 | 1.3 MB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/lower_elbow/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/lower_elbow/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/lower_forearm` | 2 | 1.5 MB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/lower_forearm/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/lower_forearm/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/lower_shoulder` | 2 | 746 KB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/lower_shoulder/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/lower_shoulder/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/torso` | 4 | 9.2 MB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/torso/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/torso/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/upper_elbow` | 2 | 1.5 MB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/upper_elbow/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/upper_elbow/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/upper_forearm` | 2 | 3.0 MB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/upper_forearm/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/upper_forearm/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/upper_shoulder` | 2 | 4.3 MB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/upper_shoulder/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/upper_shoulder/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/baxter_description/meshes/wrist` | 2 | 1.4 MB | [`robosuite/models/assets/bullet_data/baxter_description/meshes/wrist/_OMITTED.md`](./robosuite/models/assets/bullet_data/baxter_description/meshes/wrist/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/panda_description/meshes/collision` | 10 | 115 KB | [`robosuite/models/assets/bullet_data/panda_description/meshes/collision/_OMITTED.md`](./robosuite/models/assets/bullet_data/panda_description/meshes/collision/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/panda_description/meshes/visual` | 10 | 10.0 MB | [`robosuite/models/assets/bullet_data/panda_description/meshes/visual/_OMITTED.md`](./robosuite/models/assets/bullet_data/panda_description/meshes/visual/_OMITTED.md) |
| `robosuite/models/assets/bullet_data/sawyer_description/meshes` | 16 | 17.1 MB | [`robosuite/models/assets/bullet_data/sawyer_description/meshes/_OMITTED.md`](./robosuite/models/assets/bullet_data/sawyer_description/meshes/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/bd_gripper` | 14 | 2.0 MB | [`robosuite/models/assets/grippers/meshes/bd_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/bd_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/fourier_hands` | 24 | 4.9 MB | [`robosuite/models/assets/grippers/meshes/fourier_hands/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/fourier_hands/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/inspire_hands` | 26 | 10.6 MB | [`robosuite/models/assets/grippers/meshes/inspire_hands/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/inspire_hands/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/jaco_three_finger_gripper` | 12 | 7.3 MB | [`robosuite/models/assets/grippers/meshes/jaco_three_finger_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/jaco_three_finger_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/panda_gripper` | 9 | 1.7 MB | [`robosuite/models/assets/grippers/meshes/panda_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/panda_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/rethink_gripper` | 8 | 7.9 MB | [`robosuite/models/assets/grippers/meshes/rethink_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/rethink_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/robotiq_140_gripper` | 18 | 4.0 MB | [`robosuite/models/assets/grippers/meshes/robotiq_140_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/robotiq_140_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/robotiq_85_gripper` | 41 | 6.1 MB | [`robosuite/models/assets/grippers/meshes/robotiq_85_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/robotiq_85_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/robotiq_s_gripper` | 15 | 2.1 MB | [`robosuite/models/assets/grippers/meshes/robotiq_s_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/robotiq_s_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/meshes/xarm7_gripper` | 16 | 4.3 MB | [`robosuite/models/assets/grippers/meshes/xarm7_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/meshes/xarm7_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/obj_meshes/rethink_gripper` | 2 | 2.9 MB | [`robosuite/models/assets/grippers/obj_meshes/rethink_gripper/_OMITTED.md`](./robosuite/models/assets/grippers/obj_meshes/rethink_gripper/_OMITTED.md) |
| `robosuite/models/assets/grippers/obj_meshes/rethink_gripper/connector_plate` | 1 | 7.0 MB | [`robosuite/models/assets/grippers/obj_meshes/rethink_gripper/connector_plate/_OMITTED.md`](./robosuite/models/assets/grippers/obj_meshes/rethink_gripper/connector_plate/_OMITTED.md) |
| `robosuite/models/assets/grippers/obj_meshes/rethink_gripper/electric_gripper_base` | 2 | 2.8 MB | [`robosuite/models/assets/grippers/obj_meshes/rethink_gripper/electric_gripper_base/_OMITTED.md`](./robosuite/models/assets/grippers/obj_meshes/rethink_gripper/electric_gripper_base/_OMITTED.md) |
| `robosuite/models/assets/objects/meshes` | 17 | 380 KB | [`robosuite/models/assets/objects/meshes/_OMITTED.md`](./robosuite/models/assets/objects/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/head` | 2 | 753 KB | [`robosuite/models/assets/robots/baxter/obj_meshes/head/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/head/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/head/H0` | 1 | 552 KB | [`robosuite/models/assets/robots/baxter/obj_meshes/head/H0/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/head/H0/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/head/H1` | 2 | 410 KB | [`robosuite/models/assets/robots/baxter/obj_meshes/head/H1/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/head/H1/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/lower_elbow` | 1 | 1.1 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/lower_elbow/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/lower_elbow/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/lower_elbow/E1` | 2 | 1.4 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/lower_elbow/E1/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/lower_elbow/E1/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/lower_forearm` | 1 | 1.3 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/lower_forearm/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/lower_forearm/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/lower_forearm/W1` | 2 | 1.6 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/lower_forearm/W1/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/lower_forearm/W1/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/lower_shoulder` | 1 | 590 KB | [`robosuite/models/assets/robots/baxter/obj_meshes/lower_shoulder/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/lower_shoulder/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/lower_shoulder/S1` | 1 | 752 KB | [`robosuite/models/assets/robots/baxter/obj_meshes/lower_shoulder/S1/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/lower_shoulder/S1/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/torso` | 3 | 8.9 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/torso/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/torso/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/torso/base_link` | 6 | 9.8 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/torso/base_link/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/torso/base_link/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/torso/base_link_collision` | 1 | 2.3 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/torso/base_link_collision/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/torso/base_link_collision/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/upper_elbow` | 1 | 1.2 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/upper_elbow/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/upper_elbow/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/upper_elbow/E0` | 2 | 1.6 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/upper_elbow/E0/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/upper_elbow/E0/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/upper_forearm` | 1 | 2.8 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/upper_forearm/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/upper_forearm/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/upper_forearm/W0` | 4 | 3.5 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/upper_forearm/W0/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/upper_forearm/W0/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/upper_shoulder` | 1 | 3.6 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/upper_shoulder/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/upper_shoulder/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/upper_shoulder/S0` | 2 | 4.7 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/upper_shoulder/S0/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/upper_shoulder/S0/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/wrist` | 1 | 1.1 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/wrist/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/wrist/_OMITTED.md) |
| `robosuite/models/assets/robots/baxter/obj_meshes/wrist/W2` | 3 | 3.8 MB | [`robosuite/models/assets/robots/baxter/obj_meshes/wrist/W2/_OMITTED.md`](./robosuite/models/assets/robots/baxter/obj_meshes/wrist/W2/_OMITTED.md) |
| `robosuite/models/assets/robots/gr1/meshes` | 34 | 20.8 MB | [`robosuite/models/assets/robots/gr1/meshes/_OMITTED.md`](./robosuite/models/assets/robots/gr1/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/iiwa/meshes` | 32 | 33.4 MB | [`robosuite/models/assets/robots/iiwa/meshes/_OMITTED.md`](./robosuite/models/assets/robots/iiwa/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/jaco/meshes` | 18 | 9.6 MB | [`robosuite/models/assets/robots/jaco/meshes/_OMITTED.md`](./robosuite/models/assets/robots/jaco/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/kinova3/meshes` | 20 | 17.3 MB | [`robosuite/models/assets/robots/kinova3/meshes/_OMITTED.md`](./robosuite/models/assets/robots/kinova3/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/meshes` | 10 | 711 KB | [`robosuite/models/assets/robots/panda/meshes/_OMITTED.md`](./robosuite/models/assets/robots/panda/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/obj_meshes/link0_vis` | 12 | 5.7 MB | [`robosuite/models/assets/robots/panda/obj_meshes/link0_vis/_OMITTED.md`](./robosuite/models/assets/robots/panda/obj_meshes/link0_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/obj_meshes/link1_vis` | 1 | 3.6 MB | [`robosuite/models/assets/robots/panda/obj_meshes/link1_vis/_OMITTED.md`](./robosuite/models/assets/robots/panda/obj_meshes/link1_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/obj_meshes/link2_vis` | 1 | 3.6 MB | [`robosuite/models/assets/robots/panda/obj_meshes/link2_vis/_OMITTED.md`](./robosuite/models/assets/robots/panda/obj_meshes/link2_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/obj_meshes/link3_vis` | 4 | 4.2 MB | [`robosuite/models/assets/robots/panda/obj_meshes/link3_vis/_OMITTED.md`](./robosuite/models/assets/robots/panda/obj_meshes/link3_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/obj_meshes/link4_vis` | 4 | 4.3 MB | [`robosuite/models/assets/robots/panda/obj_meshes/link4_vis/_OMITTED.md`](./robosuite/models/assets/robots/panda/obj_meshes/link4_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/obj_meshes/link5_vis` | 3 | 5.4 MB | [`robosuite/models/assets/robots/panda/obj_meshes/link5_vis/_OMITTED.md`](./robosuite/models/assets/robots/panda/obj_meshes/link5_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/obj_meshes/link6_vis` | 17 | 6.3 MB | [`robosuite/models/assets/robots/panda/obj_meshes/link6_vis/_OMITTED.md`](./robosuite/models/assets/robots/panda/obj_meshes/link6_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/panda/obj_meshes/link7_vis` | 8 | 4.0 MB | [`robosuite/models/assets/robots/panda/obj_meshes/link7_vis/_OMITTED.md`](./robosuite/models/assets/robots/panda/obj_meshes/link7_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes` | 9 | 24.1 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/base` | 2 | 1.9 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/base/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/base/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/head` | 10 | 2.7 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/head/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/head/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/l0` | 7 | 7.1 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/l0/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/l0/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/l1` | 3 | 907 KB | [`robosuite/models/assets/robots/sawyer/obj_meshes/l1/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/l1/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/l2` | 5 | 1.2 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/l2/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/l2/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/l3` | 4 | 1.2 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/l3/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/l3/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/l4` | 8 | 9.2 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/l4/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/l4/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/l5` | 5 | 3.8 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/l5/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/l5/_OMITTED.md) |
| `robosuite/models/assets/robots/sawyer/obj_meshes/l6` | 6 | 3.9 MB | [`robosuite/models/assets/robots/sawyer/obj_meshes/l6/_OMITTED.md`](./robosuite/models/assets/robots/sawyer/obj_meshes/l6/_OMITTED.md) |
| `robosuite/models/assets/robots/spot/meshes` | 32 | 43.6 MB | [`robosuite/models/assets/robots/spot/meshes/_OMITTED.md`](./robosuite/models/assets/robots/spot/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/spot_arm/meshes` | 17 | 6.9 MB | [`robosuite/models/assets/robots/spot_arm/meshes/_OMITTED.md`](./robosuite/models/assets/robots/spot_arm/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/tiago/meshes/arm` | 9 | 2.4 MB | [`robosuite/models/assets/robots/tiago/meshes/arm/_OMITTED.md`](./robosuite/models/assets/robots/tiago/meshes/arm/_OMITTED.md) |
| `robosuite/models/assets/robots/tiago/meshes/base` | 6 | 3.3 MB | [`robosuite/models/assets/robots/tiago/meshes/base/_OMITTED.md`](./robosuite/models/assets/robots/tiago/meshes/base/_OMITTED.md) |
| `robosuite/models/assets/robots/tiago/meshes/base/high_resolution` | 2 | 2.7 MB | [`robosuite/models/assets/robots/tiago/meshes/base/high_resolution/_OMITTED.md`](./robosuite/models/assets/robots/tiago/meshes/base/high_resolution/_OMITTED.md) |
| `robosuite/models/assets/robots/tiago/meshes/grippers` | 11 | 667 KB | [`robosuite/models/assets/robots/tiago/meshes/grippers/_OMITTED.md`](./robosuite/models/assets/robots/tiago/meshes/grippers/_OMITTED.md) |
| `robosuite/models/assets/robots/tiago/meshes/head` | 2 | 220 KB | [`robosuite/models/assets/robots/tiago/meshes/head/_OMITTED.md`](./robosuite/models/assets/robots/tiago/meshes/head/_OMITTED.md) |
| `robosuite/models/assets/robots/tiago/meshes/torso` | 7 | 1.6 MB | [`robosuite/models/assets/robots/tiago/meshes/torso/_OMITTED.md`](./robosuite/models/assets/robots/tiago/meshes/torso/_OMITTED.md) |
| `robosuite/models/assets/robots/tiago/meshes/wheels` | 8 | 949 KB | [`robosuite/models/assets/robots/tiago/meshes/wheels/_OMITTED.md`](./robosuite/models/assets/robots/tiago/meshes/wheels/_OMITTED.md) |
| `robosuite/models/assets/robots/tiago/meshes/wheels/high_resolution` | 3 | 1.0 MB | [`robosuite/models/assets/robots/tiago/meshes/wheels/high_resolution/_OMITTED.md`](./robosuite/models/assets/robots/tiago/meshes/wheels/high_resolution/_OMITTED.md) |
| `robosuite/models/assets/robots/ur5e/meshes` | 30 | 32.1 MB | [`robosuite/models/assets/robots/ur5e/meshes/_OMITTED.md`](./robosuite/models/assets/robots/ur5e/meshes/_OMITTED.md) |
| `robosuite/models/assets/robots/ur5e/obj_meshes/base_vis` | 2 | 1.2 MB | [`robosuite/models/assets/robots/ur5e/obj_meshes/base_vis/_OMITTED.md`](./robosuite/models/assets/robots/ur5e/obj_meshes/base_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/ur5e/obj_meshes/forearm_vis` | 4 | 3.7 MB | [`robosuite/models/assets/robots/ur5e/obj_meshes/forearm_vis/_OMITTED.md`](./robosuite/models/assets/robots/ur5e/obj_meshes/forearm_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/ur5e/obj_meshes/shoulder_vis` | 3 | 5.8 MB | [`robosuite/models/assets/robots/ur5e/obj_meshes/shoulder_vis/_OMITTED.md`](./robosuite/models/assets/robots/ur5e/obj_meshes/shoulder_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/ur5e/obj_meshes/upperarm_vis` | 4 | 10.1 MB | [`robosuite/models/assets/robots/ur5e/obj_meshes/upperarm_vis/_OMITTED.md`](./robosuite/models/assets/robots/ur5e/obj_meshes/upperarm_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/ur5e/obj_meshes/wrist1_vis` | 3 | 4.3 MB | [`robosuite/models/assets/robots/ur5e/obj_meshes/wrist1_vis/_OMITTED.md`](./robosuite/models/assets/robots/ur5e/obj_meshes/wrist1_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/ur5e/obj_meshes/wrist2_vis` | 3 | 5.0 MB | [`robosuite/models/assets/robots/ur5e/obj_meshes/wrist2_vis/_OMITTED.md`](./robosuite/models/assets/robots/ur5e/obj_meshes/wrist2_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/ur5e/obj_meshes/wrist3_vis` | 1 | 212 KB | [`robosuite/models/assets/robots/ur5e/obj_meshes/wrist3_vis/_OMITTED.md`](./robosuite/models/assets/robots/ur5e/obj_meshes/wrist3_vis/_OMITTED.md) |
| `robosuite/models/assets/robots/xarm7/assets` | 16 | 4.3 MB | [`robosuite/models/assets/robots/xarm7/assets/_OMITTED.md`](./robosuite/models/assets/robots/xarm7/assets/_OMITTED.md) |
| `robosuite/models/assets/robots/xarm7/meshes` | 16 | 4.3 MB | [`robosuite/models/assets/robots/xarm7/meshes/_OMITTED.md`](./robosuite/models/assets/robots/xarm7/meshes/_OMITTED.md) |
| `robosuite/models/assets/textures` | 30 | 19.7 MB | [`robosuite/models/assets/textures/_OMITTED.md`](./robosuite/models/assets/textures/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
