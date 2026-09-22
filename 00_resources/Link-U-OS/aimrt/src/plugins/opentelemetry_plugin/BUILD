package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_opentelemetry_plugin",
    srcs = glob(
        ["*.cc", "*.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
        "@integration//:opentelemetry_cpp",
    ],
    defines = ["OPENTELEMETRY_STL_VERSION=2020"],
)
