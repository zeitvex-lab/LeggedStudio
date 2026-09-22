load("@rules_pkg//pkg:mappings.bzl", "pkg_filegroup", "pkg_files", "pkg_attributes")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "mid360lidar",
    srcs = ["mid360lidar.cpp"],
    deps = [
        "//src/mid360_lidar/module:mid360_lidar_module",
        # "@aimrt_comm//src/program",
        "@aimrt_comm//:aimrte",
    ],
)

pkg_files(
    name = "mid360lidar_config",
    srcs = [
        "//config/mid360lidar:mid360lidar_config",
    ],
    prefix = "config/mid360lidar",
)

pkg_files(
    name = "mid360lidar_script",
    srcs = [
        "//scripts/mid360lidar:mid360lidar_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/mid360lidar",
)

pkg_filegroup(
    name = "mid360lidar_filegroup",
    srcs = [
        ":mid360lidar_config",
        ":mid360lidar_script",
    ],
)

pkg_tar(
    name = "mid360lidar_without_bin_tar",
    srcs = [
        ":mid360lidar_filegroup",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "mid360lidar_bin_tar",
    srcs = [
        ":mid360lidar",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "mid360lidar_bin_flatten_tar",
    src = ":mid360lidar_bin_tar",
    prefix = "bin",
)