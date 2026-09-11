# robot-descriptions-quadruped — 参考资源

> **来源**：`00_open/robot-descriptions-quadruped/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）、unitree_go2（宇树 Go2 四足）、unitree_b2（宇树 B2 四足）、unitree_b2w（宇树 B2W 轮足）、deeprobotics_lite3（云深处 Lite3 四足）、deeprobotics_m20（云深处 M20 轮足）
> **定位**：四足机型描述汇总（URDF/xacro/MJCF）
> **收录**：181 个文件 / 11.8 MB（其中推理策略/模型文件 8 个）
> **已省略**：65 个文件 / 332.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（123 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（41 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（8 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（8 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（1 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （1 个文件）
deep_robotics/  （45 个文件）
    lite3_description/
    x30_description/
magiclab/  （30 个文件）
    cyberdog_description/
    magicdog_description/
unitree/  （95 个文件）
    aliengo_description/
    unitree_a1_description/
    unitree_b2_description/
    unitree_go1_description/
    unitree_go2_description/
zsibot/  （10 个文件）
    zsl1_description/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.xacro` | 57 |
| `.yaml` | 25 |
| `.info` | 24 |
| `.mtl` | 17 |
| `.md` | 11 |
| `.txt` | 10 |
| `.xml` | 10 |
| `.urdf` | 10 |
| `(无扩展名)` | 9 |
| `.pt` | 8 |

## 文件索引（项目内相对路径）

