load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "ctx",
    srcs = glob(
        [
            "**/*.cpp",
        ],
        exclude = ["interface_test.cpp"],
    ),
    hdrs = glob([
        "**/*.h",
    ]),
    deps = [
        "//src/core",
        "//src/hds",
        "//src/sys",
        "//src/trace",
    ],
)

cc_test(
    name = "interface_test",
    srcs = [
        "interface_test.cpp",
    ],
    deps = [
        "//src/test_protocol:test_msg_rpc",
        "//src/test",
    ],
    linkstatic = True,
)
