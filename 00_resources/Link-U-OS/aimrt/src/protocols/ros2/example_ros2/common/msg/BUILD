load("@integration//rules/utils:ros.bzl", "ros_utils")

package(
    default_visibility = ["//visibility:public"],
)

ros_utils(
    name = "example_ros2_utils",
    interface_name = "example_ros2",
    msgs = [
        "//src/protocols/ros2/example_ros2/msg:BenchmarkMessage.msg",
        "//src/protocols/ros2/example_ros2/msg:BenchmarkSignal.msg",
        "//src/protocols/ros2/example_ros2/msg:BenchmarkStatus.msg",
        "//src/protocols/ros2/example_ros2/msg:RosTestData.msg",
        "//src/protocols/ros2/example_ros2/msg:RosTestMsg.msg",
    ],
    only_aimrt_rpc = True,
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
