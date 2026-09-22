load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")

package(default_visibility = ["//visibility:public"])

pkg_tar(
    name = "tzcamera_tar",
    srcs = [
    ],
    extension = "tar",
    mode = "0755",
    strip_prefix = ".",
    tags = ["tar"],
    deps = [
        "//src/app/d415:hal_d415_bin_flatten_tar",
        "//src/app/d415:hal_d415_without_bin_tar",
        "//src/app/dcw2:hal_dcw2_bin_flatten_tar",
        "//src/app/dcw2:hal_dcw2_without_bin_tar",
        "//src/app/mid360lidar:mid360lidar_bin_flatten_tar",
        "//src/app/mid360lidar:mid360lidar_without_bin_tar",
        "//src/app/tzcamera:tzcamera_bin_flatten_tar",
        "//src/app/tzcamera:tzcamera_without_bin_tar",
        "@integration//:all_plugins_tar",
    ],
)
