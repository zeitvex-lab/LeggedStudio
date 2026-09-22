# Provider for storing information about generated protobuf RPC files
load("@rules_proto//proto:defs.bzl", "ProtoInfo")

ProtobufRpcInfo = provider(fields = ["hdrs", "srcs", "protos"])

_template_script = '''#!/bin/bash
set -e

proto_path=%s
output_dir=%s
expected_prefix=%s

# Extract the directory containing the proto file
proto_dir=$(dirname "$proto_path")

# Run protoc with the proto directory as import path
%s --proto_path="$proto_dir" %s "$proto_path"

# Rename files if needed to match expected names
if [[ -n "$expected_prefix" ]]; then
  proto_basename=$(basename "$proto_path" .proto)
  if [[ "$expected_prefix" != "$proto_basename" ]]; then
    # Fix include paths in .cc file before renaming
    if [[ -f "$output_dir/${proto_basename}.aimrt_rpc.pb.cc" ]]; then
      sed -i "s|${proto_basename}.aimrt_rpc.pb.h|${expected_prefix}.aimrt_rpc.pb.h|g" "$output_dir/${proto_basename}.aimrt_rpc.pb.cc"
      mv "$output_dir/${proto_basename}.aimrt_rpc.pb.cc" "$output_dir/${expected_prefix}.aimrt_rpc.pb.cc"
    fi
    # Rename .h file
    if [[ -f "$output_dir/${proto_basename}.aimrt_rpc.pb.h" ]]; then
      mv "$output_dir/${proto_basename}.aimrt_rpc.pb.h" "$output_dir/${expected_prefix}.aimrt_rpc.pb.h"
    fi
  fi
fi
'''


def aimrt_cc_protobuf_rpc(
    name,
    proto,
    plugin_path,
    plugin_name = "aimrt_rpc",
    includes = [],
    deps = [],
    copts = [],
    dep_protos = [],
    output_proto_name = None):
    # Add required AIMRT dependencies
    all_deps = deps + [
        "@aimrt//src/interface/aimrt_module_cpp_interface",
        "@aimrt//src/interface/aimrt_module_protobuf_interface",
    ]

    # Create unique names for intermediate targets
    generate_name = "%s_pb_cc" % name
    name_hdrs_cc = "%s_hdrs_cc" % name
    name_srcs_cc = "%s_srcs_cc" % name

    # Generate RPC code from protobuf using the specified plugin
    _protobuf_rpc(
        name = generate_name,
        proto = proto,
        dep_protos = dep_protos,
        plugin_name = plugin_name,
        plugin_path = plugin_path,
        includes = includes,
        output_proto_name = output_proto_name,
    )

    # Extract generated header files
    _cc_package_protobuf_rpc_hdrs(
        name = name_hdrs_cc,
        srcs = [generate_name],
        field = "hdrs",
    )

    # Extract generated source files
    _cc_package_protobuf_rpc_srcs(
        name = name_srcs_cc,
        srcs = [generate_name],
        field = "srcs",
    )

    # Create final C++ library with generated code
    native.cc_library(
        name = name,
        srcs = [name_srcs_cc],
        hdrs = [name_hdrs_cc],
        deps = all_deps,
        copts = copts,
    )

