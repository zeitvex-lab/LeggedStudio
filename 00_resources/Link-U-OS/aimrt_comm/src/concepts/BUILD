load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "concepts",
    srcs = [],
    hdrs = ["impl.h"],
)

cc_test(
    name = "concepts_test",
    srcs = [
        "impl_test.cpp",
    ],
    deps = [
        ":concepts",
        "@googletest//:gtest_main",
    ],
)
