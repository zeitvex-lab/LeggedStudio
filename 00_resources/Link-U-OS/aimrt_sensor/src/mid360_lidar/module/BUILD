package(default_visibility = ["//visibility:public"])

cc_library(
    name = "mid360_lidar_module",
    srcs = glob([
        "*.cpp",
    ]),
    hdrs = glob([
        "*.hpp",
    ]),
    deps = [
        "@aimrt_comm//:aimrte",
        "//src/mid360_lidar/rs_driver:rs_driver",
        "@ros2_common_interfaces//:cpp_sensor_msgs",
    ],
)