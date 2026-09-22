load("@integration//rules/utils:flattern_tar.bzl", "flatten_tar")
load("@rules_pkg//pkg:mappings.bzl", "pkg_filegroup", "pkg_files", "pkg_attributes")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")

package(default_visibility = ["//visibility:public"])

pkg_files(
    name = "viz_plugin_script",
    # srcs = glob(["install/linux/bin/*.sh"]),
    srcs = select({
       "//conditions:default": ["install/linux/bin/a2/start_viz_module.sh"],
    }),
    strip_prefix = select({
       "//conditions:default": "install/linux/bin/a2",
    }),
    attributes = pkg_attributes(mode = "0755"),
    prefix= "scripts/viz"
)

pkg_files(
    name = "viz_plugin_config",
    # srcs = glob(["install/linux/bin/cfg/*.yaml"]),
    srcs = select({
       "//conditions:default": ["install/linux/bin/a2/viz_module.yaml"],
    }),
    strip_prefix = select({
       "//conditions:default": "install/linux/bin/a2",
    }),
    prefix= "config/viz"
)

pkg_filegroup(
    name = "aimrt_viz_filegroup",
    srcs = [
        ":viz_plugin_script",
        ":viz_plugin_config",
    ],
)

pkg_tar(
    name = "aimrt_viz_without_bin_tar",
    srcs = [
        ":aimrt_viz_filegroup",
    ],
    extension = "tar",
    mode = "0755",
    tags = ["tar"],
)