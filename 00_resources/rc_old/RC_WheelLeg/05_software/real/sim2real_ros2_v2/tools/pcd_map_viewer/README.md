# PCD Map Viewer

Offline Web tool for Odin PCD inspection and route editing.

This is not the Nano runtime Web UI. Use it before a run to inspect the map and save route YAML files.

## Archived Dependency Boundary

The Python server and application source are archived, but the original Three.js static files are not. The 3D page therefore is **not** ready to run from a fresh clone until these compatible files are supplied:

```text
tools/pcd_map_viewer/vendor/three.module.js
tools/pcd_map_viewer/vendor/jsm/controls/OrbitControls.js
```

You may place them in that local `vendor/` layout or pass another directory with `--vendor-dir`. Keep both files from the same Three.js release. Their exact original release and redistribution terms were not recorded in this snapshot, so this repository does not silently substitute a guessed version.

## Start

From the repository root:

```powershell
python .\05_software\real\sim2real_ros2_v2\tools\pcd_map_viewer\server.py --http-port 8090
```

With an external vendor directory:

```powershell
python .\05_software\real\sim2real_ros2_v2\tools\pcd_map_viewer\server.py --vendor-dir C:\path\to\three-vendor --http-port 8090
```

Open:

```text
http://127.0.0.1:8090
```

You can also run directly from this directory:

```powershell
python server.py --http-port 8090
```

## What It Does

- Scans `map/*.pcd`.
- Shows raw Odin PCD as a rotatable 3D point cloud.
- Supports z filtering, default `z=-2.0..1.0m`.
- Supports voxel display for structure checks.
- Provides a simplified 2D layer view.
- Lets you click waypoints in 3D or 2D.
- Lets you draw obstacle terrain rectangles and edit their x/y/yaw/size.
- Tags new waypoints with the matching obstacle terrain, defaulting to `flat`.
- Saves route YAML and JSON under `map/routes/<pcd_name>/`.

## Route Fields

Saved waypoint fields:

- `x`
- `y`
- `yaw_deg`
- `speed`
- `policy`
- `tolerance`
- `obstacle`
- `obstacle_name`

Not saved:

- `z`
- `action`

The browser may keep local `_viewZ` only for drawing markers in 3D. The runtime route runner is planar.

## Saved Format

```yaml
name: test_route
map: map1
frame_id: map
obstacles:
  - id: 1
    name: wall_1
    obstacle: wall
    x: 1.5000
    y: 2.0000
    yaw_deg: 0.00
    length: 1.000
    width: 0.500
    policy: rough
waypoints:
  - id: 1
    x: 1.0000
    y: 2.0000
    yaw_deg: 0.00
    speed: 0.350
    policy: rough
    tolerance: 0.150
    obstacle: wall
    obstacle_name: wall_1
```

The current `v0.12.0` runtime route is configured separately in `src/sim2real_bringup/config/runtime.yaml`:

```text
map/routes/A_min/A_min_route.json
```

The editor can also save YAML, but the archived runtime does not provide the `/route_runner/cmd` interface described by an earlier draft. Use the current JSON task file and Web/navigation controls documented by this snapshot.

See also:

- [Archived map data](../../map/README.md)
- [ROS 2 v2 snapshot](../../README.md)
