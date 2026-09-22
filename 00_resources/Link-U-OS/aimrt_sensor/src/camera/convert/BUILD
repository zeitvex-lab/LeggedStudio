load("@rules_cuda//cuda:defs.bzl", "cuda_library")
load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")
package(default_visibility = ["//visibility:public"])

cuda_library(
    name = "convert_cuda",
    srcs = glob([
        "*.cu",
    ]),
    hdrs = glob([
        "*.cuh",
    ]),
)

cc_library_with_top_header(
    name = "convert",
    srcs = glob([
        "*.cpp",
    ]),
    hdrs = glob([
        "*.hpp",
    ]),
    deps = [
        ":convert_cuda",
        "@integration//:jetson_multimedia",
        "//src/camera/utils:utils",
        "@integration//:vpi",
        "@aimrt_comm//:aimrte",
    ],
)