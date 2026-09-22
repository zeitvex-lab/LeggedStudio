# Protobuf Rpc 编译配置

## 概述
Protobuf RPC的定义主要体现在Protocol Buffers（Protobuf）中使用service关键字定义RPC接口，通过rpc关键字定义远程调用的方法。

本文档以 `hal_hand_service.proto` 为例,说明如何在项目中配置和使用 Protobuf RPC。

## 配置步骤

### 1. 在 aimrt_protocol 仓库导出 proto 文件

在 `aimdk/protocol/hal/hand/BUILD` 文件中添加导出配置:

```bash
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "hal_hand_service.proto",
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
    name = "hal_hand_service_utils",
    dep_protos = [
        ":hand_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:hal_hand_service.proto",
)
```
**参数说明:**
- `name`: 目标名称
- `proto`: 要处理的 proto 文件路径
- `dep_protos`: 依赖的其他 proto 目标
- `is_rpc`: 标识要处理的proto是否定义RPC接口

### 3. 在其他仓库中使用

在需要使用该 proto 的仓库中添加依赖。

**关键点:** 引用的是 `protobuf_utils` 规则展开后的目标,命名格式为 `{proto_name}_rpc`。

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
        "@aimrt_comm//aimdk/protocol/hal/hand:hal_hand_service_rpc",
        # 其他依赖...
    ],
)
```

