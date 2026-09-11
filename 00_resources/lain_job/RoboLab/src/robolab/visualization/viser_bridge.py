"""MJLab-environment Viser bridge for backend-neutral ``SceneFrame`` data.

This module intentionally has no MJLab imports. It is launched with the MJLab
Python environment because that environment owns the Viser dependency; other
backends send only serialized :class:`SceneFrame` dictionaries over stdin.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _joint_configuration(frame: dict[str, Any], joint_names: tuple[str, ...]) -> list[float]:
    values = dict(zip(frame["joint_order"], frame["joint_position"]))
    return [float(values[name]) for name in joint_names]


def _network_bars(values: Any) -> str:
    """Render policy outputs as compact horizontal blue bars."""
    bars = []
    for index, raw_value in enumerate(values):
        value = max(-1.0, min(1.0, float(raw_value)))
        width = abs(value) * 100.0
        bars.append(
            '<div style="display:flex;align-items:center;gap:6px;height:13px;">'
            f'<span style="display:inline-block;width:24px;color:#888;font-size:10px;">a{index:02d}</span>'
            '<span style="display:inline-block;width:120px;height:7px;background:#e7edf5;'
            'border-radius:3px;overflow:hidden;">'
            f'<span style="display:block;width:{width:.1f}%;height:100%;background:#1976d2;'
            'border-radius:3px;"></span></span>'
            f'<span style="width:48px;text-align:right;font-size:10px;">{value:+.3f}</span>'
            '</div>'
        )
    return "".join(bars) if bars else '<span style="color:#888">—</span>'


def run_bridge(
    mjcf_path: str | Path,
    *,
    port: int = 8080,
    control_port: int = 8765,
    checkpoints: tuple[str, ...] = (),
    initial_checkpoint: str = "",
    terrain_sequence: tuple[str, ...] = (),
) -> int:
    """Serve a canonical MJCF and consume newline-delimited scene frames."""

    import mujoco
    import numpy as np
    import viser
    from mjviser import ViserMujocoScene

    output_lock = threading.Lock()
    control_lock = threading.Lock()
    control_client: socket.socket | None = None

    control_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    control_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    control_server.bind(("127.0.0.1", control_port))
    control_server.listen(1)
    control_server.settimeout(0.2)

    def accept_control() -> None:
        nonlocal control_client
        while control_client is None:
            try:
                client, _ = control_server.accept()
                with control_lock:
                    control_client = client
            except socket.timeout:
                continue
            except OSError:
                return

    threading.Thread(target=accept_control, daemon=True).start()

    def send_control(payload: dict[str, Any]) -> None:
        with output_lock:
            with control_lock:
                if control_client is not None:
                    try:
                        control_client.sendall((json.dumps(payload) + "\n").encode())
                    except OSError:
                        pass

    server = viser.ViserServer(label="robolab-mjlab", port=port)
    model = mujoco.MjModel.from_xml_path(str(mjcf_path))
    data = mujoco.MjData(model)
    scene = ViserMujocoScene(server, model, num_envs=1)
    scene.create_scene_gui()
    # Keep Isaac Gym and terrain in one world frame.  The mjviser default
    # camera tracking recenters the robot every update, which makes a moving
    # robot look stationary relative to an external terrain handle.
    scene.camera_tracking_enabled = False
    terrain_handles: list[Any] = []
    active_terrain: tuple[str, int] = ("", -1)

    def set_terrain(terrain: str | dict[str, Any]) -> None:
        """Display the collision terrain serialized by the Isaac Gym worker."""
        nonlocal terrain_handles, active_terrain
        if isinstance(terrain, str):
            terrain = {"name": terrain, "revision": 0}
        name = str(terrain.get("name", "plane"))
        revision = int(terrain.get("revision", 0))
        if (name, revision) == active_terrain:
            return
        new_handles: list[Any] = []
        try:
            path = f"/terrain/{name}_{revision}"
            if name == "plane":
                new_handles.append(
                    server.scene.add_grid(
                        path, width=20.0, height=20.0, plane="xy",
                        plane_color=(110, 120, 110), plane_opacity=0.35,
                    )
                )
            else:
                height_field = terrain.get("height_field")
                if height_field:
                    import trimesh

                    heights = np.asarray(height_field, dtype=np.float64)
                    scale_xy = float(terrain.get("horizontal_scale", 0.1))
                    scale_z = float(terrain.get("vertical_scale", 0.005))
                    origin = np.asarray(terrain.get("origin", (0.0, 0.0, 0.0)), dtype=np.float64)
                    rows, cols = heights.shape
                    xx, yy = np.meshgrid(
                        (np.arange(rows) - (rows - 1) / 2.0) * scale_xy + origin[0],
                        (np.arange(cols) - (cols - 1) / 2.0) * scale_xy + origin[1],
                        indexing="ij",
                    )
                    vertices = np.column_stack((xx.ravel(), yy.ravel(), heights.ravel() * scale_z))
                    faces = []
                    for i in range(rows - 1):
                        for j in range(cols - 1):
                            a = i * cols + j
                            b, c, d = a + 1, a + cols, a + cols + 1
                            faces.extend(((a, c, b), (b, c, d)))
                    mesh = trimesh.Trimesh(vertices=vertices, faces=np.asarray(faces), process=False)
                    mesh.visual.vertex_colors = np.tile(
                        np.asarray([125, 105, 85, 255], dtype=np.uint8),
                        (len(mesh.vertices), 1),
                    )
                    # This Viser version accepts only the trimesh object and
                    # transform kwargs; color/opacity are encoded in the
                    # trimesh material above.
                    new_handles.append(server.scene.add_mesh_trimesh(path, mesh))
                else:
                    # Preview fallback used before the first backend frame.
                    for index in range(9):
                        x = (index % 3 - 1) * 2.0
                        y = (index // 3 - 1) * 2.0
                        height = 0.12 if name == "rough" else (0.2 * (index % 3 + 1) if name == "stairs" else 0.08)
                        new_handles.append(
                            server.scene.add_box(
                                f"{path}_{index}", dimensions=(1.8, 1.8, height),
                                position=(x, y, height / 2.0),
                                color=(125, 105, 85) if name == "rough" else (100, 110, 125), opacity=0.85,
                            )
                        )
        except Exception as exc:
            for handle in new_handles:
                handle.remove()
            status.content = (
                f'<span style="color:red">Terrain upload failed: {type(exc).__name__}: {exc}</span>'
            )
            return
        for handle in terrain_handles:
            handle.remove()
        terrain_handles = new_handles
        active_terrain = (name, revision)

    set_terrain({"name": "plane", "revision": 0})
    joint_names = tuple(
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        for index in range(model.njnt)
        if model.jnt_type[index] == mujoco.mjtJoint.mjJNT_HINGE
    )
    status = server.gui.add_html("Waiting for SceneFrame…")
    network_html = server.gui.add_html("Network output: —")
    with server.gui.add_folder("Policy / Commands"):
        checkpoint_paths = tuple(dict.fromkeys(
            str(Path(path).resolve()) for path in checkpoints if str(path).strip()
        ))
        checkpoint_paths = checkpoint_paths or ((str(Path(initial_checkpoint).resolve()),) if initial_checkpoint else ())
        checkpoint_labels = tuple(Path(path).name for path in checkpoint_paths)
        checkpoint_by_label = dict(zip(checkpoint_labels, checkpoint_paths))
        initial_label = Path(initial_checkpoint).name if initial_checkpoint else (
            checkpoint_labels[0] if checkpoint_labels else "current"
        )
        policy_select = server.gui.add_dropdown(
            "Checkpoint",
            # Show a readable filename in Viser.  The full absolute path is
            # kept in the bridge-side map and sent to the backend only when a
            # user changes the selection.
            options=checkpoint_labels or ("current",),
            initial_value=initial_label,
        )
        speed_range = server.gui.add_slider(
            "Speed range", min=0.5, max=3.0, step=0.1, initial_value=2.0,
            hint="Absolute range applied to vx, vy and vw sliders.",
        )
        vx = server.gui.add_slider("vx", min=-2.0, max=2.0, step=0.05, initial_value=0.0)
        vy = server.gui.add_slider("vy", min=-2.0, max=2.0, step=0.05, initial_value=0.0)
        vw = server.gui.add_slider("vw", min=-2.0, max=2.0, step=0.05, initial_value=0.0)
        zero_velocity = server.gui.add_button("Zero velocity")
        terrain_select = server.gui.add_dropdown(
            "Terrain", options=("plane", "rough", "stairs", "obstacles"), initial_value="plane"
        )

        @policy_select.on_update
        def _(_) -> None:
            selected = checkpoint_by_label.get(str(policy_select.value), initial_checkpoint)
            send_control({"type": "checkpoint", "path": str(selected)})

        def send_command(_) -> None:
            send_control({"type": "command", "vx": float(vx.value), "vy": float(vy.value), "vw": float(vw.value)})

        def update_speed_range(_) -> None:
            limit = float(speed_range.value)
            for slider in (vx, vy, vw):
                slider.min = -limit
                slider.max = limit
                slider.value = max(-limit, min(limit, float(slider.value)))
            send_command(_)

        speed_range.on_update(update_speed_range)
        vx.on_update(send_command)
        vy.on_update(send_command)
        vw.on_update(send_command)

        @zero_velocity.on_click
        def _(_) -> None:
            vx.value = 0.0
            vy.value = 0.0
            vw.value = 0.0
            send_command(_)

        @terrain_select.on_update
        def _(_) -> None:
            # Do not replace the displayed terrain optimistically.  Wait for
            # the worker's committed terrain payload so a failed/rejected
            # Isaac Gym rebuild cannot leave an empty scene.
            send_control({"type": "terrain", "name": str(terrain_select.value)})
    print(f"viser (listening *:{server.get_port()})", flush=True)
    print(f"HTTP http://localhost:{server.get_port()}", flush=True)
    print(f"Websocket ws://localhost:{server.get_port()}", flush=True)

    if terrain_sequence:
        def _run_terrain_sequence() -> None:
            # This is an explicit integration-test hook; normal play leaves it empty.
            time.sleep(2.0)
            for name in terrain_sequence:
                terrain_select.value = name
                send_control({"type": "terrain", "name": name})
                print(f"Terrain test requested: {name}", flush=True)
                time.sleep(3.0)
        threading.Thread(target=_run_terrain_sequence, daemon=True).start()

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            frame = payload.get("scene_frame", payload)
            training = payload.get("training_frame", {})
            backend_terrain = payload.get("terrain", {"name": "plane", "revision": 0})
            set_terrain(backend_terrain)
            # Isaac Gym reports the world-space free-joint pose. MuJoCo uses
            # the same convention for a free joint, so no terrain/body offset
            # is applied here. The terrain world origin remains z=0.
            data.qpos[:3] = np.asarray(frame["root_position"], dtype=np.float64)
            data.qpos[3:7] = np.asarray(frame["root_orientation"], dtype=np.float64)
            values = _joint_configuration(frame, joint_names)
            qpos_indices = [int(model.jnt_qposadr[index]) for index in range(model.njnt)
                            if model.jnt_type[index] == mujoco.mjtJoint.mjJNT_HINGE]
            data.qpos[qpos_indices] = np.asarray(values, dtype=np.float64)
            mujoco.mj_forward(model, data)
            scene.update_from_mjdata(data)
            network = payload.get("network_output", ())
            network_html.content = (
                '<div style="font-weight:600;margin-bottom:4px;">Network output</div>'
                + _network_bars(network)
            )
            command = ", ".join(f"{x:.2f}" for x in frame.get("command", ()))
            contacts = ", ".join(frame.get("contacts", ())) or "none"
            status.content = (
                f"<b>{frame.get('robot', 'robot')}</b>"
                f"<br/>Step: {training.get('step', '—')}"
                f"<br/>Backend: {training.get('backend', '—')}"
                f"<br/>Terrain preview: {terrain_select.value}"
                f"<br/>Reward: {float(frame.get('reward', 0.0)):.3f}"
                f"<br/>Command: {command}<br/>Contacts: {contacts}"
                + "".join(
                    f"<br/>{key}: {float(value):.3f}"
                    for key, value in training.get("metrics", {}).items()
                )
            )
        except Exception as exc:  # Keep the viewer alive for malformed frames.
            status.content = f"<span style='color:red'>Frame error: {exc}</span>"
    server.stop()
    control_server.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mjcf", required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--checkpoints", nargs="*", default=[])
    parser.add_argument("--initial-checkpoint", default="")
    parser.add_argument("--control-port", type=int, default=8765)
    parser.add_argument("--terrain-sequence", nargs="*", default=[])
    args = parser.parse_args(argv)
    return run_bridge(
        args.mjcf,
        port=args.port,
        checkpoints=tuple(args.checkpoints),
        initial_checkpoint=args.initial_checkpoint,
        control_port=args.control_port,
        terrain_sequence=tuple(args.terrain_sequence),
    )


if __name__ == "__main__":
    raise SystemExit(main())
