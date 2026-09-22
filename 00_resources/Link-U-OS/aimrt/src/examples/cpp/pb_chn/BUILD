load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

pkg_files(
    name = "pb_chn_config",
    srcs = [
        "//src/examples/cpp/pb_chn/install/linux/bin/cfg:pb_chn_config",
    ],
    prefix = "config/pb_chn",
)

pkg_files(
    name = "pb_chn_script",
    srcs = [
        "//src/examples/cpp/pb_chn/install/linux/bin:pb_chn_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/pb_chn",
)

pkg_filegroup(
    name = "pb_chn_filegroup",
    srcs = [
        ":pb_chn_config",
        ":pb_chn_script",
    ],
)

pkg_tar(
    name = "pb_chn_without_bin_tar",
    srcs = [
        ":pb_chn_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "pb_chn_bin_tar",
    srcs = [
        "//src/examples/cpp/pb_chn/app/normal_pb_chn_publisher_app",
        "//src/examples/cpp/pb_chn/app/normal_pb_chn_subscriber_app",
        "//src/examples/cpp/pb_chn/pkg/pb_chn_pkg",
        "//src/examples/cpp/pb_chn/pkg/pb_chn_pub_pkg",
        "//src/examples/cpp/pb_chn/pkg/pb_chn_sub_pkg",
        "//src/runtime/main:aimrt_main",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "pb_chn_bin_flatten_tar",
    src = ":pb_chn_bin_tar",
    prefix = "bin",
)

pkg_tar(
    name = "pb_chn_tar",
    srcs = [
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
    deps = [
        ":pb_chn_bin_flatten_tar",
        ":pb_chn_without_bin_tar",
    ],
)
