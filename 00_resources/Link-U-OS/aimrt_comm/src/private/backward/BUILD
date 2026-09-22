load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "backward",
    hdrs = [
        "backward.hpp",
        "details/dwarf.h",
    ],
    deps = [
        "//src/macro",
        "@integration//:elfutils",
    ],
)
