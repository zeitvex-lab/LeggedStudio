load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

exports_files(["VERSION"])

pkg_tar(
    name = "aimrt_viz_bin_tar",
    srcs = [
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
    deps = [
        "//src/plugins/viz_plugin:aimrt_viz_plugin_flatten_tar",
        "//src/pkg/viz_pkg:aimrt_viz_pkg_flatten_tar",
        "@aimrt//:aimrt_plugins_flatten_tar",
    ],
)


flatten_tar(
    name = "aimrt_viz_flatten_tar",
    src = ":aimrt_viz_bin_tar",
    prefix = "bin",
)


pkg_tar(
    name = "viz_tar",
    deps = [
        ":aimrt_viz_flatten_tar",
        "//src/examples/viz:aimrt_viz_without_bin_tar",
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],

)