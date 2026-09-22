load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "convert",
    srcs = [],
    hdrs = ["interface.h"],
    deps = [
        "//src/panic",
    ],
)

cc_test(
    name = "interface_test",
    srcs = [
        "interface_test.cpp",
    ],
    deps = [
        ":convert",
        "@googletest//:gtest_main",
    ],
)
