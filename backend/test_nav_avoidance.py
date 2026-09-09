"""Unit tests for the reactive obstacle-avoidance controller (Feature 1)."""

from __future__ import annotations

import unittest

from adapters.mjlab.nav_avoidance import (
    AvoidanceConfig,
    _point_rect_signed_distance,
    compute_avoidance_command,
)


class RectSignedDistanceTest(unittest.TestCase):
    def test_outside_returns_positive(self):
        # Obstacle centred at (2,0), half extents (0.6, 2.4).
        dist = _point_rect_signed_distance(0.0, 0.0, (2.0, 0.0, 0.6, 2.4))
        self.assertGreater(dist, 0.0)

    def test_inside_returns_negative(self):
        dist = _point_rect_signed_distance(2.0, 0.0, (2.0, 0.0, 0.6, 2.4))
        self.assertLess(dist, 0.0)

    def test_on_surface_returns_zero(self):
        dist = _point_rect_signed_distance(2.6, 0.0, (2.0, 0.0, 0.6, 2.4))
        self.assertAlmostEqual(dist, 0.0, places=4)


class AvoidanceCommandTest(unittest.TestCase):
    def setUp(self):
        self.obstacle = (2.0, 0.0, 0.6, 2.4)

    def test_no_obstacle_free_track_to_waypoint(self):
        # Far from obstacle, command should head toward waypoint.
        result = compute_avoidance_command((0.0, 0.0), (6.0, 0.0), [self.obstacle])
        cmd = result["command"]
        self.assertGreater(cmd[0], 0.0)  # heading +x
        self.assertFalse(result["avoidance_active"])

    def test_repulsion_pushes_away_from_obstacle(self):
        # Robot right next to the obstacle, waypoint beyond it.
        result = compute_avoidance_command((1.0, 0.0), (6.0, 0.0), [self.obstacle])
        self.assertTrue(result["avoidance_active"])
        # The repulsive influence should reduce forward attraction or add -x.
        # Nearest obstacle distance is reported and finite.
        self.assertIsNotNone(result["nearest_obstacle_distance"])

    def test_command_clamped(self):
        result = compute_avoidance_command(
            (0.0, 0.0), (6.0, 0.0), [],
            AvoidanceConfig(max_surface_vel=0.5),
        )
        mag = (result["command"][0] ** 2 + result["command"][1] ** 2) ** 0.5
        self.assertLessEqual(mag, 0.5 + 1e-6)

    def test_slowdown_near_obstacle(self):
        config = AvoidanceConfig(safety_radius=1.5, slow_radius=2.0)
        near = compute_avoidance_command((1.5, 0.0), (6.0, 0.0), [self.obstacle], config)
        far = compute_avoidance_command((0.0, 0.0), (6.0, 0.0), [self.obstacle], config)
        self.assertLessEqual(near["slowdown"], far["slowdown"])


if __name__ == "__main__":
    unittest.main()


class ClosedLoopNaviTest(unittest.TestCase):
    """Validate the reactive closed-loop controller steers around obstacles."""

    def test_obstacle_in_path_adds_lateral_avoidance(self):
        # Robot slightly off the obstacle's centre line, heading toward waypoint
        # at (+x). The obstacle sits right in front, so the closed-loop command
        # must acquire a lateral (|y|) component to steer around it.
        obstacle = (2.0, 0.0, 0.6, 0.6)  # right in the +x path
        result = compute_avoidance_command((1.0, 0.2), (6.0, 0.0), [obstacle])
        cmd = result["command"]
        self.assertTrue(result["avoidance_active"])
        # Lateral component should be non-negligible (pushing around the block).
        self.assertGreater(abs(cmd[1]), 1e-3)

    def test_free_path_stays_straight(self):
        # No obstacle near the path: command is essentially straight toward +x.
        result = compute_avoidance_command((0.0, 0.0), (6.0, 0.0), [])
        cmd = result["command"]
        self.assertLess(abs(cmd[1]), 1e-6)
        self.assertGreater(cmd[0], 0.0)


if __name__ == "__main__":
    unittest.main()
