package(default_visibility = ["//visibility:public"])

cc_library(
    name = "aimrt_module_cpp_interface",
    hdrs = glob(
        ["**/*.h"],
        exclude = ["**/*_test.h"],
    ) + ["//:aimrt_runtime_version.h"],
    includes = [".."],
    deps = [
        "//src/common/util",
        "//src/interface/aimrt_module_c_interface",
    ] + select({
        "@integration//:use_stdexec": ["@stdexec"],
        "//conditions:default": ["@integration//:unifex"],
    }),
    defines = select({
        "@integration//:use_stdexec": ["AIMRT_EXECUTOR_USE_STDEXEC"],
        "//conditions:default": [],
    }) + select({
        "@integration//:use_global_logger": ["AIMRT_CONTEXT_DEFINE_GLOBAL_LOGGER_HANDLE"],
        "//conditions:default": [],
    }),
)

