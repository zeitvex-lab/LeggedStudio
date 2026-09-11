# microduck_maploc

2D ToF-based submap SLAM (pose-graph + loop closure), boot-time Monte Carlo relocalization, A\* path planning, and a streaming protocol — for the [microduck](https://github.com/apirrone/microduck_runtime) robot, running on a Radxa Zero 3 (4× Cortex-A55).

The crate is sensor-agnostic and runtime-agnostic. The duck's runtime feeds it odometry deltas + horizontal-plane ToF scans; the crate maintains an occupancy map (as anchored submaps composited into a global grid), corrects drift via loop closure over an SE(2) pose graph, plans on the composite with A\*, and (optionally) runs a TCP server that streams telemetry to a laptop viewer and receives goal clicks back.

## Modules

| Module           | Purpose |
|------------------|---------|
| `grid`           | Log-odds occupancy grid (i16 fixed-point), Bresenham ray integration, ray casting, cached Euclidean distance field, save/load (`MDLM`, also in-memory via `to_bytes`/`read_from`). |
| `submap` / `submap_manager` | Local grids anchored at SE(2) poses; lifecycle (freeze on age/travel), retained raw scans for loop closure. |
| `scan_matcher`   | Hector-style Gauss-Newton scan-to-map matching on the distance field, optional pose prior. Residual is beam-only, scored at the final pose. |
| `pose_graph` / `optimizer` | SE(2) nodes + relative-pose edges; dense Gauss-Newton over the full graph, first node fixed. |
| `loop_closer`    | Submap-to-submap closures: coarse correlative pre-search (±0.5 m × ±20°) then GN refinement priored at the coarse winner. |
| `mcl`            | Boot-time relocalize-from-uniform against a saved map: tempered likelihood, systematic resampling, free-cell injection, cluster-based lock. No internal motion gate — the consumer must require real motion before accepting a lock (the runtime does). |
| `relocalize`     | One-shot brute-force pose search (coarse over free cells × yaw, top-K refined), used as diagnostic + MCL seeding. |
| `planner`        | A\* on the grid with obstacle inflation + supercover line-of-sight smoothing. Filters single-beam noise via `occ_threshold_fp`. |
| `follower`       | Turn-then-go waypoint controller with hysteresis. Inputs: estimated pose. Outputs: body-frame velocities `(vx, wz)`. |
| `session`        | Save/load the full SLAM state (submaps + graph + tracked pose), atomic + fsynced. |
| `wire` / `stream` | Framed binary protocol — 6 messages (see below); single-client TCP servers (`Telemetry`, `GoalServer`). |
| `mount` / `replay` | VL53L5CX zone-projection LUT; `.mdlg` log replay for offline iteration. |

## Public API

```rust,ignore
use microduck_maploc::{
    grid::{GridConfig, OccupancyGrid},
    submap_manager::{SubmapManager, SubmapManagerConfig},
    loop_closer::{detect_loops, LoopCloserConfig},
    optimizer::{optimize, OptimizerConfig},
    planner::{plan, PlannerConfig},
    follower::{follow_step, FollowerState},
    global_render::{render_global, GlobalRenderConfig},
};

let mut mgr = SubmapManager::new(SubmapManagerConfig::default());

// Per tick: advance the tracked pose from odometry, then
mgr.tick(now_s, tracked);                       // open/freeze submaps
if let Some(cur) = mgr.current_mut() {
    cur.integrate_scan(tracked, &angles, &ranges);
}
// On submap freeze: detect_loops(...) → pose-graph edges → optimize(...)
// → push corrected anchors back AND apply the same correction to `tracked`.

// Goal arrives: plan on the composite render.
let grid = render_global(mgr.all(), &GlobalRenderConfig::default()).unwrap();
if let Some(path) = plan(&grid, (x, y), goal, PlannerConfig::default()) {
    let mut follower = FollowerState::new(path[1..].to_vec());
    let cmd = follow_step(&mut follower, (x, y), yaw, 0.20, 1.20, 0.10);
    // cmd.vx (m/s) + cmd.wz (rad/s) → locomotion velocity command
}
```

See `microduck_runtime/src/maploc.rs` for the full production wiring (including MCL relocalize on boot).

## Wire protocol

Every message is `u32 LE length` ++ `u8 tag` ++ payload (length covers tag + payload, capped at 1 MB). All multi-byte fields are little-endian. The `wire` module is the canonical spec; a Python implementation in [microduck_maploc/sim/wire.py](https://github.com/apirrone/microduck_maploc) follows it for the sim and laptop viewer.

| Tag    | Direction      | Body                                                                |
|--------|----------------|---------------------------------------------------------------------|
| `0x01` | server → client | `Hello { version: u32 }` — sent on connect                          |
| `0x02` | server → client | `Pose { x, y, yaw, std, residual, lock, timestamp_ms }`             |
| `0x03` | server → client | Map blob (raw `OccupancyGrid` bytes — same format on disk and on wire) |
| `0x04` | server → client | `Path { waypoints: Vec<(f32, f32)> }`                               |
| `0x05` | server → client | `Scan { angles_body, ranges, origin }`                              |
| `0x80` | client → server | `Goal { x, y }` — laptop click                                      |

Map blob format (also on-disk): `MDLM` magic, `u32` version, `5 × f32` (x_range, y_range, cell), `2 × u32` (W, H), then `W*H × i16 LE` log-odds × 100. Cross-arch safe; header validated on load.

## Performance

Tuned for the Radxa Zero 3 (4× Cortex-A55). Ballpark per-call costs on an apartment-sized composite (~200×160 cells, 64 beams):

- Mapping update (`integrate_scan`): a few thousand i16 cell ops — sub-millisecond.
- Distance field recompute: O(W·H) Felzenszwalb, a few ms; cached until the grid mutates.
- MCL update (800 particles): beam offsets precomputed per scan, endpoints via angle-addition — no trig in the inner loop.
- Brute-force relocalize: coarse pass parallelized over yaw bins (rayon) with per-yaw offset tables; top-K refined.
- Global render: inverse-mapped compositing over each submap's footprint, ~13 k cells per submap.

Run `cargo run --release --example bench_field` for numbers on your hardware.

## Tests

```bash
cargo test --release
```

55 unit + integration tests: round-trips (save/load, session, wire), planner corner-safety, rotated-render hole-freedom, scan-matcher residual semantics, MCL cluster/lock geometry, and an end-to-end loop-closure drift-recovery scenario.

## Status

Used in production by the [microduck_runtime](https://github.com/apirrone/microduck_runtime) `--maploc` flag. The sensor-side hookup (VL53L5CX/L8CX I²C driver, FK projection, floor filtering) lives on the runtime side; this crate consumes pre-projected horizontal scans (angles + ranges in body frame).

The Python reference implementation in [microduck_maploc](https://github.com/apirrone/microduck_maploc) (`sim/`) is the development sandbox: MuJoCo apartment, sim duck, viewer with click-to-goto. It speaks the same wire protocol so the laptop viewer can connect to either the sim or the real duck.
