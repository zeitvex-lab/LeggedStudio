# LeggedSkillDeploy — 参考资源

> **来源**：`00_open/LeggedSkillDeploy/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_go1（宇树 Go1 四足）、unitree_g1（宇树 G1 人形）、deeprobotics_m20（云深处 M20 轮足）
> **定位**：多机型技能部署包（策略 + 部署配置）
> **收录**：159 个文件 / 43.6 MB（其中推理策略/模型文件 31 个）
> **已省略**：232 个文件 / 339.8 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（55 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（23 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（50 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（4 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（7 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（19 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （3 个文件）
bash/  （3 个文件）
    (直接文件)/
motor_sdk/  （11 个文件）
    go1_pro_sdk/
policy/  （54 个文件）
    issacgym/
    unitree_rl_lab/
robot_description/  （66 个文件）
    mjcf/
    urdf/
src/  （22 个文件）
    (直接文件)/
    input_dev/
    interface/
    scripts/
    tools/
    utils/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 46 |
| `.pt` | 26 |
| `.yaml` | 23 |
| `.xml` | 17 |
| `.xacro` | 15 |
| `.txt` | 8 |
| `.csv` | 6 |
| `.urdf` | 6 |
| `.onnx` | 5 |
| `.sh` | 2 |
| `(无扩展名)` | 1 |
| `.md` | 1 |
| `.bat` | 1 |
| `.rviz` | 1 |
| `.world` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
README.md
bash/git.bat
bash/git.sh
bash/merge.sh
motor_sdk/go1_pro_sdk/example_1.py
motor_sdk/go1_pro_sdk/example_ros2.py
motor_sdk/go1_pro_sdk/example_ros2_old.py
motor_sdk/go1_pro_sdk/ucl/common.py
motor_sdk/go1_pro_sdk/ucl/complex.py
motor_sdk/go1_pro_sdk/ucl/enums.py
motor_sdk/go1_pro_sdk/ucl/highCmd.py
motor_sdk/go1_pro_sdk/ucl/highState.py
motor_sdk/go1_pro_sdk/ucl/lowCmd.py
motor_sdk/go1_pro_sdk/ucl/lowState.py
motor_sdk/go1_pro_sdk/ucl/unitreeConnection.py
policy/issacgym/M20/M20/Jun13_23-01-46_highplatform.pt
policy/issacgym/M20/M20/Jun18_15-24-47_lc.pt
policy/issacgym/M20/M20/config.yaml
policy/issacgym/M20/M20/policy_dwaq.pt
policy/issacgym/M20/M20_lab/config.yaml
policy/issacgym/M20/M20_lab/policy.pt
policy/issacgym/duow/duow/Mar19_09-34-46_lc.pt
policy/issacgym/duow/duow/config.yaml
policy/issacgym/go1/go1/Mar03_22-44-57_2.pt
policy/issacgym/go1/go1/Mar05_21-28-33_hs.pt
policy/issacgym/go1/go1/Mar16_21-28-37_ls.pt
policy/issacgym/go1/go1/Mar24_22-05-56_hop.pt
policy/issacgym/go1/go1/Mar25_19-19-16_bound.pt
policy/issacgym/go1/go1/config.yaml
policy/issacgym/go1/himloco/config.yaml
policy/issacgym/go1/himloco/himloco_best.pt
policy/issacgym/go1/moe/config.yaml
policy/issacgym/go1/moe/moe_best.pt
policy/issacgym/go1/np3o/config.yaml
policy/issacgym/go1/np3o/np3o_cpu_model.pt
policy/issacgym/go2w/go2w_himloco/May07_21-38-45_lc.pt
policy/issacgym/go2w/go2w_himloco/May09_00-04-51_lc_stand_front.pt
policy/issacgym/go2w/go2w_himloco/May09_15-08-14_hs.pt
policy/issacgym/go2w/go2w_himloco/May09_17-24-55_ls.pt
policy/issacgym/go2w/go2w_himloco/config.yaml
policy/unitree_rl_lab/g1/dance1_subject2/config.yaml
policy/unitree_rl_lab/g1/dance1_subject2/dance1_subject2_30hz.csv
policy/unitree_rl_lab/g1/dance1_subject2/policy.onnx
policy/unitree_rl_lab/g1/dance1_subject2/policy.pt
policy/unitree_rl_lab/g1/dance_102/G1_Take_102.bvh_60hz.csv
policy/unitree_rl_lab/g1/dance_102/config.yaml
policy/unitree_rl_lab/g1/dance_102/policy.onnx
policy/unitree_rl_lab/g1/dance_102/policy.pt
policy/unitree_rl_lab/g1/g1_amp/config.yaml
policy/unitree_rl_lab/g1/g1_amp/g1_amp.pt
policy/unitree_rl_lab/g1/g1_loco/config.yaml
policy/unitree_rl_lab/g1/g1_loco/policy_29dof.pt
policy/unitree_rl_lab/g1/gangnam_style/G1_gangnam_style_V01.bvh_60hz.csv
policy/unitree_rl_lab/g1/gangnam_style/config.yaml
policy/unitree_rl_lab/g1/gangnam_style/policy.onnx
policy/unitree_rl_lab/g1/gangnam_style/policy.pt
policy/unitree_rl_lab/go2/go2_back_filp/config.yaml
policy/unitree_rl_lab/go2/go2_back_filp/go2_backfilp_0428_for_csv_to_npz.csv
policy/unitree_rl_lab/go2/go2_back_filp/policy.onnx
policy/unitree_rl_lab/go2/go2_back_filp/policy.pt
policy/unitree_rl_lab/go2/go2_jump/config.yaml
policy/unitree_rl_lab/go2/go2_jump/go2_jump.csv
policy/unitree_rl_lab/go2/go2_jump/policy.onnx
policy/unitree_rl_lab/go2/go2_jump/policy.pt
policy/unitree_rl_lab/go2/go2_loco/config.yaml
policy/unitree_rl_lab/go2/go2_loco/policy.pt
policy/unitree_rl_lab/go2/go2_silde_filp/config.yaml
policy/unitree_rl_lab/go2/go2_silde_filp/go2_sildfilp_0428_for_csv_to_npz.csv
policy/unitree_rl_lab/go2/go2_silde_filp/policy.pt
requirements.txt
robot_description/mjcf/M20/M20.xml
robot_description/mjcf/duow/duow.xml
robot_description/mjcf/g1/g1_29dof.xml
robot_description/mjcf/go1/go1.xml
robot_description/mjcf/go2/go2.xml
robot_description/mjcf/go2w/go2w.xml
robot_description/mjcf/terrains/empty_world.xml
robot_description/mjcf/terrains/gap.xml
robot_description/mjcf/terrains/parkour.xml
robot_description/mjcf/terrains/race_track.xml
robot_description/urdf/src/duow_description/CMakeLists.txt
robot_description/urdf/src/duow_description/config/duow_control_ros2.yaml
robot_description/urdf/src/duow_description/launch/gazebo.launch.py
robot_description/urdf/src/duow_description/launch/rviz.launch.py
robot_description/urdf/src/duow_description/package.xml
robot_description/urdf/src/duow_description/urdf/duow_description.urdf
robot_description/urdf/src/duow_description/xacro/gazebo.xacro
robot_description/urdf/src/duow_description/xacro/robot.xacro
robot_description/urdf/src/g1_description/CMakeLists.txt
robot_description/urdf/src/g1_description/config/g1_control_ros2.yaml
robot_description/urdf/src/g1_description/launch/gazebo.launch.py
robot_description/urdf/src/g1_description/launch/rviz.launch.py
robot_description/urdf/src/g1_description/package.xml
robot_description/urdf/src/g1_description/urdf/g1_29dof_rev_1_0_modify_inertia.urdf
robot_description/urdf/src/g1_description/xacro/gazebo.xacro
robot_description/urdf/src/g1_description/xacro/robot.xacro
robot_description/urdf/src/go1_description/CMakeLists.txt
robot_description/urdf/src/go1_description/config/go1_control_ros2.yaml
robot_description/urdf/src/go1_description/launch/gazebo.launch.py
robot_description/urdf/src/go1_description/launch/rviz.launch.py
robot_description/urdf/src/go1_description/package.xml
robot_description/urdf/src/go1_description/urdf/go1_description.urdf
robot_description/urdf/src/go1_description/xacro/gazebo.xacro
robot_description/urdf/src/go1_description/xacro/robot.xacro
robot_description/urdf/src/go2_description/CMakeLists.txt
robot_description/urdf/src/go2_description/config/go2_control_ros2.yaml
robot_description/urdf/src/go2_description/launch/gazebo.launch.py
robot_description/urdf/src/go2_description/launch/rviz.launch.py
robot_description/urdf/src/go2_description/package.xml
robot_description/urdf/src/go2_description/urdf/go2_description.urdf
robot_description/urdf/src/go2_description/xacro/gazebo.xacro
robot_description/urdf/src/go2_description/xacro/robot.xacro
robot_description/urdf/src/go2w_description/CMakeLists.txt
robot_description/urdf/src/go2w_description/config/go2w_control_ros2.yaml
robot_description/urdf/src/go2w_description/launch/gazebo.launch.py
robot_description/urdf/src/go2w_description/launch/rviz.launch.py
robot_description/urdf/src/go2w_description/package.xml
robot_description/urdf/src/go2w_description/urdf/go2w_description.urdf
robot_description/urdf/src/go2w_description/xacro/gazebo.xacro
robot_description/urdf/src/go2w_description/xacro/robot.xacro
robot_description/urdf/src/m20_description/CMakeLists.txt
robot_description/urdf/src/m20_description/config/m20_control_ros2.yaml
robot_description/urdf/src/m20_description/launch/gazebo.launch.py
robot_description/urdf/src/m20_description/launch/rviz.launch.py
robot_description/urdf/src/m20_description/package.xml
robot_description/urdf/src/m20_description/urdf/m20_description.urdf
robot_description/urdf/src/m20_description/xacro/gazebo.xacro
robot_description/urdf/src/m20_description/xacro/robot.xacro
robot_description/urdf/src/robot_common/CMakeLists.txt
robot_description/urdf/src/robot_common/package.xml
robot_description/urdf/src/robot_common/rviz/check_joint.rviz
robot_description/urdf/src/robot_common/scripts/odom_to_tf.py
robot_description/urdf/src/robot_common/worlds/stairs.world
robot_description/urdf/src/robot_common/xacro/d435.xacro
robot_description/urdf/src/robot_common/xacro/gazebo_plugins.xacro
robot_description/urdf/src/robot_common/xacro/mid360.xacro
src/input_dev/keyboard_control.py
src/input_dev/phone_web_control.py
src/input_dev/xbox_control.py
src/input_dev/xbox_control_pygame.py
src/interface/IOGazebo.py
src/interface/IOMuJoCo.py
src/interface/IOReal_go1.py
src/rl_gazebo.py
src/rl_mujoco.py
src/rl_mujoco_glfw.py
src/rl_real_go1.py
src/scripts/motion_loader.py
src/scripts/observation_buffer.py
src/scripts/rl_data.py
src/scripts/rl_deploy.py
src/scripts/rl_sdk.py
src/tools/actuator_net.py
src/tools/convert_policy.py
src/utils/helper.py
src/utils/math.py
src/utils/mujoco_video_recorder.py
src/utils/path_config.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `assets` | 2 | 3.7 MB | [`assets/_OMITTED.md`](./assets/_OMITTED.md) |
| `robot_description/mjcf/M20/meshes` | 17 | 11.4 MB | [`robot_description/mjcf/M20/meshes/_OMITTED.md`](./robot_description/mjcf/M20/meshes/_OMITTED.md) |
| `robot_description/mjcf/duow/assets` | 9 | 17.5 MB | [`robot_description/mjcf/duow/assets/_OMITTED.md`](./robot_description/mjcf/duow/assets/_OMITTED.md) |
| `robot_description/mjcf/g1/meshes` | 64 | 51.8 MB | [`robot_description/mjcf/g1/meshes/_OMITTED.md`](./robot_description/mjcf/g1/meshes/_OMITTED.md) |
| `robot_description/mjcf/go1/assets` | 6 | 9.9 MB | [`robot_description/mjcf/go1/assets/_OMITTED.md`](./robot_description/mjcf/go1/assets/_OMITTED.md) |
| `robot_description/mjcf/go2/assets` | 16 | 27.8 MB | [`robot_description/mjcf/go2/assets/_OMITTED.md`](./robot_description/mjcf/go2/assets/_OMITTED.md) |
| `robot_description/mjcf/go2w/assets` | 21 | 32.7 MB | [`robot_description/mjcf/go2w/assets/_OMITTED.md`](./robot_description/mjcf/go2w/assets/_OMITTED.md) |
| `robot_description/mjcf/terrains/textures` | 8 | 90 KB | [`robot_description/mjcf/terrains/textures/_OMITTED.md`](./robot_description/mjcf/terrains/textures/_OMITTED.md) |
| `robot_description/urdf/src/duow_description/meshes` | 11 | 18.3 MB | [`robot_description/urdf/src/duow_description/meshes/_OMITTED.md`](./robot_description/urdf/src/duow_description/meshes/_OMITTED.md) |
| `robot_description/urdf/src/g1_description/meshes` | 38 | 32.9 MB | [`robot_description/urdf/src/g1_description/meshes/_OMITTED.md`](./robot_description/urdf/src/g1_description/meshes/_OMITTED.md) |
| `robot_description/urdf/src/go1_description/meshes` | 6 | 68.8 MB | [`robot_description/urdf/src/go1_description/meshes/_OMITTED.md`](./robot_description/urdf/src/go1_description/meshes/_OMITTED.md) |
| `robot_description/urdf/src/go2_description/meshes` | 7 | 24.7 MB | [`robot_description/urdf/src/go2_description/meshes/_OMITTED.md`](./robot_description/urdf/src/go2_description/meshes/_OMITTED.md) |
| `robot_description/urdf/src/go2w_description/meshes` | 9 | 29.0 MB | [`robot_description/urdf/src/go2w_description/meshes/_OMITTED.md`](./robot_description/urdf/src/go2w_description/meshes/_OMITTED.md) |
| `robot_description/urdf/src/m20_description/meshes` | 17 | 11.4 MB | [`robot_description/urdf/src/m20_description/meshes/_OMITTED.md`](./robot_description/urdf/src/m20_description/meshes/_OMITTED.md) |
| `robot_description/urdf/src/robot_common/meshes` | 1 | 23 KB | [`robot_description/urdf/src/robot_common/meshes/_OMITTED.md`](./robot_description/urdf/src/robot_common/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
