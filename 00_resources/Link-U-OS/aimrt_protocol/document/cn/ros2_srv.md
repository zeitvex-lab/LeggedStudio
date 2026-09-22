# ROS2 Srv编译配置

## 概述

ROS2中的srv（服务）是一种基于客户端-服务器模型的通信机制，用于节点间的同步请求-响应交互，区别于主题（topic）的发布-订阅异步通信。服务由服务端提供，客户端调用，服务端接收请求并返回响应。

本文档以 `GetBagList.srv`为例，说明如何在项目中配置和使用ROS2 Srv。

## 配置步骤

### 1. 在 aimrt_protocol 仓导出 srv 文件

在 `ros2/record_playback/srv/BUILD` 文件中添加导出配置：

```bash
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "GetBagList.srv",
])
```
**说明:** 使用 `exports_files` 使 srv 文件对其他 BUILD 目标可见。

### 2. 在 aimrt_comm 仓库定义构建目标

在 [aimrt_comm](https://github.com/Link-U-OS/aimrt_comm) 仓库中定义 msg 构建目标。

**重要提示:** 每个 srv 文件都需要单独定义一个 `ros_utils` 目标。

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

**参数说明:**
- `name`: 目标名称
- `interface_name`: 生成的接口namespace名
- `msgs`: 依赖的 msgs 文件路径
- `deps`: 依赖的其他 ros2 msg/srv 目标
- `srv`: 要处理的 srv 文件路径

### 3. 在其他仓库中使用

在需要使用该 srv 的仓库中添加依赖。

**关键点:** 引用的是 `ros_utils` 规则展开后的目标,命名格式为 `{interface_name}_rpc`。

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
        # 其他依赖...
    ],
)

```