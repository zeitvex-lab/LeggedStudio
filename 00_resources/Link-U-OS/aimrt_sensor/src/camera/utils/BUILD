load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "utils",
    srcs = glob([
        "*.cpp",
    ]),
    hdrs = glob([
        "*.hpp",
    ]),
    deps = [
        "@aimrt_comm//:aimrte",
        "//src/device/i2c",
    ]
)