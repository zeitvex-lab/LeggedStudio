load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

pkg_files(
    name = "ros2_rpc_config",
    srcs = [
        "//src/examples/cpp/ros2_rpc/install/linux/bin/cfg:ros2_rpc_config",
    ],
    prefix = "config/ros2_rpc",
)

pkg_files(
    name = "ros2_rpc_script",
    srcs = [
        "//src/examples/cpp/ros2_rpc/install/linux/bin:ros2_rpc_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/ros2_rpc",
)

pkg_filegroup(
    name = "ros2_rpc_filegroup",
    srcs = [
        ":ros2_rpc_config",
        ":ros2_rpc_script",
    ],
)

pkg_tar(
    name = "ros2_rpc_without_bin_tar",
    srcs = [
        ":ros2_rpc_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "ros2_rpc_bin_tar",
    srcs = [
        "//src/examples/cpp/ros2_rpc/app/normal_ros2_rpc_client_app",
        "//src/examples/cpp/ros2_rpc/app/normal_ros2_rpc_server_app",
        "//src/examples/cpp/ros2_rpc/pkg/ros2_rpc_client_pkg",
        "//src/examples/cpp/ros2_rpc/pkg/ros2_rpc_pkg",
        "//src/examples/cpp/ros2_rpc/pkg/ros2_rpc_server_pkg",
        "//src/runtime/main:aimrt_main",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "ros2_rpc_bin_flatten_tar",
    src = ":ros2_rpc_bin_tar",
    prefix = "bin",
)

pkg_tar(
    name = "ros2_rpc_tar",
    srcs = [
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
    deps = [
        ":ros2_rpc_bin_flatten_tar",
        ":ros2_rpc_without_bin_tar",
    ],
)
