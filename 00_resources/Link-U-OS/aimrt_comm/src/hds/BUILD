load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "hds",
    hdrs = [
        "context.h",
        "interface.h",
    ],
    deps = [
        "//src/core",
        # "@health_diag_generation//:libhealth_diag_generation",
    ],
)

cc_test(
    name = "interface_test",
    srcs = [
        "interface_test.cc",
    ],
    deps = [
        ":hds",
        "//src/test",
    ],
    linkstatic = True,
)
