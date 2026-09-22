package(default_visibility = ["//visibility:public"])

cc_library(
    name = "module",
    srcs = glob([
        "*.cc",
    ]),
    hdrs = glob([
        "**/*.h",
    ]),
    deps = [
        "//src/core",
        "@aimrt_comm//src/all_in_one",
        "@aimrt_comm//aimdk/protocol/hds:hds_service_rpc",
        "@aimrt_comm//aimdk/protocol/hds/monitor:monitor_service_rpc",
        "@aimrt_comm//aimdk/protocol/hds:alert_channel_cc_proto",
        "@aimrt_comm//aimdk/protocol/hds:hds_service_lib",
    ],
)
