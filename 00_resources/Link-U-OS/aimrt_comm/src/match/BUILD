load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "match",
    hdrs = glob([
        "*.h",
    ]),
    deps = [
        "//src/macro",
        "//src/trait",
    ],
)

cc_test(
    name = "match_test",
    srcs = [
        "match_test.cpp",
    ],
    deps = [
        ":match",
        "//src/test",
    ],
    linkstatic = True,
)
