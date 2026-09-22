

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "core",
    srcs = glob([
        "**/*.cc"
    ]),
    hdrs = glob([
        "**/*.h",
        "**/*.hpp",
    ]),
    deps = [
        "@aimrt_comm//aimdk/protocol/hal/bms:hal_bms_channel_cc_proto",
        "@aimrt_comm//aimdk/protocol/hal/state:hal_state_channel_cc_proto",
        "@aimrt_comm//aimdk/protocol/hds/process:process_heartbeat_channel_cc_proto",
        "@aimrt_comm//aimdk/protocol/hds:system_status_cc_proto",
        "@aimrt_comm//src/all_in_one",
        "@aimrt_comm//src/common",
        "@nlohmann_json//:json",
    ],
)
