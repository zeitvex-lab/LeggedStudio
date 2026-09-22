package(default_visibility = ["//visibility:public"])

common_srcs = glob([
    "**/*.cc",
])

common_hdrs = glob([
    "**/*.h",
])

common_deps = [
    "//src/common",
    "//plugin/common",
    "//aimdk/protocol/hds/process:process_heartbeat_channel_cc_proto",
    "@aimrt//:libaimrt",
    "@integration//:boost",
    "@reflectcpp",
]

cc_library(
    name = "core",
    srcs = common_srcs,
    hdrs = common_hdrs,
    deps = common_deps,
)

cc_binary(
    name = "aimrt_monitor_plugin",
    srcs = common_srcs + common_hdrs,
    linkshared = True,
    deps = common_deps,
)
