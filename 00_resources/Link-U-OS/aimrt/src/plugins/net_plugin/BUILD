package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_net_plugin",
    srcs = glob(
        ["**/*.cc", "**/*.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/common/net",
        "//src/runtime/core",
    ],
)
