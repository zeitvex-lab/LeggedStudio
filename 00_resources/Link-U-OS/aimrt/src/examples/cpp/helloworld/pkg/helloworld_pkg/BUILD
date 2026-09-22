load("@rules_cc//cc:defs.bzl", "cc_library")

cc_library(
    name = "helloworld_pkg",
    srcs = glob(["*.cc"]),
    deps = [
        "//src/interface/aimrt_pkg_c_interface:aimrt_pkg_c_interface",
        "//src/examples/cpp/helloworld/module/helloworld_module:helloworld_module",
    ],
    visibility = ["//visibility:public"],
)