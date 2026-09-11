# go2w_sim2sim — 参考资源

> **来源**：`00_open/go2w_sim2sim/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2w（宇树 Go2W 轮足）
> **定位**：Go2W 轮足 sim2sim 部署工程（MuJoCo）
> **收录**：149 个文件 / 110.4 MB（其中推理策略/模型文件 35 个）
> **已省略**：95 个文件 / 230.7 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（28 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（2 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（56 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **评测与测试**（3 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（60 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
.github/  （2 个文件）
    workflows/
docs/  （36 个文件）
    (直接文件)/
    assets/
    demo-assets/
mujoco/  （27 个文件）
    (直接文件)/
    C++/
    Python/
policy/  （33 个文件）
    history_1/
    history_5/
    lmm/
    motion_tracking/
    raycam/
    vtm/
    vtm_gru_sru/
    vtm_lstm_sru/
robot/  （9 个文件）
    go2w_description/
ros2/  （13 个文件）
    (直接文件)/
    src/
tools/  （12 个文件）
    (直接文件)/
    raycaster_wasm_port/
utils/  （13 个文件）
    cpp_gamepad/
    cpp_manager_env/
    mujoco_thread/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.onnx` | 21 |
| `.cpp` | 16 |
| `.pt` | 14 |
| `.js` | 13 |
| `.xml` | 11 |
| `.json` | 10 |
| `.md` | 9 |
| `.h` | 9 |
| `(无扩展名)` | 7 |
| `.mjs` | 5 |
| `.cmake` | 5 |
| `.hpp` | 5 |
| `.txt` | 4 |
| `.py` | 4 |
| `.yml` | 3 |

## 文件索引（项目内相对路径）

