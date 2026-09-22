load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@rules_pkg//pkg:mappings.bzl", "pkg_files")

package(default_visibility = ["//visibility:public"])

pkg_tar(
    name = "health_monitor_tar",
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
    deps = [
        "//src/app/health_monitor:health_monitor_bin_flatten_tar",
        "//src/app/health_monitor:health_monitor_without_bin_tar",
        "@integration//:all_plugins_tar",
    ],
)
