"""Reactive obstacle avoidance controller for native navigation (Feature 1).

The native navigation mode follows a planned waypoint route.  On its own that
is an *open-loop* waypoint follower: the robot steers toward the next waypoint
regardless of what is actually in the world.  This module layers a *reactive*
perception-decision loop on top of that route:

  1. 感知 (perceive): given the robot's live world position and the map's
     obstacle rectangles, compute a signed proximity to each obstacle and the
     nearest-approach direction.
  2. 决策 (decide): combine an *attractive* velocity toward the current
     waypoint with a *repulsive* velocity away from any obstacle inside the
     safety radius (a potential-field controller), then clamp to a feasible
     surface velocity.
  3. 闭环 (close the loop): the modulated command is fed back into the policy
     every step, so the robot reacts to the world state instead of blindly
     executing a precomputed path.

The controller is deliberately pure-Python (no torch / mjlab), so it can be
unit-tested in the lightweight control-plane environment and reused verbatim
by the isolated native worker.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# (cx, cy, half_width, half_height) axis-aligned rectangle in world metres.
Obstacle = tuple[float, float, float, float]


@dataclass(frozen=True)
class AvoidanceConfig:
    """Tuning knobs for the reactive avoidance controller."""

    safety_radius: float = 0.9      # obstacles within this radius exert repulsion (m)
    repulsive_gain: float = 1.6     # repulsive velocity gain (scaled by proximity)
    waypoint_gain: float = 1.0      # attractive velocity gain toward the waypoint
    max_surface_vel: float = 1.0    # clamp the combined command magnitude to +/- this
    slow_radius: float = 1.2        # within this radius of an obstacle, also slow down

    def as_dict(self) -> dict:
        return {
            "safety_radius": self.safety_radius,
            "repulsive_gain": self.repulsive_gain,
            "waypoint_gain": self.waypoint_gain,
            "max_surface_vel": self.max_surface_vel,
            "slow_radius": self.slow_radius,
        }


def _point_rect_signed_distance(
    px: float, py: float, obstacle: Obstacle
) -> float:
    """Signed distance from point to an axis-aligned rectangle.

    Negative when the point is strictly inside the rectangle (penetration),
    zero on the surface, positive otherwise.  This gives a continuous proximity
    signal even when the robot is already touching / inside an obstacle.
    """
    cx, cy, half_w, half_h = obstacle
    left, right = cx - half_w, cx + half_w
    bottom, top = cy - half_h, cy + half_h
    # Strictly inside the rectangle -> negative distance to the nearest edge.
    if (left < px < right) and (bottom < py < top):
        return -min(px - left, right - px, py - bottom, top - py)
    dx = max(left - px, 0.0, px - right)
    dy = max(bottom - py, 0.0, py - top)
    return math.hypot(dx, dy)


def _nearest_point_on_rect(px: float, py: float, obstacle: Obstacle) -> tuple[float, float]:
    cx, cy, half_w, half_h = obstacle
    nx = min(max(px, cx - half_w), cx + half_w)
    ny = min(max(py, cy - half_h), cy + half_h)
    return nx, ny


def compute_avoidance_command(
    position: tuple[float, float],
    waypoint: tuple[float, float],
    obstacles: list[Obstacle],
    config: AvoidanceConfig | None = None,
) -> dict:
    """Compute a reactive (attractive + repulsive) surface velocity command.

    Returns the modulated (vx, vy) with magnitude clamped to
    ``max_surface_vel``, plus diagnostics (nearest obstacle distance, active
    avoidance flag, slowdown factor) so the navigation report can record how
    much the perception-decision loop actually engaged.
    """
    cfg = config or AvoidanceConfig()
    px, py = position
    wx, wy = waypoint

    # Attractive velocity toward the current waypoint.
    dx, dy = wx - px, wy - py
    norm = math.hypot(dx, dy)
    if norm > 1e-6:
        attract_x = dx / norm * cfg.waypoint_gain
        attract_y = dy / norm * cfg.waypoint_gain
    else:
        attract_x = attract_y = 0.0

    # Repulsive velocity away from any obstacle inside the safety radius.
    rep_x = rep_y = 0.0
    nearest = float("inf")
    active = False
    for obstacle in obstacles:
        dist = _point_rect_signed_distance(px, py, obstacle)
        if dist < nearest:
            nearest = dist
        if dist < cfg.safety_radius:
            active = True
            # Push away from the nearest point on the obstacle surface.
            nx, ny = _nearest_point_on_rect(px, py, obstacle)
            ox, oy = px - nx, py - ny
            onorm = math.hypot(ox, oy)
            if onorm > 1e-6:
                ux, uy = ox / onorm, oy / onorm
            else:
                ux, uy = 0.0, 0.0
            strength = (cfg.safety_radius - dist) / cfg.safety_radius
            rep_x += ux * cfg.repulsive_gain * strength
            rep_y += uy * cfg.repulsive_gain * strength

    command_x = attract_x + rep_x
    command_y = attract_y + rep_y
    mag = math.hypot(command_x, command_y)
    if mag > cfg.max_surface_vel:
        scale = cfg.max_surface_vel / mag
        command_x, command_y = command_x * scale, command_y * scale

    # Slow down (shrink magnitude) when close to an obstacle.
    if nearest < 0.0:
        # Penetrating: hard stop toward the obstacle.
        command_x, command_y = 0.0, 0.0
    elif nearest < cfg.slow_radius:
        slowdown = max(0.0, nearest / cfg.slow_radius)
        command_x *= slowdown
        command_y *= slowdown

    return {
        "command": [command_x, command_y],
        "nearest_obstacle_distance": round(nearest, 4) if math.isfinite(nearest) else None,
        "avoidance_active": active,
        "slowdown": round(1.0 if nearest >= cfg.slow_radius else max(0.0, nearest / cfg.slow_radius), 4),
        "attractive": [round(attract_x, 4), round(attract_y, 4)],
        "repulsive": [round(rep_x, 4), round(rep_y, 4)],
    }
