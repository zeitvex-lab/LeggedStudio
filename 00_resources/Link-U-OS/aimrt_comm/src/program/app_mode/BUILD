package(default_visibility = ["//visibility:public"])

cc_library(
    name = "app_mode",
    srcs = ["app_mode.cpp"],
    hdrs = [
        "app_mode.h",
    ],
    linkopts = [
    ],
    deps = [
        "//src/module",
        "//src/program/details",
        "//src/register_backward",
        "//src/runtime/interface",
        "@com_github_gflags_gflags//:gflags",
        "@aimrt//:libaimrt",
        "//src/minidump",
    ],
)
