package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_record_playback_plugin",
    srcs = glob(
        ["*.cc", "*.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
        "//src/protocols/plugins/record_playback_plugin:aimrt_record_playback_rpc",
        "@mcap",
    ],
)
