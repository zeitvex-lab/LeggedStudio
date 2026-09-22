package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "pb_rpc_server_pkg",
    srcs = ["pkg_main.cc"],
    linkshared = True,
    deps = [
        "//src/interface/aimrt_pkg_c_interface",
        "//src/examples/cpp/pb_rpc/module/normal_rpc_co_server_module",
        "//src/examples/cpp/pb_rpc/module/proxy_rpc_co_module",
        "//src/examples/cpp/pb_rpc/module/normal_rpc_sync_server_module",
        "//src/examples/cpp/pb_rpc/module/normal_rpc_async_server_module",
    ],
)
