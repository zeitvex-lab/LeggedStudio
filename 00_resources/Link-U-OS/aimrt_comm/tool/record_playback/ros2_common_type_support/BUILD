package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrte_ros2_common_type_support",
    srcs = [
        "type_support_pkg.cpp",
    ],
    deps = [
        "@aimrt//:libaimrt",
        "@ros2_common_interfaces//:cpp_std_msgs",
        "@ros2_rclcpp//:rclcpp",
        "@ros2_common_interfaces//:cpp_nav_msgs",
        "@ros2_common_interfaces//:cpp_geometry_msgs",
        "@ros2_common_interfaces//:cpp_sensor_msgs",
        "@ros2_common_interfaces//:cpp_visualization_msgs",
        "@ros2_geometry2//:cpp_tf2_msgs",
        "@ros2_navigation//:cpp_map_msgs",
    ],
    linkshared = True,
)
