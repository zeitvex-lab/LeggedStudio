load("@rules_pkg//pkg:mappings.bzl", "pkg_filegroup", "pkg_files", "pkg_attributes")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "process_manager",
    srcs = ["main.cc"],
    deps = [
        "@com_github_gflags_gflags//:gflags",
        "@aimrt//src/runtime/core",
        "//src/module:process_manager_module",
        "//src/process_manager",
    ],
)

pkg_files(
    name = "process_manager_config",
    srcs = [
        "//config/process_manager:process_manager_config",
    ],
    prefix = "config/process_manager",
)

pkg_files(
    name = "process_manager_script",
    srcs = [
        "//scripts/process_manager:process_manager_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",  
    ),
    prefix = "scripts/process_manager",
    
)


pkg_filegroup(
    name = "process_manager_filegroup",
    srcs = [
        ":process_manager_config",
        ":process_manager_script",
    ],
)

pkg_tar(
    name = "process_manager_without_bin_tar",
    srcs = [
        "//src/app:process_manager_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "process_manager_bin_tar",
    srcs = [
        ":process_manager",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "process_manager_bin_flatten_tar",
    src = "//src/app:process_manager_bin_tar",
    prefix = "bin",
)

