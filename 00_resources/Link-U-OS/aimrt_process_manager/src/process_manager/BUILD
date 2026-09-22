package(default_visibility = ["//visibility:public"])

cc_library(
    name = "process_manager",
    srcs = glob([
        "**/*.cc",
    ]),
    hdrs = glob([
        "**/*.h",
    ]),
    deps = [
        "@aimrt_comm//aimdk/protocol/em:api_rpc",
        "@integration//:boost", 
        "@aimrt//src/common/util",
        "//src/config_manager",
        "//src/util",
        "@yaml-cpp",
    ],
)
