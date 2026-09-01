import tempfile
import unittest
from pathlib import Path

import numpy as np

from adapters.mjlab_new.algorithms.off_policy import OffPolicyConfig, SACAlgorithm


class SacCheckpointTests(unittest.TestCase):
    def test_checkpoint_round_trip_preserves_deterministic_action(self):
        config = OffPolicyConfig(batch_size=2, replay_size=16)
        source = SACAlgorithm(4, 2, config, device="cpu")
        observations = np.asarray([[0.2, -0.1, 0.3, 0.4]], dtype=np.float32)
        expected, _ = source.act(observations, deterministic=True)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sac.pt"
            source.save(str(path))
            restored = SACAlgorithm(4, 2, config, device="cpu")
            restored.load(str(path))
            actual, _ = restored.act(observations, deterministic=True)

        np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
