package(default_visibility = ["//visibility:public"])

cc_library(
    name = "normal_publisher_module",
    srcs = ["normal_publisher_module.cc"],
    hdrs = ["normal_publisher_module.h"],
    deps = [
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_protobuf_interface", 
        "//src/protocols/pb/example:event_cc_proto",
        "@yaml-cpp",
    ],
)
