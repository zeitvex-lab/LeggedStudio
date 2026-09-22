# ROS2 Msg Build Configuration

## Overview

In ROS2, msg (messages) are the basic data structures for inter-node communication, used to pass information between publishers and subscribers.

This document uses `joint msgs` as an example to illustrate how to configure and use ROS2 Msg in a project.

## Configuration Steps

### 1. Export msg files in the aimrt_protocol repository

Add export configuration in the `aimdk/protocol/hal/joint/msg/BUILD` file:

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
**Explanation:** Use `exports_files` to make msg files visible to other BUILD targets.

### 2. Define build targets in the aimrt_comm repository

Define msg build targets in the [aimrt_comm](https://github.com/Link-U-OS/aimrt_comm) repository.

**Important Note:** It is recommended to define one `ros_utils` target for multiple msg files in the same directory.

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

**Parameter Description:**
- `name`: Target name
- `interface_name`: Generated interface namespace name
- `msgs`: Path to the msg files to be processed
- `deps`: Other dependent ROS2 msg targets
- `type_support_name`: Type support naming

### 3. Usage in other repositories

Add dependencies in repositories that need to use these msgs.

**Key point:** The reference is to the target expanded by the `ros_utils` rule, with the naming format `{interface_name}_lib`.

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
        # Other dependencies...
    ],
)
```
