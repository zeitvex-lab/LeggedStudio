load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(
    default_visibility = ["//visibility:public"],
)

protobuf_utils(
    name = "common_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_common",
    proto = "//src/protocols/pb/example:common.proto",
)

protobuf_utils(
    name = "pb_example_utils",
    dep_protos = [
        ":common_proto",
    ],
    is_rpc = True,
    only_aimrt_rpc = True,
    proto = "//src/protocols/pb/example:rpc.proto",
)
