load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "ref",
    hdrs = [
        "impl.h",
    ],
)

cc_test(
    name = "impl_test",
    srcs = [
        "impl_test.cpp",
    ],
    deps = [
        ":ref",
        "//src/test",
    ],
    linkstatic = True,
)
