# Protobuf Channel 编译配置

## 概述

[Protobuf](https://protobuf.dev/) 是由 Google 开发的轻量级、高效的数据序列化格式,广泛用作接口定义语言(IDL)。使用时需要先定义 `.proto` 文件来描述消息结构。

本文档以 `hand_channel.proto` 为例,说明如何在项目中配置和使用 Protobuf Channel。

## 配置步骤

### 1. 在 aimrt_protocol 仓库导出 proto 文件

在 `aimdk/protocol/hal/hand/BUILD` 文件中添加导出配置:

```bash
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "hand_channel.proto",
])
```

**说明:** 使用 `exports_files` 使 proto 文件对其他 BUILD 目标可见。


### 2. 在 aimrt_comm 仓库定义构建目标

在 [aimrt_comm](https://github.com/Link-U-OS/aimrt_comm) 仓库中定义 protobuf 构建目标。

**重要提示:** 每个 proto 文件都需要单独定义一个 `protobuf_utils` 目标。

```bash
load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "hand_channel_utils",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:hand_channel.proto",
    dep_protos = [
        ":hand_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    type_support_name = "aimdk_protocol_hand_channel",
)
```

**参数说明:**
- `name`: 目标名称
- `proto`: 要处理的 proto 文件路径
- `dep_protos`: 依赖的其他 proto 目标
- `type_support_name`: 类型支持的命名


### 3. 在其他仓库中使用

在需要使用该 proto 的仓库中添加依赖。

**关键点:** 引用的是 `protobuf_utils` 规则展开后的目标,命名格式为 `{proto_name}_cc_proto`。

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
        "@aimrt_comm//aimdk/protocol/hal/hand:hand_channel_cc_proto",
        # 其他依赖...
    ],
)
```
