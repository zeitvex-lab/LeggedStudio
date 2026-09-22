load("@rules_cc//cc:defs.bzl", "cc_binary")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "helloworld_app",
    srcs = glob(["*.cc"]),
    deps = [
        "//src/runtime/core",
        "@com_github_gflags_gflags//:gflags",
    ],
)
