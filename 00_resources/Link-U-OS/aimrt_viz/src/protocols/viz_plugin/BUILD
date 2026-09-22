load("//local_rules:protobuf_rpc.bzl", "aimrt_cc_protobuf_rpc")
load("@rules_proto//proto:defs.bzl", "proto_library")
load("@rules_cc//cc:defs.bzl", "cc_proto_library")

package(default_visibility = ["//visibility:public"])

proto_library(
    name = "viz_plugin_proto",
    srcs = ["viz_plugin.proto"],
    strip_import_prefix = "/src/protocols/viz_plugin",
)

cc_proto_library(
    name = "viz_plugin_cc_proto",
    deps = [":viz_plugin_proto"],
)

aimrt_cc_protobuf_rpc(
    name = "viz_plugin_rpc",
    proto = "viz_plugin.proto",
    dep_protos = [":viz_plugin_proto"],
    plugin_path = "@integration//:aimrt_protoc_plugin_cpp_gen_aimrt_cpp_rpc",
    plugin_name = "aimrt_rpc",
    output_proto_name = "viz_plugin",
    deps = [":viz_plugin_cc_proto"],
)
