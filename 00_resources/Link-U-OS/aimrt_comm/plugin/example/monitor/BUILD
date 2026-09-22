package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "monitor",
    srcs = [
        "main.cpp",
        "time_wheel_executor.cc",
        "time_wheel_executor.h",
        "worker.cc",
        "worker.h",
    ],
    deps = [
        "//:aimrte",
        "//aimdk/protocol/demo:demo_service_rpc",
        "//aimdk/protocol/demo:demo_channel_cc_proto",
    ],
)
