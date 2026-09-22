load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "minidump",
    srcs = [
        "minidump_manager.cpp",
    ],
    hdrs = [
        "minidump_manager.h",
    ],
    deps = [
        "//src/ctx",
        "@breakpad//:breakpad_client",
    ],
)
