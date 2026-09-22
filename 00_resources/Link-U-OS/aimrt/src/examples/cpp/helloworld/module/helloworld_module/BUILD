# Copyright (c) 2023, AgiBot Inc.
# All rights reserved.

load("@rules_cc//cc:defs.bzl", "cc_library", "cc_test")

cc_library(
    name = "helloworld_module",
    srcs = glob(
        ["*.cc"],
        exclude = ["*_test.cc"],
    ),
    hdrs = glob(["*.h"]),
    deps = [
        "@yaml-cpp",
        "//src/interface/aimrt_module_cpp_interface:aimrt_module_cpp_interface",
    ],
    visibility = ["//visibility:public"],
)

cc_test(
    name = "helloworld_module_test",
    srcs = glob(["*_test.cc"]),
    deps = [
        ":helloworld_module",
        "@googletest//:gtest_main",
    ],
)