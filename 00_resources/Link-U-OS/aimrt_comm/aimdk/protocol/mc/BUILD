load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "mc_service_utils",
    dep_protos = [
        "//aimdk/protocol/mc/base:mc_base_service_proto",
        "//aimdk/protocol/mc/data:mc_data_service_proto",
        "//aimdk/protocol/mc/force:mc_force_service_proto",
        "//aimdk/protocol/mc/kinematics:mc_kinematics_service_proto",
        "//aimdk/protocol/mc/motion:mc_motion_service_proto",
        "//aimdk/protocol/mc/remote:mc_remote_service_proto",
        "//aimdk/protocol/mc/test:mc_test_service_proto",
        "//aimdk/protocol/mc/tools:mc_tools_service_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc:mc_service.proto",
)
