# ROS2 Msg编译配置

## 概述

ROS2中的msg（消息）是节点间通信的基本数据结构，用于在发布者和订阅者之间传递信息。

本文档以`joint msgs`为例， 说明如何在项目中配置和使用ROS2 Msg。

## 配置步骤

### 1. 在 aimrt_protocol 仓导出 msg 文件

在 `aimdk/protocol/hal/joint/msg/BUILD` 文件中添加导出配置：

```bash
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "Command.msg",
    "JointCommand.msg",
    "JointState.msg",
    "State.msg"
])
```
**说明:** 使用 `exports_files` 使 msg 文件对其他 BUILD 目标可见。

### 2. 在 aimrt_comm 仓库定义构建目标

在 [aimrt_comm](https://github.com/Link-U-OS/aimrt_comm) 仓库中定义 msg 构建目标。

**重要提示:** 建议同级目录下多个msg定义一个 `ros_utils` 目标。

```bash
load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

ros_utils(
    name = "joint_msg_utils",
    inerface_name = "joint_msgs",
    msgs = [
        "@aimrt_protocol//aimdk/protocol/hal/joint/msg:Command.msg",
        "@aimrt_protocol//aimdk/protocol/hal/joint/msg:JointCommand.msg",
        "@aimrt_protocol//aimdk/protocol/hal/joint/msg:JointState.msg",
        "@aimrt_protocol//aimdk/protocol/hal/joint/msg:State.msg",
    ],
    type_support_name = "aimdk_protocol_joint_msgs",
    deps = [
        "@ros2_common_interfaces//:std_msgs",
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
```

**参数说明:**
- `name`: 目标名称
- `interface_name`: 生成的接口namespace名
- `msgs`: 要处理的 msg 文件路径
- `deps`: 依赖的其他 ros2 msg 目标
- `type_support_name`: 类型支持的命名

### 3. 在其他仓库中使用

在需要使用该 msgs 的仓库中添加依赖。

**关键点:** 引用的是 `ros_utils` 规则展开后的目标,命名格式为 `{interface_name}_lib`。

```bash
package(default_visibility = ["//visibility:public"])

cc_library(
    name = "ethercat_module",
    srcs = glob([
        "**/*.cc",
        "**/*.cpp",
    ]),
    hdrs = glob([
        "**/*.h",
        "**/*.hpp",
    ]),
    deps = [
        "@aimrt_comm//aimdk/protocol/hal/joint:joint_msgs_lib",
        # 其他依赖...
    ],
)
```