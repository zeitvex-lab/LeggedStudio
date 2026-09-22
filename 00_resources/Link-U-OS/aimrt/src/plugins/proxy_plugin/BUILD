package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_proxy_plugin",
    srcs = glob(
        ["*.cc", "*.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
    ],
)
