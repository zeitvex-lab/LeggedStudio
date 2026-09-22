load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "util",
    srcs = [],
    hdrs = glob(["**/*.h"]),
    deps = select({
        "@integration//:use_fmt_lib": ["@fmt"],
        "//conditions:default": [],
    }),
    defines = select({
        "@integration//:use_fmt_lib": ["AIMRT_USE_FMT_LIB"],
        "//conditions:default": [],
    }),
    includes = [".."],
)

