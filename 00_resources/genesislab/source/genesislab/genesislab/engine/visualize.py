from __future__ import annotations

from pathlib import Path
from typing import Optional

import genesis as gs


def attach_video_recorder(scene: gs.Scene, video_path: str, *, width: int = 1280, height: int = 720, fps: int = 60) -> None:
    """Attach a simple chase camera to the scene and start recording to an mp4 file.

    This is a thin wrapper around Genesis' recording API to keep all video
    wiring in one place.
    """
    path = Path(video_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    camera = scene.add_camera(
        res=(width, height),
        pos=(3.5, 0.0, 2.5),
        lookat=(0.0, 0.0, 0.5),
        fov=40,
        GUI=False,
    )

    scene.start_recording(
        data_func=lambda: camera.render(
            rgb=True,
            depth=False,
            segmentation=False,
            normal=False,
        )[0],
        rec_options=gs.recorders.VideoFile(
            filename=str(path),
            fps=fps,
            codec="libx264",
            codec_options={"preset": "veryfast", "tune": "zerolatency"},
        ),
    )


def stop_video_recorder(scene: gs.Scene) -> None:
    """Stop any active recording on the given scene (no-op if none)."""
    try:
        scene.stop_recording()
    except Exception:
        # Swallow errors to avoid breaking control flow on play / debug scripts.
        pass

