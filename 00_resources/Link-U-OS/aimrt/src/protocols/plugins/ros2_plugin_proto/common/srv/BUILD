load("@integration//rules/utils:ros.bzl", "ros_utils")

package(
    default_visibility = ["//visibility:public"],
)

ros_utils(
    name = "ros2_rpc_wrapper_utils",
    interface_name = "ros2_plugin_proto",
    only_aimrt_rpc = True,
    srv = "//src/protocols/plugins/ros2_plugin_proto/srv:RosRpcWrapper.srv",
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
