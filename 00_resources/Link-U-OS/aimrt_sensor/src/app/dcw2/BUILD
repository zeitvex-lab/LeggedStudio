load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "hal_dcw2",
    srcs = ["dcw2.cpp"],
    deps = [
        "//src/dcw2/module:dcw2_module",
        "@aimrt_comm//:aimrte",
    ],
)

pkg_files(
    name = "hal_dcw2_config",
    srcs = [
        "//config/hal_dcw2:hal_dcw2_config",
    ],
    prefix = "config/hal_dcw2",
)

pkg_files(
    name = "hal_dcw2_script",
    srcs = [
        "//scripts/hal_dcw2:hal_dcw2_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/hal_dcw2",
)

pkg_filegroup(
    name = "hal_dcw2_filegroup",
    srcs = [
        ":hal_dcw2_config",
        ":hal_dcw2_script",
    ],
)

pkg_tar(
    name = "hal_dcw2_without_bin_tar",
    srcs = [
        ":hal_dcw2_filegroup",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "hal_dcw2_bin_tar",
    srcs = [
        ":hal_dcw2",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "hal_dcw2_bin_flatten_tar",
    src = ":hal_dcw2_bin_tar",
    prefix = "bin",
)
