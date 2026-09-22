load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")

package(default_visibility = ["//visibility:public"])

pkg_tar(
    name = "process_manager_tar",
    srcs = [
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
    deps = [
        "//src/app:process_manager_bin_flatten_tar",
        "//src/app:process_manager_without_bin_tar",
        "@integration//:all_plugins_tar",
    ],
)
