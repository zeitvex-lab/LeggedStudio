package(default_visibility = ["//visibility:public"])

cc_library(
    name = "container",
    srcs = [],
    hdrs = ["indexed_variant.h"],
)

cc_test(
    name = "container_test",
    srcs = [
        "indexed_variant_test.cpp",
    ],
    deps = [
        ":container",
        "@googletest//:gtest_main",
    ],
)