```text
README.md
deep_robotics/lite3_description/CMakeLists.txt
deep_robotics/lite3_description/LICENSE
deep_robotics/lite3_description/README.md
deep_robotics/lite3_description/config/gazebo.yaml
deep_robotics/lite3_description/config/legged_gym/config.yaml
deep_robotics/lite3_description/config/legged_gym/policy.pt
deep_robotics/lite3_description/config/ocs2/gait.info
deep_robotics/lite3_description/config/ocs2/reference.info
deep_robotics/lite3_description/config/ocs2/task.info
deep_robotics/lite3_description/config/robot_control.yaml
deep_robotics/lite3_description/meshes/hip.mtl
deep_robotics/lite3_description/meshes/shank.mtl
deep_robotics/lite3_description/meshes/thigh.mtl
deep_robotics/lite3_description/meshes/torso.mtl
deep_robotics/lite3_description/package.xml
deep_robotics/lite3_description/urdf/lite3.urdf
deep_robotics/lite3_description/xacro/const.xacro
deep_robotics/lite3_description/xacro/leg.xacro
deep_robotics/lite3_description/xacro/robot.xacro
deep_robotics/lite3_description/xacro/ros2_control/gazebo.xacro
deep_robotics/lite3_description/xacro/ros2_control/robot.xacro
deep_robotics/lite3_description/xacro/ros2_control/ros2_control.xacro
deep_robotics/x30_description/CMakeLists.txt
deep_robotics/x30_description/LICENSE
deep_robotics/x30_description/README.md
deep_robotics/x30_description/config/gazebo.yaml
deep_robotics/x30_description/config/legged_gym/config.yaml
deep_robotics/x30_description/config/legged_gym/policy.pt
deep_robotics/x30_description/config/ocs2/gait.info
deep_robotics/x30_description/config/ocs2/reference.info
deep_robotics/x30_description/config/ocs2/task.info
deep_robotics/x30_description/config/robot_control.yaml
deep_robotics/x30_description/meshes/material.mtl
deep_robotics/x30_description/meshes/shank.mtl
deep_robotics/x30_description/meshes/torso.mtl
deep_robotics/x30_description/package.xml
deep_robotics/x30_description/urdf/x30.urdf
deep_robotics/x30_description/urdf/x30_generated.urdf
deep_robotics/x30_description/xacro/const.xacro
deep_robotics/x30_description/xacro/imu_link.xacro
deep_robotics/x30_description/xacro/leg.xacro
deep_robotics/x30_description/xacro/robot.xacro
deep_robotics/x30_description/xacro/ros2_control/gazebo.xacro
deep_robotics/x30_description/xacro/ros2_control/robot.xacro
deep_robotics/x30_description/xacro/ros2_control/ros2_control.xacro
magiclab/cyberdog_description/CMakeLists.txt
magiclab/cyberdog_description/README.md
magiclab/cyberdog_description/config/gazebo.yaml
magiclab/cyberdog_description/config/ocs2/gait.info
magiclab/cyberdog_description/config/ocs2/reference.info
magiclab/cyberdog_description/config/ocs2/task.info
magiclab/cyberdog_description/config/robot_control.yaml
magiclab/cyberdog_description/meshes/hip.mtl
magiclab/cyberdog_description/package.xml
magiclab/cyberdog_description/urdf/cyberdog.urdf
magiclab/cyberdog_description/xacro/const.xacro
magiclab/cyberdog_description/xacro/leg.xacro
magiclab/cyberdog_description/xacro/robot.xacro
magiclab/cyberdog_description/xacro/ros2_control/gazebo.xacro
magiclab/cyberdog_description/xacro/ros2_control/robot.xacro
magiclab/cyberdog_description/xacro/ros2_control/ros2_control.xacro
magiclab/magicdog_description/CMakeLists.txt
magiclab/magicdog_description/LICENSE
magiclab/magicdog_description/README.md
magiclab/magicdog_description/config/gazebo.yaml
magiclab/magicdog_description/meshes/base.mtl
magiclab/magicdog_description/meshes/claf.mtl
magiclab/magicdog_description/meshes/hip.mtl
magiclab/magicdog_description/meshes/thigh.mtl
magiclab/magicdog_description/package.xml
magiclab/magicdog_description/urdf/magicdog.urdf
magiclab/magicdog_description/xacro/leg.xacro
magiclab/magicdog_description/xacro/robot.xacro
magiclab/magicdog_description/xacro/ros2_control/gazebo.xacro
magiclab/magicdog_description/xacro/ros2_control/robot.xacro
unitree/aliengo_description/CMakeLists.txt
unitree/aliengo_description/LICENSE
unitree/aliengo_description/README.md
unitree/aliengo_description/config/gazebo.yaml
unitree/aliengo_description/config/legged_gym/config.yaml
unitree/aliengo_description/config/legged_gym/policy.pt
unitree/aliengo_description/config/ocs2/gait.info
unitree/aliengo_description/config/ocs2/reference.info
unitree/aliengo_description/config/ocs2/task.info
unitree/aliengo_description/config/robot_control.yaml
unitree/aliengo_description/package.xml
unitree/aliengo_description/urdf/aliengo.urdf
unitree/aliengo_description/xacro/const.xacro
unitree/aliengo_description/xacro/leg.xacro
unitree/aliengo_description/xacro/robot.xacro
unitree/aliengo_description/xacro/ros2_control/gazebo.xacro
unitree/aliengo_description/xacro/ros2_control/robot.xacro
unitree/aliengo_description/xacro/ros2_control/ros2_control.xacro
unitree/unitree_a1_description/CMakeLists.txt
unitree/unitree_a1_description/LICENSE
unitree/unitree_a1_description/README.md
unitree/unitree_a1_description/config/gazebo.yaml
unitree/unitree_a1_description/config/legged_gym/config.yaml
unitree/unitree_a1_description/config/legged_gym/config_himloco.yaml
unitree/unitree_a1_description/config/legged_gym/him.pt
unitree/unitree_a1_description/config/legged_gym/rl_sar.pt
unitree/unitree_a1_description/config/ocs2/gait.info
unitree/unitree_a1_description/config/ocs2/reference.info
unitree/unitree_a1_description/config/ocs2/task.info
unitree/unitree_a1_description/config/robot_control.yaml
unitree/unitree_a1_description/package.xml
unitree/unitree_a1_description/urdf/unitree_a1.urdf
unitree/unitree_a1_description/xacro/const.xacro
unitree/unitree_a1_description/xacro/leg.xacro
unitree/unitree_a1_description/xacro/robot.xacro
unitree/unitree_a1_description/xacro/ros2_control/gazebo.xacro
unitree/unitree_a1_description/xacro/ros2_control/robot.xacro
unitree/unitree_a1_description/xacro/ros2_control/ros2_control.xacro
unitree/unitree_b2_description/CMakeLists.txt
unitree/unitree_b2_description/LICENSE
unitree/unitree_b2_description/README.md
unitree/unitree_b2_description/config/gazebo.yaml
unitree/unitree_b2_description/config/ocs2/gait.info
unitree/unitree_b2_description/config/ocs2/reference.info
unitree/unitree_b2_description/config/ocs2/task.info
unitree/unitree_b2_description/config/robot_control.yaml
unitree/unitree_b2_description/package.xml
unitree/unitree_b2_description/urdf/unitree_b2.urdf
unitree/unitree_b2_description/xacro/const.xacro
unitree/unitree_b2_description/xacro/leg.xacro
unitree/unitree_b2_description/xacro/materials.xacro
unitree/unitree_b2_description/xacro/robot.xacro
unitree/unitree_b2_description/xacro/ros2_control/gazebo.xacro
unitree/unitree_b2_description/xacro/ros2_control/robot.xacro
unitree/unitree_b2_description/xacro/ros2_control/ros2_control.xacro
unitree/unitree_go1_description/CMakeLists.txt
unitree/unitree_go1_description/LICENSE
unitree/unitree_go1_description/README.md
unitree/unitree_go1_description/config/gazebo.yaml
unitree/unitree_go1_description/config/ocs2/gait.info
unitree/unitree_go1_description/config/ocs2/reference.info
unitree/unitree_go1_description/config/ocs2/task.info
unitree/unitree_go1_description/config/robot_control.yaml
unitree/unitree_go1_description/package.xml
unitree/unitree_go1_description/urdf/unitree_go1.urdf
unitree/unitree_go1_description/xacro/const.xacro
unitree/unitree_go1_description/xacro/depthCamera.xacro
unitree/unitree_go1_description/xacro/leg.xacro
unitree/unitree_go1_description/xacro/robot.xacro
unitree/unitree_go1_description/xacro/ros2_control/gazebo.xacro
unitree/unitree_go1_description/xacro/ros2_control/robot.xacro
unitree/unitree_go1_description/xacro/ros2_control/ros2_control.xacro
unitree/unitree_go1_description/xacro/ultraSound.xacro
unitree/unitree_go2_description/CMakeLists.txt
unitree/unitree_go2_description/LICENSE
unitree/unitree_go2_description/README.md
unitree/unitree_go2_description/config/gazebo.yaml
unitree/unitree_go2_description/config/himloco/config.yaml
unitree/unitree_go2_description/config/himloco/himloco.pt
unitree/unitree_go2_description/config/legged_gym/config.yaml
unitree/unitree_go2_description/config/legged_gym/policy.pt
unitree/unitree_go2_description/config/ocs2/gait.info
unitree/unitree_go2_description/config/ocs2/reference.info
unitree/unitree_go2_description/config/ocs2/task.info
unitree/unitree_go2_description/config/robot_control.yaml
unitree/unitree_go2_description/config/robot_lab/config.yaml
unitree/unitree_go2_description/config/robot_lab/policy.pt
unitree/unitree_go2_description/package.xml
unitree/unitree_go2_description/urdf/unitree_go2.urdf
unitree/unitree_go2_description/xacro/const.xacro
unitree/unitree_go2_description/xacro/leg.xacro
unitree/unitree_go2_description/xacro/robot.xacro
unitree/unitree_go2_description/xacro/ros2_control/gazebo.xacro
unitree/unitree_go2_description/xacro/ros2_control/robot.xacro
unitree/unitree_go2_description/xacro/ros2_control/ros2_control.xacro
zsibot/zsl1_description/CMakeLists.txt
zsibot/zsl1_description/LICENSE
zsibot/zsl1_description/README.md
zsibot/zsl1_description/meshes/abad.mtl
zsibot/zsl1_description/meshes/base.mtl
zsibot/zsl1_description/meshes/foot.mtl
zsibot/zsl1_description/meshes/hip.mtl
zsibot/zsl1_description/meshes/knee.mtl
zsibot/zsl1_description/package.xml
zsibot/zsl1_description/xacro/robot.xacro
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.images` | 10 | 1.4 MB | [`.images/_OMITTED.md`](./.images/_OMITTED.md) |
| `deep_robotics/lite3_description/meshes` | 4 | 36.6 MB | [`deep_robotics/lite3_description/meshes/_OMITTED.md`](./deep_robotics/lite3_description/meshes/_OMITTED.md) |
| `deep_robotics/x30_description/meshes` | 4 | 48.6 MB | [`deep_robotics/x30_description/meshes/_OMITTED.md`](./deep_robotics/x30_description/meshes/_OMITTED.md) |
| `magiclab/cyberdog_description/meshes` | 5 | 14.2 MB | [`magiclab/cyberdog_description/meshes/_OMITTED.md`](./magiclab/cyberdog_description/meshes/_OMITTED.md) |
| `magiclab/magicdog_description/meshes` | 5 | 61.5 MB | [`magiclab/magicdog_description/meshes/_OMITTED.md`](./magiclab/magicdog_description/meshes/_OMITTED.md) |
| `unitree/aliengo_description/meshes` | 6 | 6.0 MB | [`unitree/aliengo_description/meshes/_OMITTED.md`](./unitree/aliengo_description/meshes/_OMITTED.md) |
| `unitree/unitree_a1_description/meshes` | 6 | 8.8 MB | [`unitree/unitree_a1_description/meshes/_OMITTED.md`](./unitree/unitree_a1_description/meshes/_OMITTED.md) |
| `unitree/unitree_b2_description/meshes` | 6 | 56.6 MB | [`unitree/unitree_b2_description/meshes/_OMITTED.md`](./unitree/unitree_b2_description/meshes/_OMITTED.md) |
| `unitree/unitree_go1_description/meshes` | 7 | 38.7 MB | [`unitree/unitree_go1_description/meshes/_OMITTED.md`](./unitree/unitree_go1_description/meshes/_OMITTED.md) |
| `unitree/unitree_go2_description/meshes` | 7 | 24.7 MB | [`unitree/unitree_go2_description/meshes/_OMITTED.md`](./unitree/unitree_go2_description/meshes/_OMITTED.md) |
| `zsibot/zsl1_description/meshes` | 5 | 34.8 MB | [`zsibot/zsl1_description/meshes/_OMITTED.md`](./zsibot/zsl1_description/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
