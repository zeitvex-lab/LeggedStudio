//! microduck_maploc — v2 (submap-based pose-graph SLAM).
//!
//! See `docs/PLAN.md` and `docs/DESIGN.md` for the intended architecture.
//!
//! Module map (all shipped):
//!
//!   grid           — 2D log-odds occupancy + cached distance field
//!   submap         — local grid + SE(2) anchor pose + retained raw scans
//!   submap_manager — open / close submaps based on time + travel
//!   scan_matcher   — Hector-style GN scan-to-map matching
//!   pose_graph     — SE(2) nodes + relative-pose edges
//!   optimizer      — dense Gauss-Newton over the full graph
//!   loop_closer    — coarse-to-fine submap-to-submap loop matching
//!   global_render  — composite all submaps into one grid (inverse-mapped)
//!   mcl            — particle-filter relocalize against a saved map
//!   relocalize     — one-shot brute-force pose search (diagnostic / seeding)
//!   planner        — A* + inflation + supercover LOS simplification
//!   follower       — turn-then-go waypoint follower (velocity output)
//!   session        — save/load the whole SLAM state (fsynced, atomic)
//!   wire / stream  — telemetry + goal TCP protocol
//!   replay         — read back .mdlg session files for offline iteration
//!
//! MCL is scoped to boot-time relocalize-from-uniform on a saved map;
//! live tracking is odometry + (loop-closure-corrected) submap anchors.

pub mod follower;
pub mod global_render;
pub mod grid;
pub mod loop_closer;
pub mod mcl;
pub mod mount;
pub mod optimizer;
pub mod planner;
pub mod pose_graph;
pub mod relocalize;
pub mod replay;
pub mod scan_matcher;
pub mod session;
pub mod stream;
pub mod submap;
pub mod submap_manager;
pub mod wire;

pub use follower::{follow_step, FollowCommand, FollowerState};
pub use grid::{GridConfig, OccupancyGrid};
pub use planner::{plan, PlannerConfig};
pub use scan_matcher::{match_scan, ScanMatchConfig, ScanMatchResult};
pub use wire::{Goal, LockState, Message, Path as WirePath, Pose, Scan};
