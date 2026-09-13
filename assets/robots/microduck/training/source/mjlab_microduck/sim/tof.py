"""A simulated VL53L5CX, so the duck can see a wall.

8x8 zones over a 45-degree square field of view, out to 4 m, at 15 Hz — the real sensor's shape,
because `tofd` publishes frames of exactly that and `maploc` reprojects them assuming it.

Modelled on `~/MISC/microduck_maploc`'s `sim/tof_sensor.py`, which had these numbers from the
datasheet and from the sensor on a desk: noise that grows with distance (millimetres up close,
centimetres out near the limit), and a status per zone rather than a distance alone.

**The status byte matters as much as the distance.** A real sensor distinguishes "nothing out there"
from "could not measure", and `maploc` treats them differently — a zone with no target is empty
space to clear on the map, and a zone that failed is no information at all. A simulator reporting
only distances would let a bug through that hardware finds.
"""

from __future__ import annotations

import mujoco
import numpy as np

# The sensor, as `tof/src/lib.rs` publishes it.
ROWS = 8
COLS = 8
ZONES = ROWS * COLS
STATUS_VALID = 5
STATUS_NO_TARGET = 255

# VL53L5CX: 45 degrees per axis (63 on the diagonal), 4 m of range.
FOV_DEG = 45.0
MAX_RANGE = 4.0


