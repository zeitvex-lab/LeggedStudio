load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")
load("@rules_pkg//pkg:mappings.bzl", "pkg_files")
load("@integration//rules/utils:cc_single.bzl", "cc_single_library")

package(default_visibility = ["//visibility:public"])

alias(
    name = "protoc_plugin_cpp_gen_aimrt_cpp_rpc",
    actual = "//src/tools/protoc_plugin_cpp_gen_aimrt_cpp_rpc:protoc_plugin_cpp_gen_aimrt_cpp_rpc",
)

alias(
    name = "ros2_py_gen_aimrt_cpp_rpc",
    actual = "//src/tools/ros2_py_gen_aimrt_cpp_rpc:ros2_py_gen_aimrt_cpp_rpc",
)

genrule(
    name = "generate_version_header",
    srcs = ["//:VERSION"],
    outs = ["aimrt_runtime_version.h"],
    cmd = """
        VERSION=$$(cat $(location //:VERSION) | tr -d '\\n\\r')
        echo '#pragma once' > $@
        echo '#define AIMRT_RUNTIME_VERSION "'"$$VERSION"'"' >> $@
    """,
)

pkg_files(
    name = "ros2_libs",
    srcs = [
        "@ros2_rmw_fastrtps//:rmw_fastrtps",
    ],
    prefix = "bin",
    renames = {
        "@ros2_rmw_fastrtps//:rmw_fastrtps": "librmw_fastrtps.so",
    },
)

pkg_tar(
    name = "aimrt_plugins_tar",
    srcs = [
        ":ros2_libs",
        "//src/plugins/echo_plugin:aimrt_echo_plugin",
        "//src/plugins/grpc_plugin:aimrt_grpc_plugin",
        "//src/plugins/iceoryx_plugin:aimrt_iceoryx_plugin",
        "//src/plugins/log_control_plugin:aimrt_log_control_plugin",
        "//src/plugins/mqtt_plugin:aimrt_mqtt_plugin",
        "//src/plugins/net_plugin:aimrt_net_plugin",
        "//src/plugins/opentelemetry_plugin:aimrt_opentelemetry_plugin",
        "//src/plugins/parameter_plugin:aimrt_parameter_plugin",
        "//src/plugins/proxy_plugin:aimrt_proxy_plugin",
        "//src/plugins/record_playback_plugin:aimrt_record_playback_plugin",
        "//src/plugins/ros2_plugin:aimrt_ros2_plugin",
        "//src/plugins/time_manipulator_plugin:aimrt_time_manipulator_plugin",
        "//src/plugins/topic_logger_plugin:aimrt_topic_logger_plugin",
        "//src/plugins/zenoh_plugin:aimrt_zenoh_plugin",
        "//src/runtime/main:aimrt_main",
        "@integration//:iox-roudi",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "aimrt_plugins_flatten_tar",
    src = ":aimrt_plugins_tar",
    prefix = "bin",
)

pkg_tar(
    name = "aimrt_typesupport_tar",
    srcs = [
        "//src/protocols/pb/actuator:aimrt_actuator_type_support",
        "//src/protocols/pb/common:aimrt_common_type_support",
        "//src/protocols/pb/geometry:aimrt_geometry_type_support",
        "//src/protocols/pb/sensor:aimrt_sensor_type_support",
        "//src/protocols/plugins/topic_logger_plugin:aimrt_topic_logger_type_support",
        "//src/protocols/ros2/aimrt_msgs:aimrt_ros2_aimrt_msgs_type_support",
        "//src/protocols/ros2/ros2_msgs:aimrt_ros2_common_type_support",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "aimrt_typesupport_flatten_tar",
    src = ":aimrt_typesupport_tar",
    prefix = "bin",
)

cc_single_library(
    name = "libaimrt",
    deps = [
        "//src/common/net",
        "//src/common/ros2_util",
        "//src/common/util",
        "//src/interface/aimrt_core_plugin_interface",
        "//src/interface/aimrt_module_c_interface",
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_protobuf_interface",
        "//src/interface/aimrt_module_ros2_interface",
        "//src/interface/aimrt_pkg_c_interface",
        "//src/interface/aimrt_type_support_pkg_c_interface",
        "//src/protocols/plugins/record_playback_plugin:aimrt_record_playback_rpc",
        "//src/runtime/core",
    ],
)
