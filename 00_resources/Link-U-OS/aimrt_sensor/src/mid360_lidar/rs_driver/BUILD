package(default_visibility = ["//visibility:public"])

cc_library(
    name = "rs_driver",
    hdrs = glob(
        ["**/*.hpp"],
    ),
    deps = [
        "@aimrt_comm//src/ctx",
    ],
    strip_include_prefix = ".",
    include_prefix = "rs_driver",
    defines = [
        "DISABLE_PCAP_PARSE",
        # "ENABLE_WAIT_IF_QUEUE_EMPTY"  # 这个不需要打开，打开会轮询，消耗CPU资源
    ],

)