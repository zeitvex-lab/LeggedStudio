load("@integration//rules/utils:proto.bzl", "protobuf_utils")
load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "test_msg_utils",
    dep_protos = [
    ],
    is_rpc = True,
    output_proto_name = "test_msg_new",
    proto = "test_msg.proto",
)

ros_utils(
    name = "test_service_utils",
    interface_name = "test_service",
    msgs = [
        "//src/test_protocol/msg:TestMsg.msg",
    ],
    srv = "//src/test_protocol/srv:TestService.srv",
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
