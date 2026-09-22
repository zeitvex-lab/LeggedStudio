load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "pong",
    srcs = [
        "ball.cpp",
        "ball.h",
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
    name = "pong_script",
    srcs = [
        "//scripts/example/pong:pong_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/example/pong",
)

pkg_filegroup(
    name = "pong_filegroup",
    srcs = [
        ":pong_script",
    ],
)

pkg_tar(
    name = "pong_without_bin_tar",
    srcs = [
        ":pong_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "pong_bin_tar",
    srcs = [
        ":pong",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "pong_flatten_bin_tar",
    src = ":pong_bin_tar",
    prefix = "bin",
)
