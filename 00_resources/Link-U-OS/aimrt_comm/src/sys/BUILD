load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

# config_setting(
#     name = "ci_config",
#     define_values = {
#         "IS_CI": "1",
#     },
# )

cc_library_with_top_header(
    name = "sys",
    srcs = glob([
        "internal/*.cpp",
    ]) + [
        "details/utils.cpp",
        "info.cpp",
    ],
    hdrs = glob([
        "internal/*.h",
    ]) + [
        "details/utils.h",
        "info.h",
    ],
    deps = [
        "//src/panic",
        "//src/utils",
        "@fmt",
        "@integration//:boost",
        "@yaml-cpp",
    ],
)

cc_test(
    name = "sys_test",
    srcs = [
        "sys_test.cpp",
    ],
    data = glob([
        "test/**/*",
    ]),
    linkstatic = True,
    deps = [
        ":sys",
        "//src/test",
    ],
)

cc_test(
    name = "utils_test",
    srcs = [
        "details/utils_test.cpp",
    ],
    data = glob([
        "test/**/*",
    ]),
    linkstatic = True,
    deps = [
        ":sys",
        "//src/test",
    ],
)
