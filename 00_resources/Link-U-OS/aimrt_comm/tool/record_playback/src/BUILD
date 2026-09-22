load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrte-tool-record_playback",
    srcs = [
        "main.cpp",
        "parse_cmd.h",
        "record.cpp",
        "record.h",
        "util.h",
    ],
    deps = [
        "//:aimrte",
        "//aimdk/protocol/hds:exception_channel_cc_proto",
        "//ros2/record_playback:record_playback_msgs_cc_interface",
        "//ros2/record_playback/GetActionList:record_playback_msgs_rpc",
        "//ros2/record_playback/GetBagList:record_playback_msgs_rpc",
        "//ros2/record_playback/GetUploadAllowed:record_playback_msgs_rpc",
        "//ros2/record_playback/StartRecord:record_playback_msgs_rpc",
        "//ros2/record_playback/StopRecord:record_playback_msgs_rpc",
        "//ros2/record_playback/UpdateRecordAction:record_playback_msgs_rpc",
        "//src/module",
        "@aimrt//:libaimrt",
        "@com_github_gflags_gflags//:gflags",
        "@fmt",
        "@yaml-cpp",
    ],
)

pkg_files(
    name = "record_playback_config",
    srcs = [
        "//config/comm:topic_meta_config",
        "//config/record_playback:record_playback_config",
    ],
    prefix = "config/record_playback",
)

pkg_files(
    name = "record_playback_script",
    srcs = [
        "//scripts/record_playback:record_playback_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/record_playback",
)

pkg_filegroup(
    name = "record_playback_filegroup",
    srcs = [
        ":record_playback_config",
        ":record_playback_script",
    ],
)

pkg_tar(
    name = "record_playback_without_bin_tar",
    srcs = [
        ":record_playback_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "record_playback_bin_tar",
    srcs = [
        ":aimrte-tool-record_playback",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "record_playback_bin_flatten_tar",
    src = ":record_playback_bin_tar",
    prefix = "bin",
)
