package(default_visibility = ["//visibility:public"])

cc_library(
    name = "proxy_rpc_co_module",
    srcs = glob(["*.cc"]),
    hdrs = glob(["*.h"]),
    deps = [
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_protobuf_interface", 
        "//src/protocols/pb/example/rpc:aimrt_rpc_rpc",
        "@yaml-cpp",
    ],
)
