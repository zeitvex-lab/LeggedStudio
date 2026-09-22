package(default_visibility = ["//visibility:public"])

cc_library(
    name = "dcw2_module",
    srcs = glob([
        "*.cpp",
    ]),
    hdrs = glob([
        "*.hpp",
    ]),
    deps = [
        "@aimrt_comm//:aimrte",
        "@ros2_common_interfaces//:cpp_sensor_msgs",
        "@integration//:OrbbecSDK",
        "@cv_bridge",
    ],
)