load("@integration//rules/utils:header_utils.bzl", "cc_library_with_top_header")

package(default_visibility = ["//visibility:public"])

cc_library_with_top_header(
    name = "trace",
    srcs = [
    ],
    hdrs = glob(["**/*.h"]),
    deps = [
        "//src/core",
        "//src/utils",
    ],
)

cc_test(
    name = "boolean_test",
    srcs = [
        "boolean_test.cc",
    ],
    deps = [
        ":trace",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "counter_test",
    srcs = [
        "counter_test.cc",
    ],
    deps = [
        ":trace",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "event_test",
    srcs = [
        "event_test.cc",
    ],
    deps = [
        ":trace",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "gauage_test",
    srcs = [
        "gauage_test.cc",
    ],
    deps = [
        ":trace",
        "//src/test",
    ],
    linkstatic = True,
)

cc_test(
    name = "long_event_test",
    srcs = [
        "long_event_test.cc",
    ],
    deps = [
        ":trace",
        "//src/test",
    ],
    linkstatic = True,
)
