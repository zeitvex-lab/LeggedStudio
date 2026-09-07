"""DreamWaQ M20 terminations.

The source terminates on time-out and on a height check: the mean base
height above the terrain probe grid dropping below 0.20 m (a low, flipped,
or collapsed base).  There is no orientation-angle termination in the
source, so none is added here.
"""

import torch


def base_below_terrain(env, sensor_name: str, min_height: float = 0.2) -> torch.Tensor:
  scan = env.scene[sensor_name].data
  mean_terrain_z = scan.hit_pos_w[..., 2].mean(1)
  root_z = env.scene["robot"].data.root_link_pos_w[:, 2]
  return (root_z - mean_terrain_z) < min_height
