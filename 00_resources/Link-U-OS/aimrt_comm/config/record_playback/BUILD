package(default_visibility = ["//visibility:public"])

filegroup(
    name = "comm_config_yaml",
    srcs = select({
        "@integration//toolchains/platforms:is_orin_aarch64": ["comm/orin/record_playback_config.yaml"],
        "//conditions:default": ["comm/x86/record_playback_config.yaml"],
    }),
)

filegroup(
    name = "a2_action_yaml",
    srcs = select({
        "@integration//toolchains/platforms:is_orin_aarch64": ["a2/orin/record_playback_action.yaml"],
        "//conditions:default": ["a2/x86/record_playback_action.yaml"],
    }),
)

filegroup(
    name = "record_playback_config",
    srcs = select({
        "//conditions:default": [
            ":comm_config_yaml",
            ":a2_action_yaml",
        ],
    }),
)
