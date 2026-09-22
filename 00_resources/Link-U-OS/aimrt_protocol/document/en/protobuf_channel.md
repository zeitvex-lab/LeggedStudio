# Protobuf Channel Build Configuration

## Overview

[Protobuf](https://protobuf.dev/) is a lightweight, efficient data serialization format developed by Google, widely used as an Interface Definition Language (IDL). When using it, you need to define `.proto` files first to describe the message structure.

This document uses `hand_channel.proto` as an example to illustrate how to configure and use Protobuf Channels in a project.

## Configuration Steps

### 1. Export proto files in the aimrt_protocol repository

Add export configuration in the `aimdk/protocol/hal/hand/BUILD` file:

```bash
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "hand_channel.proto",
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
    name = "hand_channel_utils",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:hand_channel.proto",
    dep_protos = [
        ":hand_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    type_support_name = "aimdk_protocol_hand_channel",
)
```

**Parameter Description:**
- `name`: Target name
- `proto`: Path to the proto file to be processed
- `dep_protos`: Other dependent proto targets
- `type_support_name`: Type support naming


### 3. Usage in other repositories

Add dependencies in repositories that need to use this proto.

**Key point:** The reference is to the target expanded by the `protobuf_utils` rule, with the naming format `{proto_name}_cc_proto`.

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
        # Other dependencies...
    ],
)
```