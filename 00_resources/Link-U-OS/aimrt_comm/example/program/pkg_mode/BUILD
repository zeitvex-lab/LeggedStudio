package(default_visibility = ["//visibility:public"])

cc_library(
    name = "example_use_pkg_mode_lib",
    srcs = [
        "pkg_main.cpp",
    ],
    deps = [
        "//example/program/common",
        "//src/program/pkg_mode",
    ],
)

cc_binary(
    name = "example-use_pkg_mode",
    srcs = [
        "pkg_main.cpp",
    ],
    linkshared = True,
    deps = [
        "//example/program/common",
        "//src/program/pkg_mode",
    ],
)
