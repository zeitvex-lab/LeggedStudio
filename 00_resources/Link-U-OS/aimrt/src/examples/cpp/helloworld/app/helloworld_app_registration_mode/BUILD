load("@rules_cc//cc:defs.bzl", "cc_binary")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "src_files",
    srcs = glob(["*.cc"]),
)

cc_binary(
    name = "helloworld_app_registration_mode",
    srcs = [":src_files"],
    deps = [
        "@com_github_gflags_gflags//:gflags",
        "//src/runtime/core:core",
        "//src/examples/cpp/helloworld/module/helloworld_module:helloworld_module",
    ],
)