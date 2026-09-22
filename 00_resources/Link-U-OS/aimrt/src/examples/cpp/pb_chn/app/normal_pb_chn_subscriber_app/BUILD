package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "normal_pb_chn_subscriber_app",
    srcs = ["main.cc"],
    deps = [
        "//src/interface/aimrt_module_protobuf_interface",
        "//src/protocols/pb/example:event_cc_proto",
        "//src/runtime/core",
        "@com_github_gflags_gflags//:gflags",
    ],
)
