load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@rules_pkg//pkg:mappings.bzl", "pkg_files")
load("@integration//rules/utils:pkg_lib.bzl", "pkg_lib")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_viz_plugin",
    srcs = glob(
        ["*.cc", "*.h"],
    ),
    linkshared = True,
    deps = [
        "@aimrt//src/interface/aimrt_core_plugin_interface",
        "@aimrt//src/runtime/core",
        "//src/protocols/viz_plugin:viz_plugin_rpc",
    ],
)

pkg_tar(
    name = "aimrt_viz_plugin_tar",
    srcs = [
        ":aimrt_viz_plugin",
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
)


flatten_tar(
    name = "aimrt_viz_plugin_flatten_tar",
    src = ":aimrt_viz_plugin_tar",
    prefix = "bin",
)