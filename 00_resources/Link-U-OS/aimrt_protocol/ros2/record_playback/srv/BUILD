package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "GetActionList.srv",
    "GetBagList.srv",
    "StartRecord.srv",
    "StopRecord.srv",
    "GetUploadAllowed.srv",
    "UpdateRecordAction.srv",
])

filegroup(
    name = "ros2_files",
    srcs = glob(
        [
            "**",
        ],
        exclude = ["BUILD"],
    ),
)
