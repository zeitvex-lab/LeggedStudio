load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "sync",
    srcs = glob(
        [
            "**/*.cpp",
        ],
        exclude = ["**/*_test.cpp"],
    ),
    hdrs = glob(
        [
            "**/*.h",
        ],
        exclude = ["test/common.h"],
    ),
    deps = [
        "//src/container",
        "//src/core",
        "//src/ctx",
    ],
    exclude_hdrs=["test/common.h"]
)

# cc_library(
#     name = "common",
#     hdrs = ["common.h"],
#     includes = ["test"],
#     deps = [
#         "//src/test",
#     ],
# )

cc_test(
    name = "coroutine_decorator_test",
    srcs = [
        "test/common.h",
        "details/coroutine_decorator_test.cpp",
    ],
    deps = [
        ":sync",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "any_test",
    srcs = [
        "test/common.h",
        "any_test.cpp",
    ],
    deps = [
        ":sync",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "atom_data_test",
    srcs = [
        "test/common.h",
        "atom_data_test.cpp",
    ],
    deps = [
        "//src/test",
        ":sync",
    ],
    linkstatic = True,
)

cc_test(
    name = "mutex_test",
    srcs = [
        "test/common.h",
        "mutex_test.cpp",
    ],
    deps = [
        "//src/test",
        ":sync",
    ],
    linkstatic = True,
)

cc_test(
    name = "spin_mutex_test",
    srcs = [
        "test/common.h",
        "spin_mutex_test.cpp",
    ],
    deps = [
        "//src/test",
        ":sync",
    ],
    linkstatic = True,
)
