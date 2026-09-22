load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "test_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/mc/motion:planning_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/test:test.proto",
    type_support_name = "aimdk_protocol_mc_test",
)

protobuf_utils(
    name = "mc_test_service_utils",
    dep_protos = [
        ":test_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/test:mc_test_service.proto",
)
