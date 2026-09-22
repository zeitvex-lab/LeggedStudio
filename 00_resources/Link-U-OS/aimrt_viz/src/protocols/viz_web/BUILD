load("//local_rules:protobuf_rpc.bzl", "aimrt_cc_protobuf_rpc")
load("@rules_proto//proto:defs.bzl", "proto_library")
load("@rules_cc//cc:defs.bzl", "cc_proto_library")

package(default_visibility = ["//visibility:public"])

proto_library(
    name = "viz_web_proto",
    srcs = glob(["*.proto"]),
    strip_import_prefix = "/src/protocols/viz_web",
)

cc_proto_library(
    name = "viz_web_cc_proto",
    deps = [":viz_web_proto"],
)

cc_library(
    name = "viz_web_cc_lib",
    srcs = glob(["*.cc"]),
    hdrs = glob(["*.h"]),
    deps = [":viz_web_cc_proto","@integration//:protobuf"],
)

aimrt_cc_protobuf_rpc(
    name = "viz_web_rpc",
    proto = "viz_web.proto",
    dep_protos = [":viz_web_proto"],
    plugin_path = "@integration//:aimrt_protoc_plugin_cpp_gen_aimrt_cpp_rpc",
    plugin_name = "aimrt_rpc",
    output_proto_name = "viz_web",
    deps = [":viz_web_cc_lib"],
)