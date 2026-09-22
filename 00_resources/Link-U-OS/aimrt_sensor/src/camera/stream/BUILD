load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "stream",
    srcs = glob([
        "*.cpp",
    ]),
    hdrs = glob([
        "*.hpp",
    ]),
    deps = [
        "@integration//:jetson_multimedia",
        "@ros2_foxglove//:cpp_foxglove_msgs",
        "@aimrt_comm//:aimrte",
    ],
)