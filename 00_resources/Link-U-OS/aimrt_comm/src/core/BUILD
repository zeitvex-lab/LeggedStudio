load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "core",
    srcs = glob([
        "context/*.cpp",
    ]) + [
        "context.cpp",
        "get_scheduler.cpp",
    ],
    hdrs = glob([
        "**/*.h",
        "**/*.inl",
    ]),
    defines = ["AIMRT_USE_FMT_LIB"],
    deps = [
        "//src/concepts",
        "//src/convert",
        "//src/macro",
        "//src/panic",
        "//src/res",
        "//src/sys",
        "//src/trait",
        "@aimrt//:libaimrt",
        "@fmt",
        "@reflectcpp",
    ],
)

cc_test(
    name = "context_test",
    srcs = [
        "context_test.cpp",
    ],
    deps = [
        "//src/test",
        "//src/test_protocol:test_msg_rpc",
        "//src/test_protocol:test_service_rpc",
        "//src/trait",
        "@integration//:eigen",
    ],
    linkstatic = True,
)

cc_test(
    name = "coroutine_test",
    srcs = [
        "coroutine_test.cpp",
    ],
    deps = [
        "//src/test",
        "//src/test_protocol:test_msg_rpc",
        "//src/test_protocol:test_service_rpc",
        "@aimrt//:libaimrt",
        "//src/trait",
        "@integration//:eigen",
    ],
    linkstatic = True,
)

cc_test(
    name = "mock_test",
    srcs = [
        "mock_test.cpp",
    ],
    deps = [
        "//src/test",
        "//src/test_protocol:test_msg_rpc",
        "//src/test_protocol:test_service_rpc",
        "//src/trait",
        "@integration//:eigen",
    ],
    linkstatic = True,
)
