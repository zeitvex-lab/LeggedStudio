package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "pb_chn_sub_pkg",
    srcs = ["pkg_main.cc"],
    linkshared = True,
    deps = [
        "//src/interface/aimrt_pkg_c_interface",
        "//src/examples/cpp/pb_chn/module/normal_subscriber_module",
        "//src/examples/cpp/pb_chn/module/benchmark_subscriber_module",
    ],
)
