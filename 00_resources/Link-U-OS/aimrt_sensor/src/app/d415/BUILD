load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "hal_d415",
    srcs = ["d415.cpp"],
    deps = [
        "//src/d415/module:d415_module",
        "@aimrt_comm//:aimrte",
        "@integration//:nvbufsurftransform",  # 需要添加以链接到正确的库
    ],
)

pkg_files(
    name = "hal_d415_config",
    srcs = [
        "//config/hal_d415:hal_d415_config",
    ],
    prefix = "config/hal_d415",
)

pkg_files(
    name = "hal_d415_script",
    srcs = [
        "//scripts/hal_d415:hal_d415_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/hal_d415",
)

pkg_filegroup(
    name = "hal_d415_filegroup",
    srcs = [
        ":hal_d415_config",
        ":hal_d415_script",
    ],
)

pkg_tar(
    name = "hal_d415_without_bin_tar",
    srcs = [
        ":hal_d415_filegroup",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "hal_d415_bin_tar",
    srcs = [
        ":hal_d415",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "hal_d415_bin_flatten_tar",
    src = ":hal_d415_bin_tar",
    prefix = "bin",
)
