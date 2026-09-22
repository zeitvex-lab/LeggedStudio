package(default_visibility = ["//visibility:public"])

cc_library(
    name = "net",
    hdrs = glob(["*.h"]),
    deps = [
        "//src/common/util",
        "@integration//:boost", 
    ],
    defines = ["BOOST_ASIO_NO_DEPRECATED"], 
)