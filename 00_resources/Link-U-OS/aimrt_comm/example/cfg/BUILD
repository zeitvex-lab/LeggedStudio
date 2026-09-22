load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

pkg_files(
    name = "cfg_config",
    srcs = [
        "//config/example/cfg:demo_cfg_filegroup",
    ],
    prefix = "config/example/cfg",
)

pkg_files(
    name = "cfg_script",
    srcs = [
        "//scripts/example/cfg:demo_cfg_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/example/cfg",
)

pkg_filegroup(
    name = "cfg_filegroup",
    srcs = [
        ":cfg_config",
        ":cfg_script",
    ],
)

pkg_tar(
    name = "cfg_without_bin_tar",
    srcs = [
        ":cfg_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "cfg_bin_tar",
    srcs = [
        "//example/cfg/demo1:demo1",
        "//example/cfg/demo2:demo2",
        "//example/cfg/demo3:demo3",
        "//example/cfg/demo4:demo4",
        "//example/cfg/demo5:demo5",

    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "cfg_flatten_bin_tar",
    src = ":cfg_bin_tar",
    prefix = "bin",
)
