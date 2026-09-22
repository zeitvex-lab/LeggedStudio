package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "ros2_rpc_pkg",
    srcs = ["pkg_main.cc"],
    linkshared = True,
    deps = [
        "//src/interface/aimrt_pkg_c_interface",
        "//src/examples/cpp/ros2_rpc/module/normal_rpc_co_client_module",
        "//src/examples/cpp/ros2_rpc/module/normal_rpc_co_server_module",
        "//src/examples/cpp/ros2_rpc/module/normal_rpc_sync_client_module",
        "//src/examples/cpp/ros2_rpc/module/normal_rpc_sync_server_module",
        "//src/examples/cpp/ros2_rpc/module/normal_rpc_async_client_module",
        "//src/examples/cpp/ros2_rpc/module/normal_rpc_async_server_module",
        "//src/examples/cpp/ros2_rpc/module/normal_rpc_future_client_module",
    ],
)
