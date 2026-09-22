load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "test",
    srcs = [
        "module_test_controller.cpp",
        "test_base.cpp",
    ],
    hdrs = glob([
        "*.h",
    ]),
    deps = [
        "//src/core",
        "//src/ctx",
        "//src/runtime/interface",
        "//src/sync",
        "@googletest//:gtest_main",
    ],
)

cc_test(
    name = "mock_client_test",
    srcs = [
        "mock_client_test.cpp",
    ],
    linkstatic = True,
    deps = [
        ":test",
    ],
)

cc_test(
    name = "mock_publisher_test",
    srcs = [
        "mock_publisher_test.cpp",
    ],
    linkstatic = True,
    deps = [
        ":test",
    ],
)

cc_test(
    name = "mock_server_test",
    srcs = [
        "mock_server_test.cpp",
    ],
    linkstatic = True,
    deps = [
        ":test",
    ],
)

cc_test(
    name = "mock_subscriber_test",
    srcs = [
        "mock_subscriber_test.cpp",
    ],
    linkstatic = True,
    deps = [
        ":test",
    ],
)

cc_test(
    name = "module_test_controlller_test",
    srcs = [
        "module_test_controlller_test.cpp",
    ],
    linkstatic = True,
    deps = [
        ":test",
    ],
)
