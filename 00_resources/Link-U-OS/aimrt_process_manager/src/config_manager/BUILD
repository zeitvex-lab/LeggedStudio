package(default_visibility = ["//visibility:public"])

cc_library(
    name = "config_manager",
    srcs = glob([
        "**/*.cc",
    ]),
    hdrs = glob([
        "**/*.h",
    ]),
    deps = [
        "//src/util",
        "@integration//:boost",
        "@aimrt//src/runtime/core",
        "@yaml-cpp",
    ],
)
