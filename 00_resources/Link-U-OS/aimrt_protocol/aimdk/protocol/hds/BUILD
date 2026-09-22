package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "alert_channel.proto",
    "alert.proto",
    "exception_channel.proto",
    "exception.proto",
    "fallback_channel.proto",
    "hds_service.proto",
    "health_channel.proto",
    "health.proto",
    "system_status.proto",
    "ExceptionChannel.msg",
    "Exception.msg",
])

filegroup(
    name = "ros2_files",
    srcs = glob(
        [
            "*.msg",
        ],
    ) + [
        "CMakeLists.txt",
        'package.xml'
    ],
)
