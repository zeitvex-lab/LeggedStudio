package(default_visibility = ["//visibility:public"])

cc_library(
    name = "d415_module",
    srcs = glob([
        "*.cpp",
    ]),
    hdrs = glob([
        "*.hpp",
    ]),
    deps = [
        "@aimrt_comm//:aimrte",
        "@ros2_common_interfaces//:cpp_sensor_msgs",
        "@ros2_foxglove//:cpp_foxglove_msgs",
        "@integration//:realsense2_rsusb",
        "@cv_bridge",
        "//src/camera/convert",
    ],
)
