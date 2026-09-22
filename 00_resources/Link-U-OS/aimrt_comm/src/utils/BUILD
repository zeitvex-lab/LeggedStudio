load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "utils",
    srcs = [
        "env.cpp",
        "execute.cc",
        "string.cpp",
        "time.cc",
        "type_support.cc",
        "uuid.cc",
    ],
    hdrs = [
        "env.h",
        "execute.h",
        "string.h",
        "time.h",
        "type_support.h",
        "uuid.h",
    ],
    deps = [
        "@integration//:boost",
        "@yaml-cpp",
    ],
)
