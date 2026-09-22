package(default_visibility = ["//visibility:public"])

cc_library(
    name = "benchmark_publisher_module",
    srcs = ["benchmark_publisher_module.cc"],
    hdrs = ["benchmark_publisher_module.h"],
    deps = [
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_protobuf_interface", 
        "//src/protocols/pb/example:benchmark_cc_proto",
        "@yaml-cpp",
    ],
)
