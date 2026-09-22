package(default_visibility = ["//visibility:public"])

filegroup(
    name = "health_monitor_config",
    srcs = select({
        "@integration//toolchains/platforms:is_orin_aarch64": [
            "orin/health_monitor.yaml",
        ],
        "//conditions:default": ["x86/health_monitor.yaml"],
    }),
)
