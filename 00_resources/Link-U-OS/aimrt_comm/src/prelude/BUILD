load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "prelude",
    hdrs = glob([
        "**/*.h",
    ]),
    deps = [
        "//src/ctx",
        "//src/match",
        "//src/module",
        "//src/panic",
    ],
)

cc_test(
    name = "option_test",
    srcs = [
        "option_test.cpp",
    ],
    deps = [
        ":prelude",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "result_test",
    srcs = [
        "result_test.cpp",
    ],
    deps = [
        ":prelude",
        "//src/test",
    ],
    linkstatic = True,
)
