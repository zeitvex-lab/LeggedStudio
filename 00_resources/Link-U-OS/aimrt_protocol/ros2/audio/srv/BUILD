package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "AbandonAudioFocus.srv",
    "CaptureAudioFile.srv",
    "GetMute.srv",
    "GetVolume.srv",
    "PlayAudioFile.srv",
    "RequestAudioFocus.srv",
    "SetMute.srv",
    "SetVolume.srv",
    "StopAudioPlay.srv",
    "StopCaptureAudioFile.srv",
    "GetPlayDevice.srv",
    "SetPlayDevice.srv",
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
