load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

pkg_files(
    name = "pb_rpc_config",
    srcs = [
        "//src/examples/cpp/pb_rpc/install/linux/bin/cfg:pb_rpc_config",
    ],
    prefix = "config/pb_rpc",
)

pkg_files(
    name = "pb_rpc_script",
    srcs = [
        "//src/examples/cpp/pb_rpc/install/linux/bin:pb_rpc_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/pb_rpc",
)

pkg_filegroup(
    name = "pb_rpc_filegroup",
    srcs = [
        ":pb_rpc_config",
        ":pb_rpc_script",
    ],
)

pkg_tar(
    name = "pb_rpc_without_bin_tar",
    srcs = [
        ":pb_rpc_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "pb_rpc_bin_tar",
    srcs = [
        "//src/examples/cpp/pb_rpc/app/normal_pb_rpc_client_app",
        "//src/examples/cpp/pb_rpc/app/normal_pb_rpc_server_app",
        "//src/examples/cpp/pb_rpc/pkg/pb_rpc_client_pkg",
        "//src/examples/cpp/pb_rpc/pkg/pb_rpc_pkg",
        "//src/examples/cpp/pb_rpc/pkg/pb_rpc_server_pkg",
        "//src/runtime/main:aimrt_main",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "pb_rpc_bin_flatten_tar",
    src = ":pb_rpc_bin_tar",
    prefix = "bin",
)

pkg_tar(
    name = "pb_rpc_tar",
    srcs = [
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
    deps = [
        ":pb_rpc_bin_flatten_tar",
        ":pb_rpc_without_bin_tar",
    ],
)
