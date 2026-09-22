load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "trait",
    srcs = [
    ],
    hdrs = glob(["*.h"]),
)

cc_test(
    name = "as_is_test",
    srcs = [
        "as_is_test.cpp",
    ],
    deps = [
        ":trait",
        "@googletest//:gtest_main",
    ],
)

cc_test(
    name = "bind_test",
    srcs = [
        "bind_test.cpp",
    ],
    deps = [
        ":trait",
        "@googletest//:gtest_main",
    ],
)

cc_test(
    name = "const_cast_test",
    srcs = [
        "const_cast_test.cpp",
    ],
    deps = [
        ":trait",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "renew_test",
    srcs = [
        "renew_test.cpp",
    ],
    deps = [
        ":trait",
        "//src/test",
    ],
    linkstatic = True,
)
