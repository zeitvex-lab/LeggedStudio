# genesis-world — 参考资源

> **来源**：`00_open/genesis-world/`　｜　**类型**：仿真平台参考（多物理 / 渲染 / 传感器）
> **关联机型**：（无，通用）
> **定位**：Genesis World：Python 原生多物理仿真平台（统一多物理引擎 + Nyx 渲染 + Quadrants 编译）；URDF / MJCF / OBJ / GLB / USD 资产解析、并行与异构环境、相机与传感器、可微物理——第三物理引擎候选，与传感器/场景/可微训练参考
> **收录**：708 个文件 / 12.2 MB（其中推理策略/模型文件 0 个）
> **已省略**：348 个文件 / 206.6 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（179 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（14 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（14 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（2 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（8 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（7 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（68 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（416 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （12 个文件）
.github/  （22 个文件）
    (直接文件)/
    ISSUE_TEMPLATE/
    contributing/
    workflows/
examples/  （125 个文件）
    collision/
    coupling/
    deformable/
    drone/
    fluid/
    gui/
    ipc/
    kinematic/
    locomotion/
    manipulation/
    rendering/
    rigid/
    sap_coupling/
    sensors/
    speed_benchmark/
    tutorials/
    usd/
    viewer_plugin/
genesis/  （459 个文件）
    (直接文件)/
    assets/
    engine/
    ext/
    grad/
    logging/
    options/
    recorders/
    utils/
    vis/
tests/  （90 个文件）
    (直接文件)/
    benchmarks/
    core/
    coupling/
    deformable/
    grad/
    integration/
    ipc/
    parsers/
    particles/
    rendering/
    rigid/
    sensors/
    utils/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 475 |
| `.xml` | 59 |
| `.mtl` | 36 |
| `.urdf` | 34 |
| `.txt` | 21 |
| `.md` | 18 |
| `(无扩展名)` | 10 |
| `.yml` | 10 |
| `.frag` | 9 |
| `.vert` | 9 |
| `.json` | 6 |
| `.geom` | 6 |
| `.sdf` | 5 |
| `.html` | 3 |
| `.yaml` | 2 |

## 文件索引（项目内相对路径）

