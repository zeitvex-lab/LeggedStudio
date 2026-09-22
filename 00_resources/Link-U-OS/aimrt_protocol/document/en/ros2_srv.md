# ROS2 Srv Build Configuration

## Overview

In ROS2, srv (services) are a client-server based communication mechanism used for synchronous request-response interactions between nodes, distinguishing them from the asynchronous publish-subscribe communication of topics. Services are provided by the server, called by the client, and the server receives requests and returns responses.

This document uses `GetBagList.srv` as an example to illustrate how to configure and use ROS2 Srv in a project.

## Configuration Steps

### 1. Export srv files in the aimrt_protocol repository

Add export configuration in the `ros2/record_playback/srv/BUILD` file:

```bash
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "GetBagList.srv",
])
```
**Explanation:** Use `exports_files` to make srv files visible to other BUILD targets.

### 2. Define build targets in the aimrt_comm repository

Define msg build targets in the [aimrt_comm](https://github.com/Link-U-OS/aimrt_comm) repository.

**Important Note:** Each srv file needs a separate `ros_utils` target.

```bash
load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

ros_utils(
    name = "get_action_list_utils",
    interface_name = "record_playback_msgs",
    msgs = [
        "@aimrt_protocol//ros2/record_playback/msg:ActionInfo.msg",
    ],
    srv = "@aimrt_protocol//ros2/record_playback/srv:GetActionList.srv",
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ], 
)
```

**Parameter Description:**
- `name`: Target name
- `interface_name`: Generated interface namespace name
- `msgs`: Path to the dependent msg files
- `deps`: Other dependent ROS2 msg/srv targets
- `srv`: Path to the srv file to be processed

### 3. Usage in other repositories

Add dependencies in repositories that need to use this srv.

**Key point:** The reference is to the target expanded by the `ros_utils` rule, with the naming format `{interface_name}_rpc`.

```bash
package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrte-tool-record_playback",
    srcs = [
        "main.cpp",
        ...
    ],
    deps = [
        "//ros2/record_playback/GetBagList:record_playback_msgs_rpc",
        # Other dependencies...
    ],
)
```
