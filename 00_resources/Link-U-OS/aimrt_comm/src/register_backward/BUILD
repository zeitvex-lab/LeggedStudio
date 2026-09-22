load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "register_backward",
    srcs = ["register.cpp"],
    hdrs = ["register.h"],
    deps = [
        "//src/macro",
        "//src/private/backward",
    ],
)
