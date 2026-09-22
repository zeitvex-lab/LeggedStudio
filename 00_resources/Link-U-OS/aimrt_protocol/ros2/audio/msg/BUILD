package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "AudioCapture.msg",
    "AudioData.msg",
    "AudioInfo.msg",
    "AudioFile.msg",
    "AudioPlayback.msg",
    "FocusRequester.msg",
    "FocusResponse.msg",
    "VolumeType.msg",
    "VolumeChange.msg",
    "PlayStateType.msg",
    "PlayStateChange.msg",
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
