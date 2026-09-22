load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "tz_camera_module_lib",
    srcs = glob([
        "*.cpp",
    ]),
    hdrs = glob([
        "*.hpp",
    ]),
    deps = [    
        "//src/camera/v4l2:v4l2",
        "//src/camera/convert:convert",
        "//src/camera/utils:utils",
        "//src/camera/stream:stream",
        "@aimrt_comm//aimdk/protocol/hal/sensors:cameras_intrinsic_rpc",
        "@aimrt_comm//:aimrte",
        "@ros2_common_interfaces//:cpp_sensor_msgs",
        "@ros2_foxglove//:cpp_foxglove_msgs",
        "@integration//:opencv",
    ],
)