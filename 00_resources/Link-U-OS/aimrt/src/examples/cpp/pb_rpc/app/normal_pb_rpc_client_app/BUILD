package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "normal_pb_rpc_client_app",
    srcs = ["main.cc"],
    deps = [
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_protobuf_interface",
        "//src/protocols/pb/example/rpc:aimrt_rpc_rpc",
        "//src/runtime/core",
    ],
)
