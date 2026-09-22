"""打包观测 → **当前帧**的定位（2026-09-22）：`packed_current_frame` / `history_terms_for`。

## 为什么要单独盯这一处

同状态对拍工具 `tools/obs_crosscheck.py` 要把验收器给出的**整坨打包观测**
（`obs_dim × history_len`）切成**单帧**才能与浏览器 builder 比（浏览器只产单帧、
叠帧在 `app.js`）。它原先一律取 `packed[:obs_dim]`——**对 frame-major 成立、对
term-major（本仓缺省布局）不成立**：后者当前帧**分散在每一段的末槽**，切出来是
"第 0 段的历史 + 第 1 段的历史"，于是 5 条 `go2_rl_sdk_45` 族策略
（`go2-moe-cts` / kaiwu 四条）被**误报**"浏览器↔验收器不一致"——而实测两侧
**逐维一致 5.960e-08**。

**教训（比结论值钱）**：**尺子自己也会错，而且错法与被测物同形**——都是"对不上"。
这类缺陷不会抛异常、只会让人去改本来正确的实现，所以对拍工具自身也必须有回归锁。

**钉住的口径**：段表只有**一份**（`history_terms_for`，`pack_history` 与
`packed_current_frame` 共用）；定位当前帧一律走 `packed_current_frame`，
任何调用方（含对拍工具）不得自己再写一份切法。
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "policy_acceptance_for_history_frame", ROOT / "adapters" / "mjlab" / "policy_acceptance.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract(**over):
    """最小契约替身：只带 `packed_current_frame` / `pack_history` 需要的字段。"""
    base = dict(
        obs_dim=45,
        history_len=5,
        history_layout="",
        command_dims=3,
        action_joint_order=[f"j{i}" for i in range(12)],
        observation_kind="go2_rl_sdk_45",
        history_terms=None,
        history_interleaved=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


class PackedCurrentFrameTest(unittest.TestCase):
    """按布局定位当前帧：三种布局各一条 + 反例注入（证明这条测试有牙）。"""

    def setUp(self):
        self.engine = _load_engine()

    def _frames(self, obs_dim: int, count: int):
        """可辨识的帧序列（oldest→newest）：第 k 帧 = base + 100·k。"""
        base = np.arange(obs_dim, dtype=np.float64) + 1.0
        return [base + 100.0 * k for k in range(count)]

    def _assert_newest(self, layout: str, obs_dim=45, hist=5, **over):
        contract = _contract(history_layout=layout, obs_dim=obs_dim, history_len=hist, **over)
        frames = self._frames(obs_dim, hist)
        packed = np.asarray(
            self.engine.pack_history(SimpleNamespace(contract=contract), frames)
        ).reshape(-1)
        self.assertEqual(obs_dim * hist, packed.shape[0], f"打包长度 {layout}")
        current = self.engine.packed_current_frame(contract, packed)
        np.testing.assert_allclose(current, frames[-1], atol=0, rtol=0,
                                   err_msg=f"layout={layout}：取到的不是最新帧")
        return packed, frames

    def test_term_major_current_frame_is_newest(self):
        """缺省（term-major）：当前帧分散在每段末槽 ⇒ 必须按段表取。"""
        self._assert_newest("")

    def test_frame_major_v1_current_frame_is_newest(self):
        """`frame_major_v1`（最新帧在前）⇒ 当前帧是首段。"""
        self._assert_newest("frame_major_v1")

    def test_frame_major_oldest_first_current_frame_is_newest(self):
        """`frame_major_oldest_first`（最老在前）⇒ 当前帧是末段。"""
        self._assert_newest("frame_major_oldest_first")

    def test_naive_head_slice_is_wrong_for_term_major(self):
        """**反例注入**：证明"一律取首段"这条历史错法确实取错（测试不是白跑的）。

        若哪天有人把 `packed_current_frame` 改回 `packed[:obs_dim]`，这条会先红。
        """
        packed, frames = self._assert_newest("")
        naive = packed[: int(frames[-1].shape[0])]
        self.assertFalse(
            np.allclose(naive, frames[-1]),
            "term-major 下 '取首段' 本应取错——若它取对了，说明段表已退化成 frame-major",
        )

    def test_explicit_history_terms(self):
        """`wuji_term_major` 走契约显式段表（非缺省段表）。"""
        self._assert_newest(
            "wuji_term_major", obs_dim=9, hist=3, command_dims=3,
            action_joint_order=["j0", "j1"], history_terms=[[0, 3], [3, 3], [6, 3]],
        )

    def test_single_history_returns_whole_vector(self):
        contract = _contract(history_len=1)
        packed = np.arange(45, dtype=np.float64)
        np.testing.assert_allclose(self.engine.packed_current_frame(contract, packed), packed)

    def test_history_terms_agree_with_pack_history(self):
        """段表**只有一份**：`history_terms_for` 必须被 `pack_history` 实际使用。

        改段表而只改一处（另一处仍按旧段表切帧）正是本轮缺陷的形状，故直接断言
        "按段表拼出来的 == pack_history 拼出来的"。
        """
        contract = _contract(history_layout="term_major_suffix_extra_v1", obs_dim=48)
        frames = self._frames(48, 5)
        via_terms = np.concatenate([
            f[o:o + l] for o, l in self.engine.history_terms_for(contract) for f in frames
        ])
        via_pack = np.asarray(
            self.engine.pack_history(SimpleNamespace(contract=contract), frames)
        ).reshape(-1)
        np.testing.assert_allclose(via_terms, via_pack)


class PackedCurrentFrameFailClosedTest(unittest.TestCase):
    """定位不了就**抛**，不许给出一个"看着像当前帧"的错向量。"""

    def setUp(self):
        self.engine = _load_engine()

    def test_length_mismatch_raises(self):
        contract = _contract(obs_dim=45, history_len=5)
        with self.assertRaises(ValueError):
            self.engine.packed_current_frame(contract, np.zeros(44 * 5))

    def test_interleaved_layout_raises(self):
        """元素主序（`history_interleaved`）本仓 Python 侧不支持 ⇒ 不许按段瞎切。"""
        contract = _contract(history_interleaved=True)
        with self.assertRaises(ValueError):
            self.engine.packed_current_frame(contract, np.zeros(45 * 5))

    def test_terms_not_covering_obs_dim_raises(self):
        contract = _contract(obs_dim=40, history_len=2)  # 段表覆盖 45 ≠ 40
        with self.assertRaises(ValueError):
            self.engine.packed_current_frame(contract, np.zeros(40 * 2))

    def test_wuji_terms_missing_raises(self):
        contract = _contract(history_layout="wuji_term_major", history_terms=None)
        with self.assertRaises(ValueError):
            self.engine.packed_current_frame(contract, np.zeros(45 * 5))


class RealGo2MoeCtsHistoryTest(unittest.TestCase):
    """真实契约回归：`go2-moe-cts`（45×10、term-major、无显式 layout）曾被误报。"""

    def setUp(self):
        self.engine = _load_engine()
        self.pkg = ROOT / "assets" / "robots" / "unitree_go2"
        cfg = json.loads((self.pkg / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
        self.entry = next(e for e in cfg["policies"] if e["id"] == "go2-moe-cts")

    def test_packed_current_frame_matches_newest(self):
        contract = self.engine.PackageContract(self.pkg, self.entry)
        contract.motion_loader = None
        self.assertGreater(int(contract.history_len), 1, "本用例只针对有历史的策略")
        hist = int(contract.history_len)
        dim = int(contract.obs_dim)
        frames = [np.arange(dim, dtype=np.float64) + 1.0 + 100.0 * k for k in range(hist)]
        packed = np.asarray(
            self.engine.pack_history(SimpleNamespace(contract=contract), frames)
        ).reshape(-1)
        np.testing.assert_allclose(
            self.engine.packed_current_frame(contract, packed), frames[-1], atol=0, rtol=0
        )
        # 同一处历史误判的形状：取首段 ≠ 最新帧（钉住"这条用例真的覆盖了那个坑"）
        self.assertFalse(np.allclose(packed[:dim], frames[-1]))


if __name__ == "__main__":
    unittest.main()
