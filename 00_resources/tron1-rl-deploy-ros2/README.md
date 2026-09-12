# tron1-rl-deploy-ros2 — 参考资源

> **来源**：`00_open/tron1-rl-deploy-ros2/`　｜　**类型**：参考项目
> **关联机型**：limx_tron1_pf（逐际动力 TRON1-PF）、limx_tron1_sf（逐际动力 TRON1-SF）、limx_tron1_wf（逐际动力 TRON1-WF）
> **定位**：limxdynamics TRON1 RL 部署（ROS2 controller + hw，含 gazebo sim 与 gym/lab 双关节序参数表）
> **收录**：79 个文件 / 23.4 MB（其中推理策略/模型文件 40 个）
> **已省略**：1 个文件 / 2.6 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（1 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（2 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（62 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（14 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （3 个文件）
robot_controllers/  （62 个文件）
    (直接文件)/
    config/
    include/
    src/
robot_hw/  （14 个文件）
    (直接文件)/
    config/
    include/
    launch/
    src/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.onnx` | 40 |
| `.yaml` | 13 |
| `.cpp` | 8 |
| `.h` | 8 |
| `.xml` | 3 |
| `.md` | 2 |
| `.txt` | 2 |
| `.py` | 2 |
| `(无扩展名)` | 1 |

## 文件索引（项目内相对路径）

```text
LICENSE
README.md
README_cn.md
robot_controllers/CMakeLists.txt
robot_controllers/config/pointfoot/PF_P441A/params.yaml
robot_controllers/config/pointfoot/PF_P441A/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/PF_P441A/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/PF_P441A/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/PF_P441A/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/PF_P441B/params.yaml
robot_controllers/config/pointfoot/PF_P441B/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/PF_P441B/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/PF_P441B/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/PF_P441B/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/PF_P441C/params.yaml
robot_controllers/config/pointfoot/PF_P441C/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/PF_P441C/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/PF_P441C/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/PF_P441C/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/PF_P441C2/params.yaml
robot_controllers/config/pointfoot/PF_P441C2/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/PF_P441C2/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/PF_P441C2/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/PF_P441C2/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/PF_TRON1A/params.yaml
robot_controllers/config/pointfoot/PF_TRON1A/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/PF_TRON1A/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/PF_TRON1A/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/PF_TRON1A/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/PF_TRON1B/params.yaml
robot_controllers/config/pointfoot/PF_TRON1B/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/PF_TRON1B/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/PF_TRON1B/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/PF_TRON1B/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/SF_TRON1A/params.yaml
robot_controllers/config/pointfoot/SF_TRON1A/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/SF_TRON1A/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/SF_TRON1A/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/SF_TRON1A/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/SF_TRON1B/params.yaml
robot_controllers/config/pointfoot/SF_TRON1B/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/SF_TRON1B/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/SF_TRON1B/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/SF_TRON1B/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/WF_TRON1A/params.yaml
robot_controllers/config/pointfoot/WF_TRON1A/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/WF_TRON1A/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/WF_TRON1A/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/WF_TRON1A/policy/isaaclab/policy.onnx
robot_controllers/config/pointfoot/WF_TRON1B/params.yaml
robot_controllers/config/pointfoot/WF_TRON1B/policy/isaacgym/encoder.onnx
robot_controllers/config/pointfoot/WF_TRON1B/policy/isaacgym/policy.onnx
robot_controllers/config/pointfoot/WF_TRON1B/policy/isaaclab/encoder.onnx
robot_controllers/config/pointfoot/WF_TRON1B/policy/isaaclab/policy.onnx
robot_controllers/config/robot_controllers.yaml
robot_controllers/include/robot_controllers/ControllerBase.h
robot_controllers/include/robot_controllers/PointfootController.h
robot_controllers/include/robot_controllers/SolefootController.h
robot_controllers/include/robot_controllers/WheelfootController.h
robot_controllers/package.xml
robot_controllers/robot_controllers_plugin.xml
robot_controllers/src/ControllerBase.cpp
robot_controllers/src/PointfootController.cpp
robot_controllers/src/SolefootController.cpp
robot_controllers/src/WheelfootController.cpp
robot_hw/CMakeLists.txt
robot_hw/config/joystick.yaml
robot_hw/config/robot_hw.yaml
robot_hw/include/robot_hw/HardwareBase.h
robot_hw/include/robot_hw/HardwareLoop.h
robot_hw/include/robot_hw/PointfootHardware.h
robot_hw/include/robot_hw/RobotData.h
robot_hw/launch/pointfoot_hw.launch.py
robot_hw/launch/pointfoot_hw_sim.launch.py
robot_hw/package.xml
robot_hw/src/HardwareBase.cpp
robot_hw/src/HardwareLoop.cpp
robot_hw/src/PointfootHardware.cpp
robot_hw/src/PointfootHardwareNode.cpp
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `doc` | 1 | 2.6 MB | [`doc/_OMITTED.md`](./doc/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
