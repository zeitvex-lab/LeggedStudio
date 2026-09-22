package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_mqtt_plugin",
    srcs = glob(
        ["*.cc", "*.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
        "@integration//:paho_mqtt_c",
    ],
)
