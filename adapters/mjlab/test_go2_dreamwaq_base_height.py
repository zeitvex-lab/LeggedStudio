"""go2 dreamwaq 的 `base_height` 必须取扫描网格**中央 3×3**（移植核对 F2）。

上游（IsaacGym CTS / LLoco dreamwaq）的注释写得很直白：
"averaging the entire 1.6x1.0 m scan incorrectly rewards a crouched robot on slopes" ——
本仓移植曾写成整张 187 点平均（注释还写着 3×3），2026-09-24 移植核对按上游改正。

这条锁用**行为**判据而不是读源码：构造一张"外圈高、中央平"的假扫描，
中央 3×3 平均与整张平均给出不同的地形高度 ⇒ 函数返回值必然不同。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GO2_SOURCE = ROOT / "assets" / "robots" / "unitree_go2" / "training" / "source"


class _Data:
    def __init__(self, **fields) -> None:
        self.__dict__.update(fields)


class _Scene(dict):
    pass


class _Env:
    def __init__(self, hit_z, root_z: float) -> None:
        import torch

        points = torch.tensor(hit_z, dtype=torch.float32).reshape(1, -1, 1)
        points = torch.cat([torch.zeros_like(points), torch.zeros_like(points), points], dim=-1)
        self.num_envs = 1
        self.scene = _Scene(
            terrain_scan=_Data(data=_Data(hit_pos_w=points)),
            robot=_Data(data=_Data(root_link_pos_w=torch.tensor([[0.0, 0.0, root_z]]))),
        )


class BaseHeightWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import torch  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"训练栈不可用: {exc}")
        for path in (str(GO2_SOURCE), str(ROOT)):
            if path not in sys.path:
                sys.path.insert(0, path)
        from local_tasks.robots.unitree.go2.tasks.go2_skills.dreamwaq.mdp import rewards

        cls.base_height = staticmethod(rewards.base_height)

    def _scan(self) -> list[float]:
        # 17×11 网格：外圈 2.0 m、中央 3×3 为 0.0 —— 两种平均口径给出的地形高度必然不同
        grid = [[2.0] * 11 for _ in range(17)]
        for x in range(7, 10):
            for y in range(4, 7):
                grid[x][y] = 0.0
        return [value for row in grid for value in row]

    def test_uses_central_window_not_whole_grid(self):
        env = _Env(self._scan(), root_z=0.4)
        value = float(self.base_height(env, 0.4))
        # 中央窗口 ⇒ 地形高度 0 ⇒ (0.4 - 0 - 0.4)² = 0；整张平均则会给出正的惩罚
        self.assertAlmostEqual(0.0, value, places=6)

    def test_uniform_scan_gives_same_result_either_way(self):
        env = _Env([0.1] * 187, root_z=0.5)
        value = float(self.base_height(env, 0.4))
        self.assertAlmostEqual((0.5 - 0.1 - 0.4) ** 2, value, places=6)


if __name__ == "__main__":
    unittest.main()
