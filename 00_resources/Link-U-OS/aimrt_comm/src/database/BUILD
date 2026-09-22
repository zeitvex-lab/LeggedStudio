package(default_visibility = ["//visibility:public"])

cc_library(
    name = "database",
    hdrs = glob(["**/*.h"]),
    srcs = glob(["**/*.cpp"]),
    deps = [
        "//src/ctx",
        "@integration//:sqlcipher",
        "@integration//:openssl",
    ],
)
