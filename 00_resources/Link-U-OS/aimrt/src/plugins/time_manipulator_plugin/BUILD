package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_time_manipulator_plugin",
    srcs = glob(
        ["*.cc", "*.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
        "//src/protocols/plugins/time_manipulator_plugin:aimrt_time_manipulator_rpc"
    ],
)