```text
.codex
.github/workflows/apply-go2w-demo-hotfix.yml
.github/workflows/build-native-raycaster-wasm.yml
.gitignore
MUJOCO_LOG.TXT
README.md
docs/README.md
docs/_config.yml
docs/assets/css/site.css
docs/assets/js/demo-fallback.js
docs/assets/js/go2w-demo-optimizer-v13.js
docs/assets/js/go2w-demo-optimizer.js
docs/assets/js/go2w-demo.js
docs/assets/js/policy-worker.js
docs/assets/js/raycaster-runtime-patch.js
docs/assets/js/raycaster-worker.js
docs/assets/js/site.js
docs/assets/vendor/onnxruntime-web/ort-wasm-simd-threaded.mjs
docs/assets/vendor/onnxruntime-web/ort.wasm.min.js
docs/assets/vendor/three/OrbitControls.js
docs/assets/vendor/three/three.module.js
docs/coi-serviceworker.js
docs/demo-assets/mujoco_wasm.d.ts
docs/demo-assets/mujoco_wasm.js
docs/demo-assets/policies/motion_tracking/policy.onnx
docs/demo-assets/policies/vtm/student.onnx
docs/demo-assets/policies/vtm/student_info.json
docs/demo-assets/policies/vtm_gru_sru/student_actor.onnx
docs/demo-assets/policies/vtm_gru_sru/student_deploy.json
docs/demo-assets/policies/vtm_gru_sru/student_encoder.onnx
docs/demo-assets/policies/vtm_gru_sru/student_info.json
docs/demo-assets/policies/vtm_gru_sru/student_memory.onnx
docs/demo-assets/policies/vtm_lstm_sru/student_actor.onnx
docs/demo-assets/policies/vtm_lstm_sru/student_deploy.json
docs/demo-assets/policies/vtm_lstm_sru/student_encoder.onnx
docs/demo-assets/policies/vtm_lstm_sru/student_info.json
docs/demo-assets/policies/vtm_lstm_sru/student_memory.onnx
docs/demo-assets/scenes/go2w.xml
docs/demo-assets/scenes/scene_parkour.xml
docs/demo.html
docs/index.html
docs/raycaster-wasm-port.md
mujoco/C++/CMakeLists.txt
mujoco/C++/build_onnx/CMakeCache.txt
mujoco/C++/build_onnx/CTestConfiguration.ini
mujoco/C++/build_onnx/CTestCustom.cmake
mujoco/C++/build_onnx/CTestTestfile.cmake
mujoco/C++/build_onnx/Makefile
mujoco/C++/build_onnx/ament_cmake_core/stamps/templates_2_cmake.py.stamp
mujoco/C++/build_onnx/ament_cmake_package_templates/templates.cmake
mujoco/C++/build_onnx/ament_cmake_uninstall_target/ament_cmake_uninstall_target.cmake
mujoco/C++/build_onnx/camera_quat
mujoco/C++/build_onnx/camera_test
mujoco/C++/build_onnx/cmake_install.cmake
mujoco/C++/build_onnx/lab2mj
mujoco/C++/build_onnx/real2sim
mujoco/C++/camera_quat_lab2mj/camera_quat.cpp
mujoco/C++/camera_test/camera_test.cpp
mujoco/C++/lab2mj.cpp
mujoco/C++/mj_env.cpp
mujoco/C++/mj_env.h
mujoco/C++/real2sim/real2sim.cpp
mujoco/C++/real2sim/real2sim_env.cpp
mujoco/C++/real2sim/real2sim_env.h
mujoco/C++/sim2sim_env.cpp
mujoco/C++/sim2sim_env.h
mujoco/Python/lab2mujoco.py
mujoco/Python/lab2mujoco2.py
mujoco/SIM2SIM_DEPLOYMENT_GUIDE.md
policy/history_1/model.onnx
policy/history_1/policy.pt
policy/history_1/to_onnx.py
policy/history_5/model.onnx
policy/history_5/policy.pt
policy/lmm/policy.onnx
policy/lmm/policy.pt
policy/motion_tracking/policy.onnx
policy/motion_tracking/policy.pt
policy/raycam/policy_17000.pt
policy/vtm/student.onnx
policy/vtm/student.pt
policy/vtm/student_info.json
policy/vtm_gru_sru/student.onnx
policy/vtm_gru_sru/student.pt
policy/vtm_gru_sru/student_actor.onnx
policy/vtm_gru_sru/student_actor.pt
policy/vtm_gru_sru/student_deploy.json
policy/vtm_gru_sru/student_encoder.onnx
policy/vtm_gru_sru/student_encoder.pt
policy/vtm_gru_sru/student_info.json
policy/vtm_gru_sru/student_memory.onnx
policy/vtm_gru_sru/student_memory.pt
policy/vtm_lstm_sru/student.onnx
policy/vtm_lstm_sru/student.pt
policy/vtm_lstm_sru/student_actor.onnx
policy/vtm_lstm_sru/student_actor.pt
policy/vtm_lstm_sru/student_deploy.json
policy/vtm_lstm_sru/student_encoder.onnx
policy/vtm_lstm_sru/student_encoder.pt
policy/vtm_lstm_sru/student_info.json
policy/vtm_lstm_sru/student_memory.onnx
policy/vtm_lstm_sru/student_memory.pt
robot/go2w_description/mjcf/go2w.xml
robot/go2w_description/mjcf/scene.xml
robot/go2w_description/mjcf/scene_camera_test.xml
robot/go2w_description/mjcf/scene_demo.xml
robot/go2w_description/mjcf/scene_float_box.xml
robot/go2w_description/mjcf/scene_parkour.xml
robot/go2w_description/mjcf/scene_parkour2.xml
robot/go2w_description/mjcf/scene_parkour_real_ref.xml
robot/go2w_description/urdf/go2w_description.urdf
ros2/README.md
ros2/REAL_DEPLOY_PERFORMANCE_OPTIMIZATION.md
ros2/src/CMakeLists.txt
ros2/src/include/common/motor_crc.h
ros2/src/include/go2w_real_deploy/go2w_real_deploy_node.h
ros2/src/package.xml
ros2/src/src/common/motor_crc.cpp
ros2/src/src/deep_camera/deep_camera.cpp
ros2/src/src/go2w_real_deploy/go2w_real_deploy.cpp
ros2/src/src/go2w_real_deploy/go2w_real_deploy_node.cpp
ros2/src/src/go2w_stand/go2w_stand.cpp
ros2/start_go2w_real_deploy_wireless_only.sh
ros2/unitree_sim_env.bash
tools/SIM2SIM_ENV_BASE_GUIDE.md
tools/SPLIT_RECORD_ANALYSIS_GUIDE.md
tools/apply_go2w_demo_hotfix.mjs
tools/open_split_record_heatmaps.sh
tools/play_split_record_heatmaps.py
tools/raycaster_wasm_port/README.md
tools/raycaster_wasm_port/patch_demo_loader.mjs
tools/raycaster_wasm_port/prepare_mujoco_wasm_port.mjs
tools/raycaster_wasm_port/raycaster_camera_bindings.inc.cc
tools/raycaster_wasm_port/raycaster_memory_fix.patch
tools/render_frames_to_video.sh
tools/verify_go2w_pages_demo.mjs
utils/cpp_gamepad/gamepad.cpp
utils/cpp_gamepad/gamepad.h
utils/cpp_gamepad/gamepadkey.h
utils/cpp_manager_env/Buffer.hpp
utils/cpp_manager_env/ManagerEnv.cpp
utils/cpp_manager_env/ManagerEnv.hpp
utils/cpp_manager_env/Noise.hpp
utils/cpp_manager_env/SimpleTensor.hpp
utils/cpp_manager_env/debug.hpp
utils/cpp_manager_env/net.cpp
utils/cpp_manager_env/net.h
utils/mujoco_thread/mujoco_thread.cpp
utils/mujoco_thread/mujoco_thread.h
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `docs/assets/images` | 2 | 148 KB | [`docs/assets/images/_OMITTED.md`](./docs/assets/images/_OMITTED.md) |
| `docs/assets/vendor/onnxruntime-web` | 1 | 12.1 MB | [`docs/assets/vendor/onnxruntime-web/_OMITTED.md`](./docs/assets/vendor/onnxruntime-web/_OMITTED.md) |
| `docs/demo-assets` | 1 | 8.2 MB | [`docs/demo-assets/_OMITTED.md`](./docs/demo-assets/_OMITTED.md) |
| `docs/demo-assets/scenes/assets` | 27 | 50.2 MB | [`docs/demo-assets/scenes/assets/_OMITTED.md`](./docs/demo-assets/scenes/assets/_OMITTED.md) |
| `policy` | 2 | 21.0 MB | [`policy/_OMITTED.md`](./policy/_OMITTED.md) |
| `policy/history_5` | 1 | 60 KB | [`policy/history_5/_OMITTED.md`](./policy/history_5/_OMITTED.md) |
| `policy/raycam` | 1 | 89 KB | [`policy/raycam/_OMITTED.md`](./policy/raycam/_OMITTED.md) |
| `robot/go2w_description/meshes` | 10 | 38.9 MB | [`robot/go2w_description/meshes/_OMITTED.md`](./robot/go2w_description/meshes/_OMITTED.md) |
| `robot/go2w_description/mjcf` | 2 | 19 KB | [`robot/go2w_description/mjcf/_OMITTED.md`](./robot/go2w_description/mjcf/_OMITTED.md) |
| `robot/go2w_description/mjcf/assets` | 48 | 100.0 MB | [`robot/go2w_description/mjcf/assets/_OMITTED.md`](./robot/go2w_description/mjcf/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
