# Learn-It-All-deployment-sim2real — 参考资源

> **来源**：GitHub [`github.com/youngboss2026/Learn-It-All-deployment-sim2real`](https://github.com/youngboss2026/Learn-It-All-deployment-sim2real) @ `09defd0`（2026-09-23 抓取，详见 [`_SOURCE.md`](./_SOURCE.md)）　｜　**类型**：真机部署参考（Feetech 舵机四足 / ONNX 策略）
> **关联机型**：（无，通用）
> **定位**：Learn-It-All 四足项目的真机部署部分（youngboss2026）：在 Feetech STS3215 舵机四足平台上运行学习到的 ONNX 控制策略与开环步态——dog_feetch 运行时（ONNX 推理 / WitMotion·BNO08x IMU / 舵机 IO / 键盘手柄）与脚本（RL 行走 / 开环 IK 行走 / 关节标定与诊断），vendor 目录为 Feetech 舵机支持库与 WitMotion IMU 协议库（GPL-3.0）
> **收录**：344 个文件 / 7.4 MB（其中推理策略/模型文件 2 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（3 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（5 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（9 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（16 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（3 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（25 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（283 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
Python-WitProtocol/  （17 个文件）
    chs/
dog_feetch/  （29 个文件）
    (直接文件)/
    runtime/
    scripts/
pypot-support-feetech-sts3215/  （294 个文件）
    (直接文件)/
    .github/
    build/
    doc/
    pypot/
    pypot.egg-info/
    samples/
    tests/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 221 |
| `.rst` | 23 |
| `.png` | 18 |
| `.ipynb` | 14 |
| `.txt` | 11 |
| `.md` | 10 |
| `.xml` | 10 |
| `(无扩展名)` | 7 |
| `.jpg` | 4 |
| `.so` | 4 |
| `.dll` | 4 |
| `.rb` | 3 |
| `.onnx` | 2 |
| `.dylib` | 2 |
| `.lua` | 2 |

## 文件索引（项目内相对路径）

```text
.gitignore
Python-WitProtocol/chs/Description.txt
Python-WitProtocol/chs/README.txt
Python-WitProtocol/chs/build/lib/lib/__init__.py
Python-WitProtocol/chs/build/lib/lib/device_model.py
Python-WitProtocol/chs/lib/__init__.py
Python-WitProtocol/chs/lib/data_processor/interface/i_data_processor.py
Python-WitProtocol/chs/lib/data_processor/roles/jy901s_dataProcessor.py
Python-WitProtocol/chs/lib/device_model.py
Python-WitProtocol/chs/lib/protocol_resolver/interface/i_protocol_resolver.py
Python-WitProtocol/chs/lib/protocol_resolver/roles/protocol_485_resolver.py
Python-WitProtocol/chs/lib/protocol_resolver/roles/wit_protocol_resolver.py
Python-WitProtocol/chs/lib/utils/byte_array_converter.py
Python-WitProtocol/chs/setup.py
Python-WitProtocol/chs/witimu.egg-info/PKG-INFO
Python-WitProtocol/chs/witimu.egg-info/SOURCES.txt
Python-WitProtocol/chs/witimu.egg-info/dependency_links.txt
Python-WitProtocol/chs/witimu.egg-info/top_level.txt
README_upstream.md
_SOURCE.md
best.onnx
dog_feetch/LICENSE
dog_feetch/README.md
dog_feetch/TEST.onnx
dog_feetch/__init__.py
dog_feetch/default_position.json
dog_feetch/imu_calib_data.pkl
dog_feetch/runtime/HWT_IMU_test.py
dog_feetch/runtime/__init__.py
dog_feetch/runtime/horsebro_imu.py
dog_feetch/runtime/onnx_infer.py
dog_feetch/runtime/position_hwi.py
dog_feetch/runtime/raw_imu.py
dog_feetch/runtime/rl_utils.py
dog_feetch/runtime/xbox.py
dog_feetch/scripts/__init__.py
dog_feetch/scripts/calibrate_joint_gui.py
dog_feetch/scripts/center_all_servos.py
dog_feetch/scripts/check_motor.py
dog_feetch/scripts/configure_motor.py
dog_feetch/scripts/handmotor.py
dog_feetch/scripts/set_default_position.py
dog_feetch/scripts/test.py
dog_feetch/scripts/test1.py
dog_feetch/scripts/test2.py
dog_feetch/scripts/test3.py
dog_feetch/scripts/test_servo_direction.py
dog_feetch/scripts/walk_by_openloop.py
dog_feetch/scripts/walk_by_openloop_leg_test.py
dog_feetch/scripts/walk_by_rl.py
pypot-support-feetech-sts3215/.github/workflows/test_and_distribute.yml
pypot-support-feetech-sts3215/.gitignore
pypot-support-feetech-sts3215/LICENSE.txt
pypot-support-feetech-sts3215/MANIFEST.in
pypot-support-feetech-sts3215/README.md
pypot-support-feetech-sts3215/REST-APIs.md
pypot-support-feetech-sts3215/build/lib/pypot/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/_version.py
pypot-support-feetech-sts3215/build/lib/pypot/creatures/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/creatures/abstractcreature.py
pypot-support-feetech-sts3215/build/lib/pypot/creatures/configure_utility.py
pypot-support-feetech-sts3215/build/lib/pypot/creatures/ik.py
pypot-support-feetech-sts3215/build/lib/pypot/creatures/services_launcher.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/controller.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/conversion.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/error.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/io/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/io/abstract_io.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/io/io.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/io/io_320.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/io/io_xl330.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/io/io_xm430.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/motor.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/protocol/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/protocol/v1.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/protocol/v2.py
pypot-support-feetech-sts3215/build/lib/pypot/dynamixel/syncloop.py
pypot-support-feetech-sts3215/build/lib/pypot/feetech/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/feetech/sts3215_io.py
pypot-support-feetech-sts3215/build/lib/pypot/kinematics.py
pypot-support-feetech-sts3215/build/lib/pypot/primitive/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/primitive/manager.py
pypot-support-feetech-sts3215/build/lib/pypot/primitive/move.py
pypot-support-feetech-sts3215/build/lib/pypot/primitive/primitive.py
pypot-support-feetech-sts3215/build/lib/pypot/primitive/utils.py
pypot-support-feetech-sts3215/build/lib/pypot/robot/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/robot/config.py
pypot-support-feetech-sts3215/build/lib/pypot/robot/controller.py
pypot-support-feetech-sts3215/build/lib/pypot/robot/io.py
pypot-support-feetech-sts3215/build/lib/pypot/robot/motor.py
pypot-support-feetech-sts3215/build/lib/pypot/robot/remote.py
pypot-support-feetech-sts3215/build/lib/pypot/robot/robot.py
pypot-support-feetech-sts3215/build/lib/pypot/robot/sensor.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/arduino/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/arduino/arduino_sensor.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/camera/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/camera/abstractcam.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/camera/dummy.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/camera/opencvcam.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/contact/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/contact/contact.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/depth/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/depth/sonar.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/imagefeature/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/imagefeature/blob.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/imagefeature/face.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/imagefeature/marker.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/kinect/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/kinect/sensor.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/optibridge.py
pypot-support-feetech-sts3215/build/lib/pypot/sensor/optitrack.py
pypot-support-feetech-sts3215/build/lib/pypot/server/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/server/httpserver.py
pypot-support-feetech-sts3215/build/lib/pypot/server/rest.py
pypot-support-feetech-sts3215/build/lib/pypot/server/server.py
pypot-support-feetech-sts3215/build/lib/pypot/server/snap.py
pypot-support-feetech-sts3215/build/lib/pypot/server/snap_projects/blocs de base Poppy_FR.xml
pypot-support-feetech-sts3215/build/lib/pypot/server/snap_projects/poppy-base_demo_FR.xml
pypot-support-feetech-sts3215/build/lib/pypot/server/snap_projects/poppy-demo-project.xml
pypot-support-feetech-sts3215/build/lib/pypot/server/snap_projects/pypot-snap-blocks.xml
pypot-support-feetech-sts3215/build/lib/pypot/server/ws.py
pypot-support-feetech-sts3215/build/lib/pypot/server/zmqserver.py
pypot-support-feetech-sts3215/build/lib/pypot/tools/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/tools/dxlconfig.py
pypot-support-feetech-sts3215/build/lib/pypot/utils/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/utils/appdirs.py
pypot-support-feetech-sts3215/build/lib/pypot/utils/flushed_print.py
pypot-support-feetech-sts3215/build/lib/pypot/utils/i2c_controller.py
pypot-support-feetech-sts3215/build/lib/pypot/utils/interpolation.py
pypot-support-feetech-sts3215/build/lib/pypot/utils/pypot_time.py
pypot-support-feetech-sts3215/build/lib/pypot/utils/stoppablethread.py
pypot-support-feetech-sts3215/build/lib/pypot/utils/trajectory.py
pypot-support-feetech-sts3215/build/lib/pypot/vpl/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/vpl/download.py
pypot-support-feetech-sts3215/build/lib/pypot/vpl/scratch.py
pypot-support-feetech-sts3215/build/lib/pypot/vpl/snap.py
pypot-support-feetech-sts3215/build/lib/pypot/vrep/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/vrep/controller.py
pypot-support-feetech-sts3215/build/lib/pypot/vrep/io.py
pypot-support-feetech-sts3215/build/lib/pypot/vrep/remoteApiBindings/__init__.py
pypot-support-feetech-sts3215/build/lib/pypot/vrep/remoteApiBindings/lib/linux/32Bit/remoteApi.so
pypot-support-feetech-sts3215/build/lib/pypot/vrep/remoteApiBindings/lib/linux/64Bit/remoteApi.so
pypot-support-feetech-sts3215/build/lib/pypot/vrep/remoteApiBindings/lib/mac/64Bit/remoteApi.dylib
pypot-support-feetech-sts3215/build/lib/pypot/vrep/remoteApiBindings/lib/windows/32Bit/remoteApi.dll
pypot-support-feetech-sts3215/build/lib/pypot/vrep/remoteApiBindings/lib/windows/64Bit/remoteApi.dll
pypot-support-feetech-sts3215/build/lib/pypot/vrep/remoteApiBindings/vrep.py
pypot-support-feetech-sts3215/build/lib/pypot/vrep/remoteApiBindings/vrepConst.py
pypot-support-feetech-sts3215/changelog.md
pypot-support-feetech-sts3215/doc/ErgoRobots.jpg
pypot-support-feetech-sts3215/doc/FAQ.rst
pypot-support-feetech-sts3215/doc/Makefile
pypot-support-feetech-sts3215/doc/README.md
pypot-support-feetech-sts3215/doc/_static/my-css.css
pypot-support-feetech-sts3215/doc/_templates/layout.html
pypot-support-feetech-sts3215/doc/about.rst
pypot-support-feetech-sts3215/doc/api.rst
pypot-support-feetech-sts3215/doc/banderole-pypot.jpg
pypot-support-feetech-sts3215/doc/conf.py
pypot-support-feetech-sts3215/doc/controller.rst
pypot-support-feetech-sts3215/doc/controlling_robot.rst
pypot-support-feetech-sts3215/doc/dynamixel.rst
pypot-support-feetech-sts3215/doc/extending.rst
pypot-support-feetech-sts3215/doc/index.rst
pypot-support-feetech-sts3215/doc/installation.rst
pypot-support-feetech-sts3215/doc/logging.rst
pypot-support-feetech-sts3215/doc/move.rst
pypot-support-feetech-sts3215/doc/poppy-creatures.jpg
pypot-support-feetech-sts3215/doc/primitive.rst
pypot-support-feetech-sts3215/doc/pypot-archi.jpg
pypot-support-feetech-sts3215/doc/pypot.dynamixel.rst
pypot-support-feetech-sts3215/doc/pypot.primitive.rst
pypot-support-feetech-sts3215/doc/pypot.robot.rst
pypot-support-feetech-sts3215/doc/pypot.sensor.rst
pypot-support-feetech-sts3215/doc/pypot.server.rst
pypot-support-feetech-sts3215/doc/pypot.tools.rst
pypot-support-feetech-sts3215/doc/pypot.utils.rst
pypot-support-feetech-sts3215/doc/pypot.vrep.rst
pypot-support-feetech-sts3215/doc/pypot_logo-144x144.png
pypot-support-feetech-sts3215/doc/pypot_logo-48x48.png
pypot-support-feetech-sts3215/doc/pypot_logo.png
pypot-support-feetech-sts3215/doc/quickstart.rst
pypot-support-feetech-sts3215/doc/remote_access.rst
pypot-support-feetech-sts3215/doc/vrep.rst
pypot-support-feetech-sts3215/pypot.egg-info/PKG-INFO
pypot-support-feetech-sts3215/pypot.egg-info/SOURCES.txt
pypot-support-feetech-sts3215/pypot.egg-info/dependency_links.txt
pypot-support-feetech-sts3215/pypot.egg-info/entry_points.txt
pypot-support-feetech-sts3215/pypot.egg-info/not-zip-safe
pypot-support-feetech-sts3215/pypot.egg-info/requires.txt
pypot-support-feetech-sts3215/pypot.egg-info/top_level.txt
pypot-support-feetech-sts3215/pypot/__init__.py
pypot-support-feetech-sts3215/pypot/_version.py
pypot-support-feetech-sts3215/pypot/creatures/__init__.py
pypot-support-feetech-sts3215/pypot/creatures/abstractcreature.py
pypot-support-feetech-sts3215/pypot/creatures/configure_utility.py
pypot-support-feetech-sts3215/pypot/creatures/ik.py
pypot-support-feetech-sts3215/pypot/creatures/services_launcher.py
pypot-support-feetech-sts3215/pypot/dynamixel/__init__.py
pypot-support-feetech-sts3215/pypot/dynamixel/controller.py
pypot-support-feetech-sts3215/pypot/dynamixel/conversion.py
pypot-support-feetech-sts3215/pypot/dynamixel/error.py
pypot-support-feetech-sts3215/pypot/dynamixel/io/__init__.py
pypot-support-feetech-sts3215/pypot/dynamixel/io/abstract_io.py
pypot-support-feetech-sts3215/pypot/dynamixel/io/io.py
pypot-support-feetech-sts3215/pypot/dynamixel/io/io_320.py
pypot-support-feetech-sts3215/pypot/dynamixel/io/io_xl330.py
pypot-support-feetech-sts3215/pypot/dynamixel/io/io_xm430.py
pypot-support-feetech-sts3215/pypot/dynamixel/motor.py
pypot-support-feetech-sts3215/pypot/dynamixel/protocol/__init__.py
pypot-support-feetech-sts3215/pypot/dynamixel/protocol/v1.py
pypot-support-feetech-sts3215/pypot/dynamixel/protocol/v2.py
pypot-support-feetech-sts3215/pypot/dynamixel/syncloop.py
pypot-support-feetech-sts3215/pypot/feetech/__init__.py
pypot-support-feetech-sts3215/pypot/feetech/sts3215_io.py
pypot-support-feetech-sts3215/pypot/kinematics.py
pypot-support-feetech-sts3215/pypot/primitive/__init__.py
pypot-support-feetech-sts3215/pypot/primitive/manager.py
pypot-support-feetech-sts3215/pypot/primitive/move.py
pypot-support-feetech-sts3215/pypot/primitive/primitive.py
pypot-support-feetech-sts3215/pypot/primitive/utils.py
pypot-support-feetech-sts3215/pypot/robot/__init__.py
pypot-support-feetech-sts3215/pypot/robot/config.py
pypot-support-feetech-sts3215/pypot/robot/controller.py
pypot-support-feetech-sts3215/pypot/robot/io.py
pypot-support-feetech-sts3215/pypot/robot/motor.py
pypot-support-feetech-sts3215/pypot/robot/remote.py
pypot-support-feetech-sts3215/pypot/robot/robot.py
pypot-support-feetech-sts3215/pypot/robot/sensor.py
pypot-support-feetech-sts3215/pypot/sensor/__init__.py
pypot-support-feetech-sts3215/pypot/sensor/arduino/__init__.py
pypot-support-feetech-sts3215/pypot/sensor/arduino/arduino_sensor.py
pypot-support-feetech-sts3215/pypot/sensor/camera/__init__.py
pypot-support-feetech-sts3215/pypot/sensor/camera/abstractcam.py
pypot-support-feetech-sts3215/pypot/sensor/camera/dummy.py
pypot-support-feetech-sts3215/pypot/sensor/camera/opencvcam.py
pypot-support-feetech-sts3215/pypot/sensor/contact/__init__.py
pypot-support-feetech-sts3215/pypot/sensor/contact/contact.py
pypot-support-feetech-sts3215/pypot/sensor/depth/__init__.py
pypot-support-feetech-sts3215/pypot/sensor/depth/sonar.py
pypot-support-feetech-sts3215/pypot/sensor/imagefeature/__init__.py
pypot-support-feetech-sts3215/pypot/sensor/imagefeature/blob.py
pypot-support-feetech-sts3215/pypot/sensor/imagefeature/face.py
pypot-support-feetech-sts3215/pypot/sensor/imagefeature/marker.py
pypot-support-feetech-sts3215/pypot/sensor/kinect/__init__.py
pypot-support-feetech-sts3215/pypot/sensor/kinect/sensor.py
pypot-support-feetech-sts3215/pypot/sensor/optibridge.py
pypot-support-feetech-sts3215/pypot/sensor/optitrack.py
pypot-support-feetech-sts3215/pypot/server/__init__.py
pypot-support-feetech-sts3215/pypot/server/httpserver.py
pypot-support-feetech-sts3215/pypot/server/rest.py
pypot-support-feetech-sts3215/pypot/server/server.py
pypot-support-feetech-sts3215/pypot/server/snap.py
pypot-support-feetech-sts3215/pypot/server/snap_projects/blocs de base Poppy_FR.xml
pypot-support-feetech-sts3215/pypot/server/snap_projects/legacy_projects/poppy-ergo-jr-lib.xml
pypot-support-feetech-sts3215/pypot/server/snap_projects/legacy_projects/pypot-snap-record-orchestration-demo.xml
pypot-support-feetech-sts3215/pypot/server/snap_projects/poppy-base_demo_FR.xml
pypot-support-feetech-sts3215/pypot/server/snap_projects/poppy-demo-project.xml
pypot-support-feetech-sts3215/pypot/server/snap_projects/pypot-snap-blocks.xml
pypot-support-feetech-sts3215/pypot/server/ws.py
pypot-support-feetech-sts3215/pypot/server/zmqserver.py
pypot-support-feetech-sts3215/pypot/tools/__init__.py
pypot-support-feetech-sts3215/pypot/tools/dxlconfig.py
pypot-support-feetech-sts3215/pypot/utils/__init__.py
pypot-support-feetech-sts3215/pypot/utils/appdirs.py
pypot-support-feetech-sts3215/pypot/utils/flushed_print.py
pypot-support-feetech-sts3215/pypot/utils/i2c_controller.py
pypot-support-feetech-sts3215/pypot/utils/interpolation.py
pypot-support-feetech-sts3215/pypot/utils/pypot_time.py
pypot-support-feetech-sts3215/pypot/utils/stoppablethread.py
pypot-support-feetech-sts3215/pypot/utils/trajectory.py
pypot-support-feetech-sts3215/pypot/vpl/__init__.py
pypot-support-feetech-sts3215/pypot/vpl/download.py
pypot-support-feetech-sts3215/pypot/vpl/scratch.py
pypot-support-feetech-sts3215/pypot/vpl/snap.py
pypot-support-feetech-sts3215/pypot/vrep/__init__.py
pypot-support-feetech-sts3215/pypot/vrep/child_script/inject_code.lua
pypot-support-feetech-sts3215/pypot/vrep/child_script/timer.lua
pypot-support-feetech-sts3215/pypot/vrep/controller.py
pypot-support-feetech-sts3215/pypot/vrep/io.py
pypot-support-feetech-sts3215/pypot/vrep/remoteApiBindings/__init__.py
pypot-support-feetech-sts3215/pypot/vrep/remoteApiBindings/lib/linux/32Bit/remoteApi.so
pypot-support-feetech-sts3215/pypot/vrep/remoteApiBindings/lib/linux/64Bit/remoteApi.so
pypot-support-feetech-sts3215/pypot/vrep/remoteApiBindings/lib/mac/64Bit/remoteApi.dylib
pypot-support-feetech-sts3215/pypot/vrep/remoteApiBindings/lib/windows/32Bit/remoteApi.dll
pypot-support-feetech-sts3215/pypot/vrep/remoteApiBindings/lib/windows/64Bit/remoteApi.dll
pypot-support-feetech-sts3215/pypot/vrep/remoteApiBindings/vrep.py
pypot-support-feetech-sts3215/pypot/vrep/remoteApiBindings/vrepConst.py
pypot-support-feetech-sts3215/samples/REST/ruby/README.md
pypot-support-feetech-sts3215/samples/REST/ruby/motor.rb
pypot-support-feetech-sts3215/samples/REST/ruby/poppy-processing.rb
pypot-support-feetech-sts3215/samples/REST/ruby/poppy.rb
pypot-support-feetech-sts3215/samples/benchmarks/controller.png
pypot-support-feetech-sts3215/samples/benchmarks/controller_sync.ipynb
pypot-support-feetech-sts3215/samples/benchmarks/cpu_load.ipynb
pypot-support-feetech-sts3215/samples/benchmarks/cpu_usage.png
pypot-support-feetech-sts3215/samples/benchmarks/dxl-controller.py
pypot-support-feetech-sts3215/samples/benchmarks/dxl-single-motor.py
pypot-support-feetech-sts3215/samples/benchmarks/load_data.ipynb
pypot-support-feetech-sts3215/samples/benchmarks/packet.pdf
pypot-support-feetech-sts3215/samples/benchmarks/packet.png
pypot-support-feetech-sts3215/samples/benchmarks/robot.py
pypot-support-feetech-sts3215/samples/benchmarks/run-all.py
pypot-support-feetech-sts3215/samples/benchmarks/single_packet.ipynb
pypot-support-feetech-sts3215/samples/benchmarks/vrep.py
pypot-support-feetech-sts3215/samples/feetech-demo.ipynb
pypot-support-feetech-sts3215/samples/notebooks/Accessing pypot REST API through HTTP requests.ipynb
pypot-support-feetech-sts3215/samples/notebooks/Another language.ipynb
pypot-support-feetech-sts3215/samples/notebooks/Benchmark your Poppy robot.ipynb
pypot-support-feetech-sts3215/samples/notebooks/Controlling a Poppy Creature using SNAP.ipynb
pypot-support-feetech-sts3215/samples/notebooks/QuickStart playing with a PoppyErgo.ipynb
pypot-support-feetech-sts3215/samples/notebooks/Record, Save, and Play Moves on a Poppy Creature.ipynb
pypot-support-feetech-sts3215/samples/notebooks/image/snap-basic-blocks.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-find-pypot-blocks.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-header.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-hello-world.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-import.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-orchestration-demo.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-ready.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-right-click.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-sinus.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-slider-example.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap-slider.png
pypot-support-feetech-sts3215/samples/notebooks/image/snap.png
pypot-support-feetech-sts3215/samples/notebooks/readme.md
pypot-support-feetech-sts3215/samples/notebooks/robot-client.ipynb
pypot-support-feetech-sts3215/samples/notebooks/robot-server.ipynb
pypot-support-feetech-sts3215/samples/notebooks/sum-of-sinus.ipynb
pypot-support-feetech-sts3215/samples/profiles/ergo-jr-rpi2-idle-light-syncloop.prof
pypot-support-feetech-sts3215/samples/profiles/profiles.md
pypot-support-feetech-sts3215/samples/remoterobot-server.py
pypot-support-feetech-sts3215/samples/test_connection.py
pypot-support-feetech-sts3215/setup.cfg
pypot-support-feetech-sts3215/setup.py
pypot-support-feetech-sts3215/tests/test_crashed_prim.py
pypot-support-feetech-sts3215/tests/test_dummy.py
pypot-support-feetech-sts3215/tests/test_ik.py
pypot-support-feetech-sts3215/tests/test_import.py
pypot-support-feetech-sts3215/tests/test_primitive.py
pypot-support-feetech-sts3215/tests/test_rest_api.py
pypot-support-feetech-sts3215/tests/test_snap.py
pypot-support-feetech-sts3215/tests/test_websocket.py
pypot-support-feetech-sts3215/tests/utils.py
```
