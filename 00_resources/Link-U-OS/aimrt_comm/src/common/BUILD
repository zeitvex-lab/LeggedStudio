load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "common",
    srcs = ["topic_hz_calculator.cc"],
    hdrs = ["topic_hz_calculator.h"],
    deps = [
        "//src/ctx",
    ],
)

cc_test(
    name = "topic_hz_calculator_test",
    srcs = [
        "topic_hz_calculator_test.cc",
    ],
    deps = [
        ":common",
        "@googletest//:gtest_main",
    ],
)
