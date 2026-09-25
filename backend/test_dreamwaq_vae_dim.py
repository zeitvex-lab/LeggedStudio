"""DreamWaQ VAE 输入维必须由**历史组宽度**派生，不许写死。

2026-09-25 冒烟抓到真故障：``m20-dreamwaq`` 训练第一次 update 崩
``mat1 and mat2 shapes cannot be multiplied (128x285 and 225x128)`` ——
VEACenet 的 ``in_dim`` 写成字面量 225（从上游默认值抄来），而历史组实宽是
5 帧 × 57 维 = 285。上游真值（``00_resources/Dreamwaq/legged_gym/envs/M20/
m20_config.py``）就是派生的::

    num_observations = 57
    num_obs_hist = 5
    num_history_obs = num_obs_hist * num_observations   # = 285

所以本测试钉的是"**派生关系**"，不是某个数字：帧宽/历史长改一处，
VAE 与观测必须同时跟着变，否则判红。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "robots" / "deeprobotics_m20" / "training" / "source"
for entry in (str(ROOT), str(SOURCE)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from m20_dreamwaq.constants import (  # noqa: E402
    HISTORY_LENGTH,
    HISTORY_OBS_DIM,
    OBS_FRAME_DIM,
)
from m20_dreamwaq.mdp import observations as obs  # noqa: E402
from m20_dreamwaq.mdp.rl import _VAE  # noqa: E402


class DreamWaQDimTest(unittest.TestCase):
    def test_history_width_is_derived_not_literal(self) -> None:
        self.assertEqual(HISTORY_OBS_DIM, HISTORY_LENGTH * OBS_FRAME_DIM)

    def test_vae_encoder_consumes_the_full_history_group(self) -> None:
        vae = _VAE()
        self.assertEqual(
            vae.encoder[0].in_features,
            HISTORY_OBS_DIM,
            "VEACenet 的输入维必须等于历史组展平后的宽度（帧宽 × 历史长）",
        )

    def test_vae_decoder_reconstructs_one_actor_frame(self) -> None:
        vae = _VAE()
        self.assertEqual(vae.decoder[-1].out_features, OBS_FRAME_DIM)

    def test_history_term_uses_the_same_frame_dim(self) -> None:
        self.assertEqual(obs._FRAME_DIM, OBS_FRAME_DIM)


if __name__ == "__main__":
    unittest.main()
