load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "ping",
    srcs = [
        "main.cpp",
        "module.cpp",
        "module.h",
    ],
    deps = [
        "//:aimrte",
        "//aimdk/protocol/demo:demo_service_rpc",
        "//ros2/demo:demo_msgs_rpc",
        "//aimdk/protocol/demo:demo_channel_cc_proto",
    ],
)

pkg_files(
    name = "ping_script",
    srcs = [
        "//scripts/example/ping:ping_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/example/ping",
)

pkg_filegroup(
    name = "ping_filegroup",
    srcs = [
        ":ping_script",
    ],
)

pkg_tar(
    name = "ping_without_bin_tar",
    srcs = [
        ":ping_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "ping_bin_tar",
    srcs = [
        ":ping",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "ping_flatten_bin_tar",
    src = ":ping_bin_tar",
    prefix = "bin",
)
