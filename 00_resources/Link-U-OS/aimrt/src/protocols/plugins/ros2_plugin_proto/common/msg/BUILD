load("@integration//rules/utils:ros.bzl", "ros_utils")

package(
    default_visibility = ["//visibility:public"],
)

ros_utils(
    name = "ros2_msg_wrapper_utils",
    interface_name = "ros2_plugin_proto",
    msgs = [
        "//src/protocols/plugins/ros2_plugin_proto/msg:RosMsgWrapper.msg",
    ],
    only_aimrt_rpc = True,
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
