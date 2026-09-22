load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "common",
    srcs = ["core_proxy.cpp"],
    hdrs = ["core_proxy.h"],
    deps = [
        "//src/prelude",
        "@aimrt//:libaimrt",
    ],
)
