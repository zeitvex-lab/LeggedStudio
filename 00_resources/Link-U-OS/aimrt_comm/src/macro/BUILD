load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "macro",
    srcs = [],
    hdrs = glob([
        "*.h",
    ]),
    deps = ["//src/ref"],
)

cc_test(
    name = "defer_test",
    srcs = [
        "defer_test.cpp",
    ],
    deps = [
        ":macro",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "macro_test",
    srcs = [
        "macro_test.cpp",
    ],
    deps = [
        ":macro",
        "//src/test",
    ],
    linkstatic = True,
)
