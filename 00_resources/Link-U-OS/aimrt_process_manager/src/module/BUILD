package(default_visibility = ["//visibility:public"])

cc_library(
    name = "process_manager_module",
    srcs = glob([
        "**/*.cc",
    ]),
    hdrs = glob([
        "**/*.h",
    ]),
    deps = [
        "//src/config_manager",
        "//src/util",
        "//src/process_manager",
        "@aimrt//src/interface/aimrt_module_cpp_interface",
        "@aimrt//src/runtime/core",
        "@aimrt//src/common/net",
        "@aimrt_comm//aimdk/protocol/em:api_rpc",
        "@integration//:boost", 
        "@yaml-cpp",
        "@nlohmann_json//:json",
    ],
    defines = ["BOOST_ASIO_NO_DEPRECATED"], 
)
