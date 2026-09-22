package(default_visibility = ["//visibility:public"])

cc_library(
    name = "util",
    srcs = glob([
        "**/*.cc",
    ]),
    hdrs = glob([
        "**/*.h",
    ]),
    deps = [
        "@integration//:boost",
        "@aimrt//src/interface/aimrt_module_cpp_interface",
        "@aimrt//src/runtime/core",
        "@aimrt//src/common/util",
        "@yaml-cpp",
    ],
)
