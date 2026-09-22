package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_iceoryx_plugin",
    srcs = glob(
        ["*.cc"],
        exclude = ["*_test.cc"],
    ) + glob(
        ["*.h"],
        exclude = ["*_test.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
        "@integration//:iceoryx",
    ],
)
