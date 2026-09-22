package(default_visibility = ["//visibility:public"])

load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

cc_binary(
    name = "aimrte",
    srcs = ["main.cpp"],
    deps = ["//src/program"],
)

pkg_tar(
    name = "aimrte_tar",
    srcs = [
        ":aimrte",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "aimrte_flatten_tar",
    src = ":aimrte_tar",
    prefix = "bin",
)
