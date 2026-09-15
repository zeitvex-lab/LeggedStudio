"""B32 收口：v2 ``observation.dimension`` 必须是 v3 真值的**派生视图**（14 包 14/14 一致，无例外）。

## 这组测试守的是什么

v2 ``contract.json`` 的 ``observation.dimension`` 曾停留在 E4 基数校正前的旧值：
tron1 三包是旧「全帧和」口径（pf=135 / sf=330 / wf=165），其余各包是早期手写基数
（b2w=45 / g1=105 / go1=45 / go2=48）。v3 ``contract_v3.json`` 按实测裁定后，v2 作为
兼容视图必须跟着 v3 走。B32 已把 7 个漂移包逐一对齐（wuji_hand=69 更早上轮已修），
本文件把全仓不变量钉死：

1. **全仓不变量**：14 个内置包 v2 ``observation.dimension`` == v3 ``observation.dimension``，
   **无任何豁免**；失败信息列出 {包: (v2, v3)}；
2. **包清单钉死**：内置包数量钉在 14；增删包是有意动作，须连同本测试一起改；
3. **v3 真值表钉死**：逐包钉 v3 基数。特别注意 tron1 三包的 30/36/28 是
   **encoder 架构单帧宽度**（E4 裁决：encoder 输入 = 单帧 × 10 帧历史，策略输入 =
   单帧 + 3 维 latent + 3 维 command），与 v2 旧值 135/330/165 的「全帧和」是两种
   算法、两种语义——对齐就是以 v3 为准，**不要**试图用旧口径「调和」出新数字。

风格：纯 pytest 兼容的 unittest.TestCase（CI 的 ``unittest discover`` 与本地
``python -m pytest`` 双口径可跑）、仅标准库、直读文件。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"

# v3 真值表（B32 时的实测基数）。v3 变更是有意动作：先改 contract_v3.json 并在此
# 登记新真值，再让 v2 跟上——两处都动、测试才绿。
V3_DIMENSION_TRUTH = {
    "deeprobotics_lite3": 45,
    "deeprobotics_m20": 57,
    # tron1 三包：encoder 架构单帧宽度（E4 裁决），非全帧和。
    "limx_tron1_pf": 30,
    "limx_tron1_sf": 36,
    "limx_tron1_wf": 28,
    "microduck": 61,
    "unitree_b2": 45,
    "unitree_b2w": 57,
    "unitree_g1": 98,
    "unitree_go1": 48,
    "unitree_go2": 45,
    "unitree_go2w": 57,
    "wuji_hand": 69,
    "zex-w": 53,
}


def _builtin_robots() -> list[str]:
    """有 v2+v3 双契约的内置包清单（按目录名排序）。"""
    return sorted(
        d.name for d in ROBOTS.iterdir()
        if d.is_dir() and (d / "contract.json").exists() and (d / "contract_v3.json").exists()
    )


def _obs_dimension(robot: str, filename: str) -> int:
    """直读某包某版契约的 observation.dimension。"""
    path = ROBOTS / robot / filename
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value["observation"]["dimension"]


class RepoObsDimensionInvariantTest(unittest.TestCase):
    """全仓不变量：14 包 v2 dimension == v3 dimension，无任何例外。"""

    def test_14_builtin_packages_present(self):
        """内置包清单钉在 14（B1 口径）；增删包是有意动作，须连同本测试一起改。"""
        self.assertEqual(14, len(_builtin_robots()))

    def test_v2_dimension_is_derived_view_of_v3(self):
        """14 包全部：v2 observation.dimension == v3 observation.dimension，无例外。"""
        drift: dict[str, tuple[int, int]] = {}
        for robot in _builtin_robots():
            v2 = _obs_dimension(robot, "contract.json")
            v3 = _obs_dimension(robot, "contract_v3.json")
            if v2 != v3:
                drift[robot] = (v2, v3)
        self.assertEqual(
            {}, drift,
            "这些包的 v2 observation.dimension 漂离 v3 真值 {包: (v2, v3)}——"
            "v2 是 v3 的派生视图，应以 v3 为准对齐（tron1 三包 = encoder 单帧宽度口径）",
        )


class V3TruthPinTest(unittest.TestCase):
    """v3 真值表钉死：v3 基数变更是有意动作，须先改 contract_v3.json 再登记本表。"""

    def test_v3_dimension_matches_pinned_truth(self):
        """逐包钉 v3 基数；漂移说明 v3 被改，须连带更新真值表（双向防漂）。"""
        mismatch: dict[str, tuple[int, int]] = {}
        for robot in _builtin_robots():
            actual = _obs_dimension(robot, "contract_v3.json")
            expected = V3_DIMENSION_TRUTH[robot]
            if actual != expected:
                mismatch[robot] = (expected, actual)
        self.assertEqual(
            {}, mismatch,
            "v3 observation.dimension 偏离钉死真值 {包: (钉死值, 实际值)}——"
            "若为有意变更请更新 V3_DIMENSION_TRUTH 并让 v2 跟上",
        )

    def test_truth_table_covers_every_package(self):
        """真值表与包清单同延：多包少包都算清单漂移。"""
        self.assertEqual(sorted(V3_DIMENSION_TRUTH), _builtin_robots())


if __name__ == "__main__":
    unittest.main()
