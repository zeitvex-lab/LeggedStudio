"""training_invariants 正确性不变量检查测试。"""

from __future__ import annotations

import unittest

from contracts.training_invariants import (
    invariant_errors,
    run_invariants,
)


class InvariantsTest(unittest.TestCase):
    def _config(self) -> dict:
        return {
            "num_envs": 4096,
            "episode_length_s": 20.0,
            "reward_scales": {"track": 1.0, "torques": -0.0005},
        }

    def _contract(self) -> dict:
        return {
            "observation": {
                "dimension": 48,
                "components": [
                    {"name": "actor", "width": 45},
                    {"name": "cmd", "width": 3},
                ],
            },
            "action": {"joint_order": ["a", "b"], "action_scale": 0.25},
        }

    def test_all_pass(self) -> None:
        results = run_invariants(self._config(), self._contract())
        self.assertEqual(invariant_errors(results), [])

    def test_obs_width_mismatch(self) -> None:
        contract = self._contract()
        contract["observation"]["dimension"] = 99
        results = run_invariants(self._config(), contract)
        errors = invariant_errors(results)
        self.assertTrue(any("obs_group_width" in e for e in errors) or any("观测组宽度" in e for e in errors))

    def test_action_scale_non_positive(self) -> None:
        contract = self._contract()
        contract["action"]["action_scale"] = 0
        results = run_invariants(self._config(), contract)
        self.assertTrue(any("action_scale" in e for e in invariant_errors(results)))

    def test_timeout_missing_flags(self) -> None:
        config = self._config()
        # 去掉 episode_length_s 等 key，触发 timeout 缺省告警
        config = {k: v for k, v in config.items() if k != "episode_length_s"}
        results = run_invariants(config, self._contract())
        self.assertTrue(any("timeout" in e for e in invariant_errors(results)))

    def test_num_envs_negative(self) -> None:
        config = self._config()
        config["num_envs"] = -4
        results = run_invariants(config, self._contract())
        self.assertTrue(any("num_envs" in e for e in invariant_errors(results)))

    def test_reward_nan(self) -> None:
        import math
        config = self._config()
        config["reward_scales"]["track"] = float("nan")
        results = run_invariants(config, self._contract())
        self.assertTrue(any("奖励缩放" in e for e in invariant_errors(results)))

    def test_empty_components_skips_width(self) -> None:
        contract = self._contract()
        contract["observation"]["components"] = []
        results = run_invariants(self._config(), contract)
        self.assertEqual(invariant_errors(results), [])


if __name__ == "__main__":
    unittest.main()
