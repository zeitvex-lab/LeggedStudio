load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "health_monitor",
    srcs = ["main.cpp"],
    copts = [
        "-I$(GENDIR)",
        "-I$(GENDIR)/external/aimrt_protocol",
        "-I$(GENDIR)/external/aim_omp_protocol",
        "-DAIMHDS_ENABLE_AIMRT=ON",
        "-DAIMHDS_ENABLE_ROS2=ON",
    ],
    linkopts = select({
        "@integration//toolchains/platforms:is_orin_aarch64": [
            "-L/opt/nvidia/orin_sysroot/usr/lib/aarch64-linux-gnu",
        ],
        "//conditions:default": [],
    }),
    deps = [
        "//src/core",
        "//src/module",
        "@aimrt_comm//src/program",
    ],
)

pkg_files(
    name = "health_monitor_config",
    srcs = [
        "//config/health_monitor:health_monitor_config",
    ],
    prefix = "config/health_monitor",
)

pkg_files(
    name = "health_monitor_script",
    srcs = [
        "//scripts/health_monitor:health_monitor_scripts",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/health_monitor",
)

pkg_filegroup(
    name = "health_monitor_filegroup",
    srcs = [
        ":health_monitor_config",
        ":health_monitor_script",
    ],
)

pkg_tar(
    name = "health_monitor_without_bin_tar",
    srcs = [
        "//src/app/health_monitor:health_monitor_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "health_monitor_bin_tar",
    srcs = [
        ":health_monitor",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "health_monitor_bin_flatten_tar",
    src = "//src/app/health_monitor:health_monitor_bin_tar",
    prefix = "bin",
)
