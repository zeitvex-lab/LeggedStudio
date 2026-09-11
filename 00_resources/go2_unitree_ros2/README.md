# go2_unitree_ros2 — 参考资源

> **来源**：`00_open/go2_unitree_ros2/`　｜　**类型**：真机接口参考（ROS2 / Unitree SDK2）
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：Unitree SDK2 的 ROS2 封装参考：低层 /lowcmd（200Hz + CRC32）与 Sport API /api/sport/request 双通道、运动/关节状态与手柄读取、IMU 发布
> **收录**：65 个文件 / 951 KB（其中推理策略/模型文件 0 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **部署与推理**（3 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（2 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（60 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （3 个文件）
include/  （48 个文件）
    common/
    devel/
    nlohmann/
src/  （14 个文件）
    (直接文件)/
    common/
    devel/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.hpp` | 45 |
| `.cpp` | 14 |
| `.h` | 3 |
| `.txt` | 1 |
| `.md` | 1 |
| `.xml` | 1 |

## 文件索引（项目内相对路径）

```text
CMakeLists.txt
README.md
include/common/motor_crc.h
include/common/ros2_sport_client.h
include/devel/sport_rotation.h
include/nlohmann/adl_serializer.hpp
include/nlohmann/byte_container_with_subtype.hpp
include/nlohmann/detail/abi_macros.hpp
include/nlohmann/detail/conversions/from_json.hpp
include/nlohmann/detail/conversions/to_chars.hpp
include/nlohmann/detail/conversions/to_json.hpp
include/nlohmann/detail/exceptions.hpp
include/nlohmann/detail/hash.hpp
include/nlohmann/detail/input/binary_reader.hpp
include/nlohmann/detail/input/input_adapters.hpp
include/nlohmann/detail/input/json_sax.hpp
include/nlohmann/detail/input/lexer.hpp
include/nlohmann/detail/input/parser.hpp
include/nlohmann/detail/input/position_t.hpp
include/nlohmann/detail/iterators/internal_iterator.hpp
include/nlohmann/detail/iterators/iter_impl.hpp
include/nlohmann/detail/iterators/iteration_proxy.hpp
include/nlohmann/detail/iterators/iterator_traits.hpp
include/nlohmann/detail/iterators/json_reverse_iterator.hpp
include/nlohmann/detail/iterators/primitive_iterator.hpp
include/nlohmann/detail/json_custom_base_class.hpp
include/nlohmann/detail/json_pointer.hpp
include/nlohmann/detail/json_ref.hpp
include/nlohmann/detail/macro_scope.hpp
include/nlohmann/detail/macro_unscope.hpp
include/nlohmann/detail/meta/call_std/begin.hpp
include/nlohmann/detail/meta/call_std/end.hpp
include/nlohmann/detail/meta/cpp_future.hpp
include/nlohmann/detail/meta/detected.hpp
include/nlohmann/detail/meta/identity_tag.hpp
include/nlohmann/detail/meta/is_sax.hpp
include/nlohmann/detail/meta/std_fs.hpp
include/nlohmann/detail/meta/type_traits.hpp
include/nlohmann/detail/meta/void_t.hpp
include/nlohmann/detail/output/binary_writer.hpp
include/nlohmann/detail/output/output_adapters.hpp
include/nlohmann/detail/output/serializer.hpp
include/nlohmann/detail/string_concat.hpp
include/nlohmann/detail/string_escape.hpp
include/nlohmann/detail/value_t.hpp
include/nlohmann/json.hpp
include/nlohmann/json_fwd.hpp
include/nlohmann/ordered_map.hpp
include/nlohmann/thirdparty/hedley/hedley.hpp
include/nlohmann/thirdparty/hedley/hedley_undef.hpp
package.xml
src/common/motor_crc.cpp
src/common/ros2_sport_client.cpp
src/devel/gait_type_devel.cpp
src/devel/imu_publisher.cpp
src/devel/main_rotation.cpp
src/devel/move_rotate180.cpp
src/devel/sport_rotation.cpp
src/devel/tag_move_demo.cpp
src/low_level_ctrl.cpp
src/read_low_state.cpp
src/read_motion_state.cpp
src/read_wireless_controller.cpp
src/record_bag.cpp
src/sport_mode_ctrl.cpp
```

## 导入边界与关键数值（人工补充，重新同步时需重做）

- **收录口径**：上游很小（65 文件 / 951 KB），**全量收录**，唯一未收的是 `.git/`（及工具内置跳过的缓存目录）。
- **许可**：上游**无 LICENSE 文件**（`package.xml` 的 license 字段为 `TODO`）→ 仅作**内部参考**，不再分发；对外引用前请先联系作者。
- **关键对照数值**：`/lowcmd` **200 Hz**（`milliseconds(5)`，mode `0x01` 力矩模式，`q=PosStopF / dq=VelStopF`，示例 `kp=10 / kd=1 / tau=1`）；`/lowstate` 高 500 Hz（`lf/lowstate` 为低频）；Sport 请求 `dt = 0.002`；`LowCmd / LowState` **20 个电机槽位**（实际 12 关节）；CRC32 多项式 `0x04c11db7`（20 个 `MotorCmd` 打包）；IMU 转 `sensor_msgs/Imu` 发 `/go2/imu`（frame `imu_link`）；`sport_rotation` 的到达判据 = 目标 yaw ±5°（`Move(0,0,0.5)`）；`sportmodestate` 含 `gait_type` / `body_height` / `velocity` / `yaw_speed` / `foot_position_body[12]`；`TrajectoryFollow` 示例 30 点 / `time_seg=0.2` / vx 峰值 0.5 m/s。
- **注意**：`include/nlohmann/**` 是 vendored 第三方 JSON 库（45 个 hpp，非本仓代码）；`src/devel/*` 多为调试示例，与 `sport_rotation` 功能重叠；依赖外部 `apriltag_service`（本仓不含）→ **无法独立编译**；`tag_move_demo` 的 `tag_size=0.162`（m）、触发 ID 303。
