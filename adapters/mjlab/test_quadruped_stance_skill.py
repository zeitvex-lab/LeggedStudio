"""族级「站姿类」技能（stance）的回归锁：域随机化观测的名字与增益来源。

站姿类的 critic 帧里有一段"特权域随机化标签"（源实现的 34 维），它要读三样东西：
足端几何的摩檫、根 body 的附加质量/质心、**各执行器的 kp/kd 倍率**。源实现把前两样
写死成 go2 的名字（`FL_foot_collision` / `base_link`），第三样只认 `IdealPdActuator`。
本锁钉住两件事：

1. **名字从绑定派生、且在 go2 上仍是源实现的那两个字符串**（等价性）；
2. **换一台资产（b2）也能建出 cfg**，且名字跟着契约腿序走。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GO2_PACKAGE = ROOT / "assets" / "robots" / "unitree_go2"
GO2_SOURCE = GO2_PACKAGE / "training" / "source"
B2_SOURCE = ROOT / "assets" / "robots" / "unitree_b2" / "training" / "source"
for _path in (str(ROOT), str(GO2_PACKAGE), str(GO2_SOURCE), str(B2_SOURCE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:  # 训练栈不可用时整文件跳过（与 adapters/mjlab 其它测试同口径）
    import mjlab  # noqa: F401
except ImportError as _exc:  # pragma: no cover
    raise unittest.SkipTest(f"训练栈不可用: {_exc}")


def _critic_params(cfg, *, variant: str) -> dict:
    return dict(cfg.observations["critic"].terms["frame"].params)


class StanceDomainRandomizationNamesTests(unittest.TestCase):
    """critic 帧的 DR 段：名字来自绑定，取值与源实现逐字相同（go2）。"""

    @classmethod
    def setUpClass(cls):
        from b2_hand_stand.config import make_b2_handstand_env_cfg
        from local_tasks.robots.unitree.go2.tasks.go2_skills.hand_stand.config import (
            make_handstand_env_cfg,
        )

        cls.go2 = make_handstand_env_cfg()
        cls.b2 = make_b2_handstand_env_cfg()

    def test_go2_keeps_the_source_literals(self):
        params = _critic_params(self.go2, variant="handstand")
        self.assertEqual("FL_foot_collision", params["foot_geom"])
        self.assertEqual("base_link", params["root_body"])

    def test_b2_derives_both_names_from_its_binding(self):
        params = _critic_params(self.b2, variant="handstand")
        # b2 契约腿序以 FR 开头 ⇒ 足端几何取 FR（源实现的口径是"读一个足端几何"，
        # 摩擦 DR 是 shared_random ⇒ 读哪一个等价）
        self.assertEqual("FR_foot_collision", params["foot_geom"])
        self.assertEqual("base_link", params["root_body"])

    def test_critic_frame_is_the_same_shape_on_both_robots(self):
        """critic 帧的**声明宽**与函数类同族一致（换机型不该动观测骨架）。"""
        go2 = self.go2.observations["critic"].terms["frame"]
        b2 = self.b2.observations["critic"].terms["frame"]
        self.assertIs(go2.func, b2.func)
        self.assertEqual(go2.func.frame_dim, b2.func.frame_dim)

    def test_dr_info_reports_the_gain_source_per_actuator_kind(self):
        """b2 的执行器写在 MJCF ⇒ `actuator_source == 'asset'`；go2 走契约重建。"""
        from b2_velocity.binding import B2_VELOCITY
        from local_tasks.robots.unitree.go2.tasks.go2_skills.binding import GO2

        self.assertEqual("asset", B2_VELOCITY.actuator_source)
        self.assertEqual("contract", GO2.actuator_source)


if __name__ == "__main__":
    unittest.main()
