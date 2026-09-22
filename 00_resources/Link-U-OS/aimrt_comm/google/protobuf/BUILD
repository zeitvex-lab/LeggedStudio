load("@bazel_skylib//rules:copy_file.bzl", "copy_file")

package(default_visibility = ["//visibility:public"])

copy_file(
    name = "any_proto_copy",
    src = "@aimrt_protocol//google/protobuf:any.proto",
    out = "any.proto",
)


proto_library(
    name = "any_proto",
    srcs = [":any_proto_copy"],
    deps = [],
)

