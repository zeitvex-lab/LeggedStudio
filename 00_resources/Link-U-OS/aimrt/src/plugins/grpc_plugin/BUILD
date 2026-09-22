package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_grpc_plugin",
    srcs = glob(
        ["**/*.cc"],
        exclude = ["**/*_test.cc"],
    ) + glob(
        ["**/*.h"],
        exclude = ["**/*_test.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
        "//src/common/net",
        "@integration//:nghttp2",
    ],
)
