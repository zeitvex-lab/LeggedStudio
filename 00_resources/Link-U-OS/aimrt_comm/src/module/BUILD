load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "module",
    srcs = glob(
        [
            "**/*.cpp",
        ],
        exclude = ["cfg_test.cpp"],
    ),
    hdrs = glob([
        "**/*.h",
    ]),
    linkopts = [
    ],
    deps = [
        "//src/ctx",
        "//src/utils",
        "//aimdk/protocol/hds:exception_channel_cc_proto",
        "//aimdk/protocol/trace:event_channel_cc_proto",
        "@aimrt//:libaimrt",
        "@com_github_gflags_gflags//:gflags",
        "@reflectcpp",
    ],
)

cc_test(
    name = "cfg_test",
    srcs = [
        "cfg_test.cpp",
    ],
    deps = [
        ":module",
        "//src/test_protocol:test_msg_rpc",
        "@googletest//:gtest_main",
    ],
)
