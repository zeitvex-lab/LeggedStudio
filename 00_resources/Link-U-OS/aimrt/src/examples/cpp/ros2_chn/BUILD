load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

pkg_files(
    name = "ros2_chn_config",
    srcs = [
        "//src/examples/cpp/ros2_chn/install/linux/bin/cfg:ros2_chn_config",
    ],
    prefix = "config/ros2_chn",
)

pkg_files(
    name = "ros2_chn_script",
    srcs = [
        "//src/examples/cpp/ros2_chn/install/linux/bin:ros2_chn_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/ros2_chn",
)

pkg_filegroup(
    name = "ros2_chn_filegroup",
    srcs = [
        ":ros2_chn_config",
        ":ros2_chn_script",
    ],
)

pkg_tar(
    name = "ros2_chn_without_bin_tar",
    srcs = [
        ":ros2_chn_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "ros2_chn_bin_tar",
    srcs = [
        "//src/examples/cpp/ros2_chn/app/normal_ros2_chn_publisher_app",
        "//src/examples/cpp/ros2_chn/app/normal_ros2_chn_subscriber_app",
        "//src/examples/cpp/ros2_chn/pkg/ros2_chn_pkg",
        "//src/examples/cpp/ros2_chn/pkg/ros2_chn_pub_pkg",
        "//src/examples/cpp/ros2_chn/pkg/ros2_chn_sub_pkg",
        "//src/runtime/main:aimrt_main",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "ros2_chn_bin_flatten_tar",
    src = ":ros2_chn_bin_tar",
    prefix = "bin",
)

pkg_tar(
    name = "ros2_chn_tar",
    srcs = [
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
    deps = [
        ":ros2_chn_bin_flatten_tar",
        ":ros2_chn_without_bin_tar",
    ],
)
