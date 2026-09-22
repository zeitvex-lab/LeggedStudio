package(default_visibility = ["//visibility:public"])

cc_library(
    name = "normal_rpc_sync_client_module",
    srcs = ["normal_rpc_sync_client_module.cc"],
    hdrs = ["normal_rpc_sync_client_module.h"],
    deps = [
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_protobuf_interface", 
        "//src/protocols/pb/example/rpc:aimrt_rpc_rpc",
        "@yaml-cpp",
    ],
)
