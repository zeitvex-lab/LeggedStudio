package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "pb_chn_pub_pkg",
    srcs = ["pkg_main.cc"],
    linkshared = True,
    deps = [
        "//src/interface/aimrt_pkg_c_interface",
        "//src/examples/cpp/pb_chn/module/normal_publisher_module",
        "//src/examples/cpp/pb_chn/module/benchmark_publisher_module",
    ],
)