def _protobuf_rpc_impl(ctx):
    # Retrieve tools and input files
    protoc = ctx.executable.protoc
    plugin = ctx.executable.plugin_path
    proto = ctx.file.proto
    dep_protos = ctx.attr.dep_protos
    plugin_name = ctx.attr.plugin_name
    filename_without_ext = (proto.basename).split(".")[0]

    # Configure output filenames - use output_proto_name if provided
    final_filename = ctx.attr.output_proto_name if ctx.attr.output_proto_name else filename_without_ext
    if plugin_name == "aimrt_rpc":
        final_filename = "{}.{}.pb".format(final_filename, plugin_name)
    gen_rpc_pb_cc = ctx.actions.declare_file("{}.cc".format(final_filename))
    gen_rpc_pb_hdr = ctx.actions.declare_file("{}.h".format(final_filename))

    # Collect output files
    output_hdrs = [gen_rpc_pb_hdr]
    output_srcs = [gen_rpc_pb_cc]

        # Collect all proto files and their import paths
    all_protos = [proto]
    proto_paths = {}  # Use dict as set in Starlark

    for dep in dep_protos:
        if ProtoInfo in dep:
            # Include all transitive imports
            for import_file in dep[ProtoInfo].transitive_imports.to_list():
                all_protos.append(import_file)
                proto_paths[import_file.dirname] = True
            # Include direct sources
            for source_file in dep[ProtoInfo].direct_sources:
                all_protos.append(source_file)
                proto_paths[source_file.dirname] = True

    # Add the main proto file's directory
    proto_paths[proto.dirname] = True

    # Construct protoc command arguments
    args = []

    # Add all discovered proto paths
    for path in proto_paths.keys():
        args.append("--proto_path={}".format(path))

    # Add user-specified include paths
    for include_path in ctx.attr.includes:
        args.append("--proto_path={}".format(include_path))

    # Use the directory where the proto file will be placed for output
    output_dir = gen_rpc_pb_cc.dirname
    args.append("--{}_out={}".format(plugin_name, output_dir))
    args.append("--plugin=protoc-gen-{}={}".format(plugin_name, plugin.path))

    # Create shell script for execution
    sh_script = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(
        output = sh_script,
        content = _template_script % (
            proto.path,
            output_dir,
            ctx.attr.output_proto_name if ctx.attr.output_proto_name else "",
            protoc.path,
            " ".join(args),
        ),
        is_executable = True,
    )

    # Execute protoc with plugin
    ctx.actions.run(
        inputs = all_protos,
        tools = [protoc, plugin],
        outputs = output_hdrs + output_srcs,
        executable = sh_script,
        progress_message = "Generating protobuf RPC code for {}".format(proto.short_path),
        use_default_shell_env = True,
    )

    # Return providers with generated file information
    default_info = DefaultInfo(
        files = depset(output_hdrs),
    )
    rpc_cc_info = ProtobufRpcInfo(
        srcs = depset(output_srcs),
        hdrs = depset(output_hdrs),
        protos = depset([proto]),
    )

    return [default_info, rpc_cc_info]

# Rule definition for protobuf RPC code generation
_protobuf_rpc = rule(
    implementation = _protobuf_rpc_impl,
    attrs = {
        "proto": attr.label(
            mandatory = True,
            allow_single_file = [".proto"],
            doc = "Input .proto source file",
        ),
        "dep_protos": attr.label_list(
            default = [],
            providers = [ProtoInfo],
            doc = "Input dependent .proto source files",
        ),
        "protoc": attr.label(
            default = "@com_google_protobuf//:protoc",
            executable = True,
            cfg = "exec",
            doc = "Protoc compiler executable",
        ),
        "plugin_name": attr.string(
            default = "aimrt_rpc",
            doc = "Plugin name (prefix for protoc-gen-{name})",
        ),
        "plugin_path": attr.label(
            mandatory = True,
            executable = True,
            cfg = "exec",
            allow_single_file = True,
            doc = "Path to the plugin executable",
        ),
        "includes": attr.string_list(
            default = [],
            doc = "List of include directories",
        ),
        "output_proto_name": attr.string(
            doc = "Output proto name",
        ),
    },
)

# Implementation for extracting specific file types from generated outputs
def _cc_package_files_impl(ctx):
    files = []
    target_field = ctx.attr.field
    for src in ctx.attr.srcs:
        target_files = getattr(src[ProtobufRpcInfo], target_field)
        files.extend(target_files.to_list())
    return [DefaultInfo(files = depset(files))]

# Rule for collecting and packaging header files
_cc_package_protobuf_rpc_hdrs = rule(
    implementation = _cc_package_files_impl,
    attrs = {
        "srcs": attr.label_list(
            mandatory = True,
            providers = [ProtobufRpcInfo],
        ),
        "field": attr.string(
            mandatory = True,
        ),
    },
)

# Rule for collecting and packaging source files
_cc_package_protobuf_rpc_srcs = rule(
    implementation = _cc_package_files_impl,
    attrs = {
        "srcs": attr.label_list(
            mandatory = True,
            providers = [ProtobufRpcInfo],
        ),
        "field": attr.string(
            mandatory = True,
        ),
    },
)