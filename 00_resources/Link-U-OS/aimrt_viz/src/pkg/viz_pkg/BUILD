load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "viz_pkg",
    srcs = ["pkg_main.cc"],
    linkshared = True,
    deps = [
        "//src/module/viz_module:viz_module",
        "@aimrt//src/interface/aimrt_module_cpp_interface",
        "@aimrt//src/interface/aimrt_pkg_c_interface",
    ],
)


pkg_tar(
    name = "aimrt_viz_pkg_tar",
    srcs = [
        ":viz_pkg",
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
)


flatten_tar(
    name = "aimrt_viz_pkg_flatten_tar",
    src = ":aimrt_viz_pkg_tar",
    prefix = "bin",
)