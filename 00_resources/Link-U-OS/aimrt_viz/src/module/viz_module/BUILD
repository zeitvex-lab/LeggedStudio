load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@rules_pkg//pkg:mappings.bzl", "pkg_files")
load("@integration//rules/utils:pkg_lib.bzl", "pkg_lib")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

genrule(
    name = "generate_version_header",
    srcs = ["//:VERSION"],
    outs = ["version.h"],
    cmd = """
        VERSION=$$(cat $(location //:VERSION) | tr -d '\\n\\r')
        echo '#pragma once' > $@
        echo '#define AIMRT_VIZ_VERSION "'"$$VERSION"'"' >> $@
    """,
)

cc_library(
    name = "viz_module",
    srcs = glob([
        "*.cc",
    ], exclude = [
        "**/*_test.cc",
    ]) + [":generate_version_header"],
    hdrs = glob([
        "*.h",
    ]),
    strip_include_prefix = ".",
    include_prefix = "viz_module",
    includes = [".", "..", "../.."],
    deps = [
        "@aimrt//src/interface/aimrt_core_plugin_interface",
        "@aimrt//src/interface/aimrt_module_c_interface",
        "@aimrt//src/interface/aimrt_module_cpp_interface",
        "@aimrt//src/interface/aimrt_module_protobuf_interface",
        "@aimrt//src/runtime/core",
        "//src/protocols/viz_plugin:viz_plugin_rpc",
        "//src/protocols/viz_web:viz_web_rpc",
    ],
)