```text
.gitattributes
.github/CODEOWNERS
.github/ISSUE_TEMPLATE/1-bug-report.yml
.github/ISSUE_TEMPLATE/2-feature-request.yml
.github/ISSUE_TEMPLATE/3-documentation.yml
.github/ISSUE_TEMPLATE/config.yml
.github/contributing/ARCHITECTURE.md
.github/contributing/CODING_CONVENTIONS.md
.github/contributing/EXAMPLES.md
.github/contributing/PULL_REQUESTS.md
.github/contributing/TESTING.md
.github/contributing/USD_PARSER.md
.github/genesis_image_ver
.github/nyx_plugin_commit
.github/pull_request_template.md
.github/workflows/alarm.yml
.github/workflows/examples.yml
.github/workflows/format.yml
.github/workflows/generic.yml
.github/workflows/nyx_plugin.yml
.github/workflows/production.yml
.github/workflows/scripts/alarm.py
.github/workflows/scripts/production_build.sh
.gitignore
.gitmodules
.pre-commit-config.yaml
.readthedocs.yaml
CLAUDE.md
CODING_GUIDELINES.md
LICENSE
MANIFEST.in
README.md
RELEASE.md
examples/collision/contact_manifold.py
examples/collision/contype.py
examples/collision/pyramid.py
examples/collision/tower.py
examples/coupling/cloth_attached_to_rigid.py
examples/coupling/cloth_on_rigid.py
examples/coupling/cut_dragon.py
examples/coupling/fem_cube_linked_with_arm.py
examples/coupling/flush_cubes.py
examples/coupling/grasp_soft_cube.py
examples/coupling/rigid_mpm_attachment.py
examples/coupling/sand_wheel.py
examples/coupling/sph_mpm.py
examples/coupling/sph_rigid.py
examples/coupling/water_wheel.py
examples/deformable/differentiable_push.py
examples/deformable/elastic_dragon.py
examples/deformable/fem_hard_and_soft_constraint.py
examples/deformable/pbd_liquid.py
examples/drone/README.md
examples/drone/fly.py
examples/drone/fly_route.py
examples/drone/hover_env.py
examples/drone/hover_eval.py
examples/drone/hover_train.py
examples/drone/interactive_drone.py
examples/drone/quadcopter_controller.py
examples/fluid/smoke.py
examples/gui/imgui_joint_control.py
examples/ipc/README.md
examples/ipc/ipc_momentum.py
examples/ipc/ipc_objects_falling.py
examples/ipc/ipc_robot_cloth_teleop.py
examples/ipc/ipc_robot_grasp_cube.py
examples/kinematic/go2_kinematic.py
examples/locomotion/backflip/readme.md
examples/locomotion/go2_backflip.py
examples/locomotion/go2_env.py
examples/locomotion/go2_eval.py
examples/locomotion/go2_train.py
examples/manipulation/behavior_cloning.py
examples/manipulation/grasp_env.py
examples/manipulation/grasp_eval.py
examples/manipulation/grasp_train.py
examples/rendering/demo.py
examples/rendering/follow_entity.py
examples/rendering/moving_camera.py
examples/rendering/render_async.py
examples/rendering/speed_test.py
examples/rigid/accelerometer_duck.py
examples/rigid/accelerometer_franka.py
examples/rigid/apply_external_wrench.py
examples/rigid/authored_decomp.py
examples/rigid/bolt_nut_self_screw.py
examples/rigid/closed_loop.py
examples/rigid/control_franka.py
examples/rigid/control_mesh.py
examples/rigid/convex_decomposition.py
examples/rigid/ddp_multi_gpu.py
examples/rigid/diffik_controller.py
examples/rigid/domain_randomization.py
examples/rigid/franka_cube.py
examples/rigid/friction_breakaway.py
examples/rigid/grasp_bottle.py
examples/rigid/gravity_compensation.py
examples/rigid/heterogeneous_simulation.py
examples/rigid/hibernation.py
examples/rigid/ik_custom_chain.py
examples/rigid/ik_duck.py
examples/rigid/ik_franka.py
examples/rigid/ik_franka_batched.py
examples/rigid/ik_shadow_hand.py
examples/rigid/merge_entities.py
examples/rigid/multi_gpu.py
examples/rigid/nonconvex_mesh.py
examples/rigid/rolling_coast.py
examples/rigid/set_phys_attr.py
examples/rigid/single_franka.py
examples/rigid/single_franka_batch_render.py
examples/rigid/single_franka_envs.py
examples/rigid/suction_cup.py
examples/rigid/terrain_from_mesh.py
examples/rigid/terrain_height_field.py
examples/rigid/terrain_subterrain.py
examples/rigid/torsional_grasp.py
examples/sap_coupling/fem_fixed_constraint.py
examples/sap_coupling/fem_sphere_and_cube.py
examples/sap_coupling/franka_grasp_fem_sphere.py
examples/sap_coupling/franka_grasp_rigid_cube.py
examples/sensors/camera_as_sensor.py
examples/sensors/contact_force_go2.py
examples/sensors/depth_camera_custom_vverts.py
examples/sensors/imu_franka.py
examples/sensors/joint_torque_franka.py
examples/sensors/lidar_teleop.py
examples/sensors/surface_distance_shadowhand.py
examples/sensors/tactile_franka.py
examples/sensors/tactile_sandbox.py
examples/sensors/temperature_grid.py
examples/speed_benchmark/anymal_c.py
examples/speed_benchmark/franka.py
examples/speed_benchmark/timers.py
examples/tutorials/IK_motion_planning_grasp.py
examples/tutorials/advanced_IK_multilink.py
examples/tutorials/advanced_hybrid_robot.py
examples/tutorials/advanced_muscle.py
examples/tutorials/advanced_worm.py
examples/tutorials/batched_IK.py
examples/tutorials/control_your_robot.py
examples/tutorials/draw_debug.py
examples/tutorials/entity_name.py
examples/tutorials/hello_genesis.py
examples/tutorials/interactive_debugging.py
examples/tutorials/mpm.py
examples/tutorials/parallel_simulation.py
examples/tutorials/pbd_cloth.py
examples/tutorials/position_control_comparison.py
examples/tutorials/selecting_rendered_envs.py
examples/tutorials/sph_liquid.py
examples/tutorials/visualization.py
examples/usd/import_stage.py
examples/usd/kitchen.py
examples/viewer_plugin/keyboard_teleop.py
examples/viewer_plugin/mesh_point_selector.py
examples/viewer_plugin/mouse_interaction.py
genesis/__init__.py
genesis/_main.py
genesis/assets/meshes/Airplane/airplane.mtl
genesis/assets/meshes/bathtub/material.mtl
genesis/assets/meshes/boat/material.mtl
genesis/assets/meshes/bolt_nut/generate_bolt_nut.py
genesis/assets/meshes/dragon/material.mtl
genesis/assets/meshes/duck/material.mtl
genesis/assets/meshes/env_sphere/material.mtl
genesis/assets/meshes/wooden_sphere_OBJ/wooden_sphere.mtl
genesis/assets/meshes/worm/worm.mtl
genesis/assets/tower/ball.urdf
genesis/assets/tower/base_pole.urdf
genesis/assets/tower/generate_tower.py
genesis/assets/tower/ring_01.urdf
genesis/assets/tower/ring_02.urdf
genesis/assets/tower/ring_03.urdf
genesis/assets/tower/ring_04.urdf
genesis/assets/tower/ring_05.urdf
genesis/assets/tower/ring_06.urdf
genesis/assets/urdf/3763/bounding_box.json
genesis/assets/urdf/3763/link_and_joint.txt
genesis/assets/urdf/3763/meta.json
genesis/assets/urdf/3763/mobility.urdf
genesis/assets/urdf/3763/mobility_v2.json
genesis/assets/urdf/3763/mobility_vhacd.urdf
genesis/assets/urdf/3763/parts_render/0.txt
genesis/assets/urdf/3763/parts_render/1.txt
genesis/assets/urdf/3763/parts_render/5.txt
genesis/assets/urdf/3763/parts_render/6.txt
genesis/assets/urdf/3763/parts_render/7.txt
genesis/assets/urdf/3763/parts_render_after_merging/0.txt
genesis/assets/urdf/3763/parts_render_after_merging/1.txt
genesis/assets/urdf/3763/parts_render_after_merging/2.txt
genesis/assets/urdf/3763/parts_render_after_merging/3.txt
genesis/assets/urdf/3763/parts_render_after_merging/4.txt
genesis/assets/urdf/3763/point_sample/label-10000.txt
genesis/assets/urdf/3763/point_sample/pts-10000.pts
genesis/assets/urdf/3763/point_sample/pts-10000.txt
genesis/assets/urdf/3763/point_sample/sample-points-all-label-10000.txt
genesis/assets/urdf/3763/point_sample/sample-points-all-pts-nor-rgba-10000.txt
genesis/assets/urdf/3763/result.json
genesis/assets/urdf/3763/result_after_merging.json
genesis/assets/urdf/3763/semantics.txt
genesis/assets/urdf/3763/textured_objs/original-1.mtl
genesis/assets/urdf/3763/textured_objs/original-1_log.txt
genesis/assets/urdf/3763/textured_objs/original-2.mtl
genesis/assets/urdf/3763/textured_objs/original-2_log.txt
genesis/assets/urdf/3763/textured_objs/original-3.mtl
genesis/assets/urdf/3763/textured_objs/original-3_log.txt
genesis/assets/urdf/3763/tree_hier.html
genesis/assets/urdf/3763/tree_hier_after_merging.html
genesis/assets/urdf/anymal_c/ANYmal_c_license.txt
genesis/assets/urdf/anymal_c/urdf/anymal_c.urdf
genesis/assets/urdf/blue_box/assets/part_1.part
genesis/assets/urdf/blue_box/model.urdf
genesis/assets/urdf/drones/body.mtl
genesis/assets/urdf/drones/cf2p.urdf
genesis/assets/urdf/drones/cf2x.urdf
genesis/assets/urdf/drones/propeller0.mtl
genesis/assets/urdf/drones/propeller1.mtl
genesis/assets/urdf/drones/propeller2.mtl
genesis/assets/urdf/drones/propeller3.mtl
genesis/assets/urdf/drones/racer.urdf
genesis/assets/urdf/go2/urdf/go2.urdf
genesis/assets/urdf/kuka_iiwa/kuka_with_gripper.sdf
genesis/assets/urdf/kuka_iiwa/kuka_with_gripper2.sdf
genesis/assets/urdf/kuka_iiwa/kuka_world.sdf
genesis/assets/urdf/kuka_iiwa/meshes/link_0.mtl
genesis/assets/urdf/kuka_iiwa/meshes/link_1.mtl
genesis/assets/urdf/kuka_iiwa/meshes/link_2.mtl
genesis/assets/urdf/kuka_iiwa/meshes/link_3.mtl
genesis/assets/urdf/kuka_iiwa/meshes/link_4.mtl
genesis/assets/urdf/kuka_iiwa/meshes/link_5.mtl
genesis/assets/urdf/kuka_iiwa/meshes/link_6.mtl
genesis/assets/urdf/kuka_iiwa/meshes/link_7.mtl
genesis/assets/urdf/kuka_iiwa/model.sdf
genesis/assets/urdf/kuka_iiwa/model.urdf
genesis/assets/urdf/kuka_iiwa/model2.sdf
genesis/assets/urdf/kuka_iiwa/model_for_sdf.urdf
genesis/assets/urdf/kuka_iiwa/model_free_base.urdf
genesis/assets/urdf/kuka_iiwa/model_mobile.urdf
genesis/assets/urdf/kuka_iiwa/model_vr_limits.urdf
genesis/assets/urdf/panda_bullet/LICENSE.txt
genesis/assets/urdf/panda_bullet/hand.urdf
genesis/assets/urdf/panda_bullet/meshes/collision/link6.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/finger.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/hand.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/link1.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/link2.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/link3.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/link4.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/link5.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/link6.mtl
genesis/assets/urdf/panda_bullet/meshes/visual/visualShapeBench.json_0.json
genesis/assets/urdf/panda_bullet/panda.urdf
genesis/assets/urdf/panda_bullet/panda_nohand.urdf
genesis/assets/urdf/panda_bullet/panda_slider_mobile.urdf
genesis/assets/urdf/panda_bullet/panda_suction.urdf
genesis/assets/urdf/plane/generate_checker.py
genesis/assets/urdf/plane/plane.mtl
genesis/assets/urdf/plane/plane.urdf
genesis/assets/urdf/plane/plane_light.mtl
genesis/assets/urdf/plane/plane_light.urdf
genesis/assets/urdf/shadow_hand/shadow_hand.urdf
genesis/assets/urdf/simple/two_cube_prismatic.urdf
genesis/assets/urdf/simple/two_cube_revolute.urdf
genesis/assets/urdf/simple/two_link_arm.urdf
genesis/assets/urdf/wheel/fancy_wheel.urdf
genesis/assets/urdf/wheel/material.mtl
genesis/assets/urdf/wheel/wheel.urdf
genesis/assets/xml/ant.xml
genesis/assets/xml/ant_grasp_ball.xml
genesis/assets/xml/ant_grasp_body.xml
genesis/assets/xml/ant_grasp_ground.xml
genesis/assets/xml/cable.xml
genesis/assets/xml/dominos.xml
genesis/assets/xml/four_bar_linkage.xml
genesis/assets/xml/four_bar_linkage_weld.xml
genesis/assets/xml/franka_emika_panda/README.md
genesis/assets/xml/franka_emika_panda/hand.xml
genesis/assets/xml/franka_emika_panda/panda.xml
genesis/assets/xml/franka_emika_panda/panda_free_base.xml
genesis/assets/xml/franka_emika_panda/panda_no_tendon.xml
genesis/assets/xml/franka_emika_panda/panda_nohand.xml
genesis/assets/xml/franka_emika_panda/panda_non_overlap.xml
genesis/assets/xml/franka_emika_panda/scene.xml
genesis/assets/xml/franka_emika_panda/scene_no_tendon.xml
genesis/assets/xml/franka_sim/LICENSE
genesis/assets/xml/franka_sim/README.md
genesis/assets/xml/franka_sim/assets/actuator0.xml
genesis/assets/xml/franka_sim/assets/actuator0_0.xml
genesis/assets/xml/franka_sim/assets/actuator0_2.xml
genesis/assets/xml/franka_sim/assets/actuator1.xml
genesis/assets/xml/franka_sim/assets/assets.xml
genesis/assets/xml/franka_sim/assets/assets_0.xml
genesis/assets/xml/franka_sim/assets/assets_2.xml
genesis/assets/xml/franka_sim/assets/basic_scene.xml
genesis/assets/xml/franka_sim/assets/chain0.xml
genesis/assets/xml/franka_sim/assets/chain0_nogripper.xml
genesis/assets/xml/franka_sim/assets/chain0_overlay.xml
genesis/assets/xml/franka_sim/assets/chain1.xml
genesis/assets/xml/franka_sim/assets/gripper_actuator0.xml
genesis/assets/xml/franka_sim/assets/gripper_assets.xml
genesis/assets/xml/franka_sim/assets/teleop_actuator.xml
genesis/assets/xml/franka_sim/ball.xml
genesis/assets/xml/franka_sim/bi-franka_panda.xml
genesis/assets/xml/franka_sim/franka_panda.xml
genesis/assets/xml/franka_sim/franka_panda_0.xml
genesis/assets/xml/franka_sim/franka_panda_1.xml
genesis/assets/xml/franka_sim/franka_panda_2.xml
genesis/assets/xml/franka_sim/franka_panda_3.xml
genesis/assets/xml/franka_sim/franka_panda_ball.xml
genesis/assets/xml/franka_sim/franka_panda_ball_.xml
genesis/assets/xml/franka_sim/franka_panda_no_finger.xml
genesis/assets/xml/franka_sim/franka_panda_teleop.xml
genesis/assets/xml/franka_sim/franka_panda_test_convex.xml
genesis/assets/xml/humanoid.xml
genesis/assets/xml/one_ball_joint.xml
genesis/assets/xml/one_tet.xml
genesis/assets/xml/rope_ball.xml
genesis/assets/xml/rope_hinge.xml
genesis/assets/xml/tet_ball.xml
genesis/assets/xml/tet_capsule.xml
genesis/assets/xml/tet_tet.xml
genesis/assets/xml/thin_box.xml
genesis/assets/xml/thin_box_mesh.xml
genesis/assets/xml/three_joint_link.xml
genesis/assets/xml/two_box.xml
genesis/assets/xml/two_skeleton.xml
genesis/assets/xml/universal_robots_ur5e/LICENSE
genesis/assets/xml/universal_robots_ur5e/README.md
genesis/assets/xml/universal_robots_ur5e/scene.xml
genesis/assets/xml/universal_robots_ur5e/ur5e.xml
genesis/assets/xml/walker.xml
genesis/constants.py
genesis/datatypes.py
genesis/engine/__init__.py
genesis/engine/boundaries/__init__.py
genesis/engine/boundaries/boundaries.py
genesis/engine/bvh.py
genesis/engine/couplers/__init__.py
genesis/engine/couplers/ipc_coupler/__init__.py
genesis/engine/couplers/ipc_coupler/coupler.py
genesis/engine/couplers/ipc_coupler/data.py
genesis/engine/couplers/ipc_coupler/utils.py
genesis/engine/couplers/legacy_coupler.py
genesis/engine/couplers/sap_coupler.py
genesis/engine/entities/__init__.py
genesis/engine/entities/base_entity.py
genesis/engine/entities/emitter.py
genesis/engine/entities/fem_entity.py
genesis/engine/entities/hybrid_entity.py
genesis/engine/entities/mpm_entity.py
genesis/engine/entities/particle_entity.py
genesis/engine/entities/pbd_entity.py
genesis/engine/entities/rigid_entity/__init__.py
genesis/engine/entities/rigid_entity/description.py
genesis/engine/entities/rigid_entity/drone_entity.py
genesis/engine/entities/rigid_entity/inertial.py
genesis/engine/entities/rigid_entity/rigid_entity.py
genesis/engine/entities/rigid_entity/rigid_equality.py
genesis/engine/entities/rigid_entity/rigid_geom.py
genesis/engine/entities/rigid_entity/rigid_joint.py
genesis/engine/entities/rigid_entity/rigid_link.py
genesis/engine/entities/rigid_entity/terrain_entity.py
genesis/engine/entities/sf_entity.py
genesis/engine/entities/sph_entity.py
genesis/engine/entities/tool_entity/__init__.py
genesis/engine/entities/tool_entity/mesh.py
genesis/engine/entities/tool_entity/tool_entity.py
genesis/engine/force_fields.py
genesis/engine/interactive_scene.py
genesis/engine/materials/FEM/__init__.py
genesis/engine/materials/FEM/base.py
genesis/engine/materials/FEM/cloth.py
genesis/engine/materials/FEM/elastic.py
genesis/engine/materials/FEM/muscle.py
genesis/engine/materials/MPM/__init__.py
genesis/engine/materials/MPM/base.py
genesis/engine/materials/MPM/elastic.py
genesis/engine/materials/MPM/elasto_plastic.py
genesis/engine/materials/MPM/liquid.py
genesis/engine/materials/MPM/muscle.py
genesis/engine/materials/MPM/sand.py
genesis/engine/materials/MPM/snow.py
genesis/engine/materials/PBD/__init__.py
genesis/engine/materials/PBD/base.py
genesis/engine/materials/PBD/cloth.py
genesis/engine/materials/PBD/elastic.py
genesis/engine/materials/PBD/liquid.py
genesis/engine/materials/PBD/particle.py
genesis/engine/materials/SF/__init__.py
genesis/engine/materials/SF/base.py
genesis/engine/materials/SF/smoke.py
genesis/engine/materials/SPH/__init__.py
genesis/engine/materials/SPH/base.py
genesis/engine/materials/SPH/liquid.py
genesis/engine/materials/__init__.py
genesis/engine/materials/base.py
genesis/engine/materials/hybrid.py
genesis/engine/materials/kinematic.py
genesis/engine/materials/rigid.py
genesis/engine/materials/tool.py
genesis/engine/mesh.py
genesis/engine/scene.py
genesis/engine/sensors/__init__.py
genesis/engine/sensors/base_sensor.py
genesis/engine/sensors/camera.py
genesis/engine/sensors/contact_force.py
genesis/engine/sensors/depth_camera.py
genesis/engine/sensors/imu.py
genesis/engine/sensors/joint_torque.py
genesis/engine/sensors/kinematic_tactile.py
genesis/engine/sensors/point_cloud_tactile.py
genesis/engine/sensors/probe.py
genesis/engine/sensors/raycaster.py
genesis/engine/sensors/sensor_manager.py
genesis/engine/sensors/surface_distance_probe.py
genesis/engine/sensors/tactile_shared.py
genesis/engine/sensors/temperature.py
genesis/engine/simulator.py
genesis/engine/solvers/__init__.py
genesis/engine/solvers/base_solver.py
genesis/engine/solvers/fem_solver.py
genesis/engine/solvers/kinematic_solver.py
genesis/engine/solvers/mpm_solver.py
genesis/engine/solvers/pbd_solver.py
genesis/engine/solvers/rigid/__init__.py
genesis/engine/solvers/rigid/abd/__init__.py
genesis/engine/solvers/rigid/abd/accessor.py
genesis/engine/solvers/rigid/abd/diff.py
genesis/engine/solvers/rigid/abd/forward_dynamics.py
genesis/engine/solvers/rigid/abd/forward_kinematics.py
genesis/engine/solvers/rigid/abd/inverse_kinematics.py
genesis/engine/solvers/rigid/abd/manual_bw.py
genesis/engine/solvers/rigid/abd/misc.py
genesis/engine/solvers/rigid/collider/__init__.py
genesis/engine/solvers/rigid/collider/box_contact.py
genesis/engine/solvers/rigid/collider/broadphase.py
genesis/engine/solvers/rigid/collider/capsule_contact.py
genesis/engine/solvers/rigid/collider/collider.py
genesis/engine/solvers/rigid/collider/constants.py
genesis/engine/solvers/rigid/collider/contact.py
genesis/engine/solvers/rigid/collider/diff_gjk.py
genesis/engine/solvers/rigid/collider/epa.py
genesis/engine/solvers/rigid/collider/gjk.py
genesis/engine/solvers/rigid/collider/gjk_support.py
genesis/engine/solvers/rigid/collider/gjk_utils.py
genesis/engine/solvers/rigid/collider/mpr.py
genesis/engine/solvers/rigid/collider/multi_contact.py
genesis/engine/solvers/rigid/collider/narrowphase.py
genesis/engine/solvers/rigid/collider/support_field.py
genesis/engine/solvers/rigid/collider/utils.py
genesis/engine/solvers/rigid/constraint/__init__.py
genesis/engine/solvers/rigid/constraint/backward.py
genesis/engine/solvers/rigid/constraint/island.py
genesis/engine/solvers/rigid/constraint/linesearch.py
genesis/engine/solvers/rigid/constraint/noslip.py
genesis/engine/solvers/rigid/constraint/solver.py
genesis/engine/solvers/rigid/constraint/solver_breakdown.py
genesis/engine/solvers/rigid/rigid_solver.py
genesis/engine/solvers/sf_solver.py
genesis/engine/solvers/sph_solver.py
genesis/engine/solvers/tool_solver.py
genesis/engine/states/__init__.py
genesis/engine/states/cache.py
genesis/engine/states/entities.py
genesis/engine/states/solvers.py
genesis/ext/VolumeSampling
genesis/ext/_trimesh_patch.py
genesis/ext/isaacgym/terrain_utils.py
genesis/ext/pyrender/__init__.py
genesis/ext/pyrender/camera.py
genesis/ext/pyrender/constants.py
genesis/ext/pyrender/font.py
genesis/ext/pyrender/jit_render.py
genesis/ext/pyrender/light.py
genesis/ext/pyrender/material.py
genesis/ext/pyrender/mesh.py
genesis/ext/pyrender/node.py
genesis/ext/pyrender/numba_gl_wrapper.py
genesis/ext/pyrender/offscreen.py
genesis/ext/pyrender/overlay/__init__.py
genesis/ext/pyrender/overlay/plugin.py
genesis/ext/pyrender/overlay/style.py
genesis/ext/pyrender/overlay/types.py
genesis/ext/pyrender/platforms/__init__.py
genesis/ext/pyrender/platforms/base.py
genesis/ext/pyrender/platforms/cgl.py
genesis/ext/pyrender/platforms/egl.py
genesis/ext/pyrender/platforms/osmesa.py
genesis/ext/pyrender/platforms/pyglet_platform.py
genesis/ext/pyrender/primitive.py
genesis/ext/pyrender/renderer.py
genesis/ext/pyrender/sampler.py
genesis/ext/pyrender/scene.py
genesis/ext/pyrender/shader_program.py
genesis/ext/pyrender/shaders/debug_quad.frag
genesis/ext/pyrender/shaders/debug_quad.vert
genesis/ext/pyrender/shaders/flat.frag
genesis/ext/pyrender/shaders/flat.vert
genesis/ext/pyrender/shaders/mesh.frag
genesis/ext/pyrender/shaders/mesh.vert
genesis/ext/pyrender/shaders/mesh_depth.frag
genesis/ext/pyrender/shaders/mesh_depth.vert
genesis/ext/pyrender/shaders/mesh_double_sided.geom
genesis/ext/pyrender/shaders/mesh_normal.frag
genesis/ext/pyrender/shaders/mesh_normal.vert
genesis/ext/pyrender/shaders/mesh_normal_double_sided.geom
genesis/ext/pyrender/shaders/point_shadow.frag
genesis/ext/pyrender/shaders/point_shadow.geom
genesis/ext/pyrender/shaders/point_shadow.vert
genesis/ext/pyrender/shaders/segmentation.frag
genesis/ext/pyrender/shaders/segmentation.vert
genesis/ext/pyrender/shaders/segmentation_double_sided.geom
genesis/ext/pyrender/shaders/text.frag
genesis/ext/pyrender/shaders/text.vert
genesis/ext/pyrender/shaders/vertex_normals.frag
genesis/ext/pyrender/shaders/vertex_normals.geom
genesis/ext/pyrender/shaders/vertex_normals.vert
genesis/ext/pyrender/shaders/vertex_normals_pc.geom
genesis/ext/pyrender/texture.py
genesis/ext/pyrender/trackball.py
genesis/ext/pyrender/utils.py
genesis/ext/pyrender/version.py
genesis/ext/pyrender/viewer.py
genesis/ext/urdfpy/__init__.py
genesis/ext/urdfpy/urdf.py
genesis/ext/urdfpy/utils.py
genesis/ext/urdfpy/version.py
genesis/grad/__init__.py
genesis/grad/creation_ops.py
genesis/grad/tensor.py
genesis/logging/__init__.py
genesis/logging/logger.py
genesis/logging/time_elapser.py
genesis/options/__init__.py
genesis/options/misc.py
genesis/options/morphs.py
genesis/options/options.py
genesis/options/profiling.py
genesis/options/recorders.py
genesis/options/renderers.py
genesis/options/scene.py
genesis/options/sensors/__init__.py
genesis/options/sensors/camera.py
genesis/options/sensors/options.py
genesis/options/sensors/raycaster.py
genesis/options/sensors/tactile.py
genesis/options/solvers.py
genesis/options/surfaces.py
genesis/options/textures.py
genesis/options/vis.py
genesis/recorders/__init__.py
genesis/recorders/base_recorder.py
genesis/recorders/file_writers.py
genesis/recorders/plotters.py
genesis/recorders/recorder_manager.py
genesis/recorders/trajectory.py
genesis/repr_base.py
genesis/styles.py
genesis/typing.py
genesis/utils/__init__.py
genesis/utils/array_class.py
genesis/utils/collision.py
genesis/utils/deprecated_module_wrapper.py
genesis/utils/element.py
genesis/utils/emoji.py
genesis/utils/geom.py
genesis/utils/gltf.py
genesis/utils/hybrid.py
genesis/utils/image_exporter.py
genesis/utils/linalg.py
genesis/utils/mesh.py
genesis/utils/misc.py
genesis/utils/mjcf.py
genesis/utils/particle.py
genesis/utils/path_planning.py
genesis/utils/point_cloud.py
genesis/utils/raycast.py
genesis/utils/raycast_qd.py
genesis/utils/repr.py
genesis/utils/ring_buffer.py
genesis/utils/sdf.py
genesis/utils/serialization.py
genesis/utils/terrain.py
genesis/utils/tools.py
genesis/utils/uid.py
genesis/utils/urdf.py
genesis/utils/usd/UsdParserSpec.md
genesis/utils/usd/__init__.py
genesis/utils/usd/usd_bake.py
genesis/utils/usd/usd_collision.py
genesis/utils/usd/usd_context.py
genesis/utils/usd/usd_geometry.py
genesis/utils/usd/usd_material.py
genesis/utils/usd/usd_rigid_entity.py
genesis/utils/usd/usd_stage.py
genesis/utils/usd/usd_utils.py
genesis/utils/video_encoder.py
genesis/utils/warnings.py
genesis/utils/watertighten.py
genesis/version.py
genesis/vis/__init__.py
genesis/vis/batch_renderer.py
genesis/vis/camera.py
genesis/vis/keybindings.py
genesis/vis/rasterizer.py
genesis/vis/rasterizer_context.py
genesis/vis/raytracer.py
genesis/vis/viewer.py
genesis/vis/viewer_plugins/__init__.py
genesis/vis/viewer_plugins/base.py
genesis/vis/viewer_plugins/plugins/__init__.py
genesis/vis/viewer_plugins/plugins/default_controls.py
genesis/vis/viewer_plugins/plugins/mouse_interaction.py
genesis/vis/viewer_plugins/raycast.py
genesis/vis/visualizer.py
pyproject.toml
tests/__init__.py
tests/benchmarks/__init__.py
tests/benchmarks/test_rigid.py
tests/conftest.py
tests/core/__init__.py
tests/core/test_backend.py
tests/core/test_bvh.py
tests/core/test_misc.py
tests/core/test_quadrants.py
tests/core/test_recorders.py
tests/core/test_surface.py
tests/core/test_utils.py
tests/coupling/__init__.py
tests/coupling/test_hybrid.py
tests/coupling/test_sph_rigid.py
tests/deformable/__init__.py
tests/deformable/test_fem.py
tests/deformable/test_muscle.py
tests/gpu_info.py
tests/grad/__init__.py
tests/grad/conftest.py
tests/grad/test_grad_tape.py
tests/grad/test_hybrid_push.py
tests/grad/test_rigid_collision.py
tests/grad/test_rigid_constraints.py
tests/grad/test_rigid_dynamics.py
tests/grad/test_rigid_optim.py
tests/grad/utils.py
tests/integration/__init__.py
tests/integration/test_integration.py
tests/ipc/__init__.py
tests/ipc/test_api.py
tests/ipc/test_deformable.py
tests/ipc/test_rigid.py
tests/ipc/utils.py
tests/monitor_test_mem.py
tests/parsers/__init__.py
tests/parsers/conftest.py
tests/parsers/test_mesh.py
tests/parsers/test_usd.py
tests/particles/__init__.py
tests/particles/test_mpm.py
tests/particles/test_pbd.py
tests/particles/test_sf.py
tests/particles/test_sph.py
tests/rendering/__init__.py
tests/rendering/conftest.py
tests/rendering/test_batch_render.py
tests/rendering/test_debug_draw.py
tests/rendering/test_dynamic_meshes.py
tests/rendering/test_imgui_overlay.py
tests/rendering/test_interactive_viewer.py
tests/rendering/test_offscreen.py
tests/rigid/__init__.py
tests/rigid/conftest.py
tests/rigid/test_api.py
tests/rigid/test_asset_loading.py
tests/rigid/test_collision.py
tests/rigid/test_collision_nonconvex.py
tests/rigid/test_constraints.py
tests/rigid/test_control.py
tests/rigid/test_dynamics.py
tests/rigid/test_friction.py
tests/rigid/test_heterogeneous.py
tests/rigid/test_islands.py
tests/rigid/test_kinematics.py
tests/rigid/test_mujoco_parity.py
tests/rigid/test_narrowphase.py
tests/rigid/test_serialization.py
tests/rigid/test_sparse.py
tests/rigid/test_terrain.py
tests/sensors/__init__.py
tests/sensors/conftest.py
tests/sensors/test_api.py
tests/sensors/test_camera.py
tests/sensors/test_contact.py
tests/sensors/test_imu.py
tests/sensors/test_joint_torque.py
tests/sensors/test_raycaster.py
tests/sensors/test_tactile.py
tests/sensors/test_temperature.py
tests/test_examples.py
tests/upload_benchmarks_table_to_wandb.py
tests/utils/assertions.py
tests/utils/assets.py
tests/utils/collision.py
tests/utils/mesh_pairs_viewer.html
tests/utils/misc.py
tests/utils/mujoco_parity.py
tests/utils/simulators.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `genesis/assets/meshes` | 12 | 33.3 MB | [`genesis/assets/meshes/_OMITTED.md`](./genesis/assets/meshes/_OMITTED.md) |
| `genesis/assets/meshes/Airplane` | 1 | 99 KB | [`genesis/assets/meshes/Airplane/_OMITTED.md`](./genesis/assets/meshes/Airplane/_OMITTED.md) |
| `genesis/assets/meshes/Airplane/textures` | 2 | 1.4 MB | [`genesis/assets/meshes/Airplane/textures/_OMITTED.md`](./genesis/assets/meshes/Airplane/textures/_OMITTED.md) |
| `genesis/assets/meshes/bathtub` | 1 | 685 KB | [`genesis/assets/meshes/bathtub/_OMITTED.md`](./genesis/assets/meshes/bathtub/_OMITTED.md) |
| `genesis/assets/meshes/boat` | 17 | 8.7 MB | [`genesis/assets/meshes/boat/_OMITTED.md`](./genesis/assets/meshes/boat/_OMITTED.md) |
| `genesis/assets/meshes/bolt_nut` | 2 | 824 KB | [`genesis/assets/meshes/bolt_nut/_OMITTED.md`](./genesis/assets/meshes/bolt_nut/_OMITTED.md) |
| `genesis/assets/meshes/camera` | 1 | 81 KB | [`genesis/assets/meshes/camera/_OMITTED.md`](./genesis/assets/meshes/camera/_OMITTED.md) |
| `genesis/assets/meshes/chopping-board/source` | 1 | 440 KB | [`genesis/assets/meshes/chopping-board/source/_OMITTED.md`](./genesis/assets/meshes/chopping-board/source/_OMITTED.md) |
| `genesis/assets/meshes/chopping-board/textures` | 1 | 424 KB | [`genesis/assets/meshes/chopping-board/textures/_OMITTED.md`](./genesis/assets/meshes/chopping-board/textures/_OMITTED.md) |
| `genesis/assets/meshes/dragon` | 2 | 2.8 MB | [`genesis/assets/meshes/dragon/_OMITTED.md`](./genesis/assets/meshes/dragon/_OMITTED.md) |
| `genesis/assets/meshes/duck` | 2 | 543 KB | [`genesis/assets/meshes/duck/_OMITTED.md`](./genesis/assets/meshes/duck/_OMITTED.md) |
| `genesis/assets/meshes/env_sphere` | 2 | 265 KB | [`genesis/assets/meshes/env_sphere/_OMITTED.md`](./genesis/assets/meshes/env_sphere/_OMITTED.md) |
| `genesis/assets/meshes/wooden_sphere_OBJ` | 5 | 5.6 MB | [`genesis/assets/meshes/wooden_sphere_OBJ/_OMITTED.md`](./genesis/assets/meshes/wooden_sphere_OBJ/_OMITTED.md) |
| `genesis/assets/meshes/worm` | 6 | 10.0 MB | [`genesis/assets/meshes/worm/_OMITTED.md`](./genesis/assets/meshes/worm/_OMITTED.md) |
| `genesis/assets/textures` | 2 | 3.2 MB | [`genesis/assets/textures/_OMITTED.md`](./genesis/assets/textures/_OMITTED.md) |
| `genesis/assets/tower` | 16 | 736 KB | [`genesis/assets/tower/_OMITTED.md`](./genesis/assets/tower/_OMITTED.md) |
| `genesis/assets/urdf/3763/parts_render` | 5 | 65 KB | [`genesis/assets/urdf/3763/parts_render/_OMITTED.md`](./genesis/assets/urdf/3763/parts_render/_OMITTED.md) |
| `genesis/assets/urdf/3763/parts_render_after_merging` | 5 | 84 KB | [`genesis/assets/urdf/3763/parts_render_after_merging/_OMITTED.md`](./genesis/assets/urdf/3763/parts_render_after_merging/_OMITTED.md) |
| `genesis/assets/urdf/3763/point_sample` | 3 | 1.5 MB | [`genesis/assets/urdf/3763/point_sample/_OMITTED.md`](./genesis/assets/urdf/3763/point_sample/_OMITTED.md) |
| `genesis/assets/urdf/3763/textured_objs` | 6 | 102 KB | [`genesis/assets/urdf/3763/textured_objs/_OMITTED.md`](./genesis/assets/urdf/3763/textured_objs/_OMITTED.md) |
| `genesis/assets/urdf/anymal_c/meshes` | 36 | 7.9 MB | [`genesis/assets/urdf/anymal_c/meshes/_OMITTED.md`](./genesis/assets/urdf/anymal_c/meshes/_OMITTED.md) |
| `genesis/assets/urdf/blue_box/assets` | 1 | 13 KB | [`genesis/assets/urdf/blue_box/assets/_OMITTED.md`](./genesis/assets/urdf/blue_box/assets/_OMITTED.md) |
| `genesis/assets/urdf/drones` | 7 | 1.4 MB | [`genesis/assets/urdf/drones/_OMITTED.md`](./genesis/assets/urdf/drones/_OMITTED.md) |
| `genesis/assets/urdf/go2/dae` | 7 | 24.7 MB | [`genesis/assets/urdf/go2/dae/_OMITTED.md`](./genesis/assets/urdf/go2/dae/_OMITTED.md) |
| `genesis/assets/urdf/kuka_iiwa/meshes` | 22 | 6.6 MB | [`genesis/assets/urdf/kuka_iiwa/meshes/_OMITTED.md`](./genesis/assets/urdf/kuka_iiwa/meshes/_OMITTED.md) |
| `genesis/assets/urdf/panda_bullet/meshes/collision` | 10 | 417 KB | [`genesis/assets/urdf/panda_bullet/meshes/collision/_OMITTED.md`](./genesis/assets/urdf/panda_bullet/meshes/collision/_OMITTED.md) |
| `genesis/assets/urdf/panda_bullet/meshes/visual` | 11 | 13.8 MB | [`genesis/assets/urdf/panda_bullet/meshes/visual/_OMITTED.md`](./genesis/assets/urdf/panda_bullet/meshes/visual/_OMITTED.md) |
| `genesis/assets/urdf/plane` | 4 | 9 KB | [`genesis/assets/urdf/plane/_OMITTED.md`](./genesis/assets/urdf/plane/_OMITTED.md) |
| `genesis/assets/urdf/shadow_hand/meshes/collision` | 11 | 60 KB | [`genesis/assets/urdf/shadow_hand/meshes/collision/_OMITTED.md`](./genesis/assets/urdf/shadow_hand/meshes/collision/_OMITTED.md) |
| `genesis/assets/urdf/shadow_hand/meshes/visual` | 11 | 1.2 MB | [`genesis/assets/urdf/shadow_hand/meshes/visual/_OMITTED.md`](./genesis/assets/urdf/shadow_hand/meshes/visual/_OMITTED.md) |
| `genesis/assets/urdf/wheel` | 3 | 1.1 MB | [`genesis/assets/urdf/wheel/_OMITTED.md`](./genesis/assets/urdf/wheel/_OMITTED.md) |
| `genesis/assets/xml` | 2 | 1 KB | [`genesis/assets/xml/_OMITTED.md`](./genesis/assets/xml/_OMITTED.md) |
| `genesis/assets/xml/franka_emika_panda` | 1 | 2.1 MB | [`genesis/assets/xml/franka_emika_panda/_OMITTED.md`](./genesis/assets/xml/franka_emika_panda/_OMITTED.md) |
| `genesis/assets/xml/franka_emika_panda/assets` | 67 | 32.7 MB | [`genesis/assets/xml/franka_emika_panda/assets/_OMITTED.md`](./genesis/assets/xml/franka_emika_panda/assets/_OMITTED.md) |
| `genesis/assets/xml/franka_sim` | 2 | 357 KB | [`genesis/assets/xml/franka_sim/_OMITTED.md`](./genesis/assets/xml/franka_sim/_OMITTED.md) |
| `genesis/assets/xml/franka_sim/meshes/collision` | 10 | 115 KB | [`genesis/assets/xml/franka_sim/meshes/collision/_OMITTED.md`](./genesis/assets/xml/franka_sim/meshes/collision/_OMITTED.md) |
| `genesis/assets/xml/franka_sim/meshes/visual` | 15 | 7.5 MB | [`genesis/assets/xml/franka_sim/meshes/visual/_OMITTED.md`](./genesis/assets/xml/franka_sim/meshes/visual/_OMITTED.md) |
| `genesis/assets/xml/universal_robots_ur5e` | 1 | 1.9 MB | [`genesis/assets/xml/universal_robots_ur5e/_OMITTED.md`](./genesis/assets/xml/universal_robots_ur5e/_OMITTED.md) |
| `genesis/assets/xml/universal_robots_ur5e/assets` | 20 | 29.5 MB | [`genesis/assets/xml/universal_robots_ur5e/assets/_OMITTED.md`](./genesis/assets/xml/universal_robots_ur5e/assets/_OMITTED.md) |
| `genesis/ext/pyrender/fonts` | 12 | 2.3 MB | [`genesis/ext/pyrender/fonts/_OMITTED.md`](./genesis/ext/pyrender/fonts/_OMITTED.md) |
| `imgs` | 3 | 2.3 MB | [`imgs/_OMITTED.md`](./imgs/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
