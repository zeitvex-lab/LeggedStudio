# Protobuf RPC Build Configuration

## Overview
Protobuf RPC definition primarily involves using the `service` keyword in Protocol Buffers (Protobuf) to define RPC interfaces, and the `rpc` keyword to define remote callable methods.

This document uses `hal_hand_service.proto` as an example to illustrate how to configure and use Protobuf RPC in a project.

## Configuration Steps

### 1. Export proto files in the aimrt_protocol repository

Add export configuration in the `aimdk/protocol/hal/hand/BUILD` file:

```bash
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "hal_hand_service.proto",
])
```

**Explanation:** Use `exports_files` to make proto files visible to other BUILD targets.

### 2. Define build targets in the aimrt_comm repository

Define protobuf build targets in the [aimrt_comm](https://github.com/Link-U-OS/aimrt_comm) repository.

**Important Note:** Each proto file needs a separate `protobuf_utils` target.

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
**Parameter Description:**
- `name`: Target name
- `proto`: Path to the proto file to be processed
- `dep_protos`: Other dependent proto targets
- `is_rpc`: Indicates whether the proto to be processed defines an RPC interface

### 3. Usage in other repositories

Add dependencies in repositories that need to use this proto.

**Key point:** The reference is to the target expanded by the `protobuf_utils` rule, with the naming format `{proto_name}_rpc`.

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
        # Other dependencies...
    ],
)
```