//! Quick microbench for the localization hot paths: distance-field
//! recompute, one MCL update over a full particle cloud, and a one-shot
//! brute-force relocalize.
//!
//! Run: `cargo run --release --example bench_field`

use std::time::Instant;

use microduck_maploc::grid::{GridConfig, OccupancyGrid};
use microduck_maploc::mcl::{Localizer, MclConfig};
use microduck_maploc::relocalize::{relocalize_against_grid, RelocalizeConfig};

fn main() {
    let mut g = OccupancyGrid::new(GridConfig::default());
    // Apartment-shaped obstacles + free interior. Mirrors the python
    // bench's mapping density (~3000 occupied cells over an 8×6 m grid).
    for t in 0..120 {
        let p = -3.5 + (t as f32) * 0.06;
        for _ in 0..10 {
            g.integrate_ray(0.0, 0.0,  3.5,  p, true);
            g.integrate_ray(0.0, 0.0, -3.5,  p, true);
            g.integrate_ray(0.0, 0.0,   p,  2.5, true);
            g.integrate_ray(0.0, 0.0,   p, -2.5, true);
        }
    }
    let n_occ: usize = g.log_raw().iter().filter(|&&v| v > 150).count();
    let n_free: usize = (0..g.height())
        .flat_map(|i| (0..g.width()).map(move |j| (i, j)))
        .filter(|&(i, j)| g.is_known_free(i, j))
        .count();
    println!("grid: {}×{} cells, {n_occ} occupied, {n_free} known-free",
             g.width(), g.height());

    let t0 = Instant::now();
    let _ = g.distance_field(200);
    println!("distance_field (cold): {:.1} ms",
             t0.elapsed().as_secs_f64() * 1000.0);
    let t0 = Instant::now();
    let _ = g.distance_field(200);
    println!("distance_field (cached): {:.3} ms",
             t0.elapsed().as_secs_f64() * 1000.0);

    // Synthesize a wide scan from the origin.
    let mut angles = Vec::new();
    let mut ranges = Vec::new();
    for k in 0..64 {
        let a = -std::f32::consts::PI + (k as f32) * (std::f32::consts::PI / 32.0);
        let r = g.cast_ray(0.0, 0.0, a, 4.0);
        angles.push(a);
        ranges.push(r);
    }
    println!("scan: {} beams", angles.len());

    // MCL: seed uniform, time predict + update cycles.
    let mut loc = Localizer::new(
        MclConfig { n_particles: 800, ..MclConfig::default() }, 0);
    loc.seed_uniform(&g);
    loc.update(&mut g, &angles, &ranges); // warm the field cache
    let n_iters = 20;
    let t0 = Instant::now();
    for _ in 0..n_iters {
        loc.predict(0.01, 0.0, 0.005);
        loc.update(&mut g, &angles, &ranges);
    }
    let dt_ms = t0.elapsed().as_secs_f64() * 1000.0 / n_iters as f64;
    println!("mcl predict+update (800 particles): {:.2} ms / frame (n={n_iters})", dt_ms);

    // Brute-force relocalize (coarse + top-K refine).
    let cfg = RelocalizeConfig::default();
    let t0 = Instant::now();
    let res = relocalize_against_grid(&mut g, &angles, &ranges, &cfg);
    let dt_ms = t0.elapsed().as_secs_f64() * 1000.0;
    match res {
        Some(r) => println!(
            "relocalize: {:.1} ms — pose=({:.2},{:.2},{:.0}°) resid={:.3} accepted={}",
            dt_ms, r.pose.0, r.pose.1, r.pose.2.to_degrees(),
            r.mean_residual_m, r.accepted),
        None => println!("relocalize: {:.1} ms — no candidate", dt_ms),
    }
}
