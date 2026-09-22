load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_filegroup", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")

package(default_visibility = ["//visibility:public"])

pkg_files(
    name = "program_config",
    srcs = [
        "//config/example/program:program_config",
    ],
    prefix = "config/example/program",
)

pkg_files(
    name = "program_script",
    srcs = [
        "//scripts/example/program:program_script",
    ],
    attributes = pkg_attributes(
        mode = "0755",
    ),
    prefix = "scripts/example/program",
)

pkg_filegroup(
    name = "program_filegroup",
    srcs = [
        ":program_config",
        ":program_script",
    ],
)

pkg_tar(
    name = "program_without_bin_tar",
    srcs = [
        ":program_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)

pkg_tar(
    name = "program_bin_tar",
    srcs = [
        "//example/program/app_mode:example-program-app_mode",
        "//example/program/pkg_mode:example-use_pkg_mode",
    ],
    extension = "tar",
    include_runfiles = True,
    mode = "0755",
    tags = ["tar"],
)

flatten_tar(
    name = "program_flatten_bin_tar",
    src = ":program_bin_tar",
    prefix = "bin",
)
