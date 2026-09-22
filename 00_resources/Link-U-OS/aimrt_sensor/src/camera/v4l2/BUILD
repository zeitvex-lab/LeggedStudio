load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "v4l2",
    srcs = glob([
        "*.cpp",
    ]),
    hdrs = glob([
        "*.hpp",
    ]),
    deps = [
        "@aimrt_comm//:aimrte",
        "@ros2_common_interfaces//:cpp_sensor_msgs",
        "@integration//:tzcam",
        "@integration//:jetson_multimedia",
    ],
)