load("@rules_pkg//pkg:mappings.bzl", "pkg_filegroup", "pkg_files", "pkg_attributes")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "tzcamera",
    srcs = ["tzcamera.cpp"],
    deps = [
        "//src/camera/mod:tz_camera_module_lib",
        "@aimrt_comm//src/program",
        "@aimrt_comm//:aimrte",
        "@integration//:nvbufsurftransform"
    ],
)

pkg_files(
    name = "tzcamera_config",
    srcs = [
        "//config/tzcamera:tzcamera_config",
    ],
    prefix = "config/tzcamera",
)

pkg_files(
    name = "tzcamera_script",
    srcs = [
        "//scripts/tzcamera:tzcamera_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/tzcamera",
)

pkg_filegroup(
    name = "tzcamera_filegroup",
    srcs = [
        ":tzcamera_config",
        ":tzcamera_script",
    ],
)

pkg_tar(
    name = "tzcamera_without_bin_tar",
    srcs = [
        ":tzcamera_filegroup",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "tzcamera_bin_tar",
    srcs = [
        ":tzcamera",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "tzcamera_bin_flatten_tar",
    src = ":tzcamera_bin_tar",
    prefix = "bin",
)