"""E1：页面三段化（**物理（只读）/ 任务（Recipe）/ 运行参数**）—— 判据"三层互不混装"。

这是**结构测试**：判据落在页面上就是三个分区块 + 物理层没有可编辑输入 + 运行参数不在任务层。
页面是手写 HTML、没有编译期检查，所以这条测试是"下一次改页面又把运行参数混回任务层"的
唯一机械保障 —— 光靠 review 是挡不住的（这正是 E1 当初的成因）。
"""

import re
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "web" / "training_create.html"


class PageLayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_three_layers_exist_in_order(self):
        # 用**元素 id** 定位（不能搜 `data-layer="..."`：样式表里的选择器会先命中，
        # 于是测的就不是"区块顺序"了 —— 这条坑第一次就把我自己绊了一下）
        positions = [self.html.find(f'id="layer-{name}"')
                     for name in ("physics", "task", "runtime")]
        self.assertNotIn(-1, positions, "三段分区标记必须齐全（物理/任务/运行参数）")
        self.assertEqual(positions, sorted(positions),
                         "分区顺序必须是 物理 → 任务 → 运行参数")

    def test_runtime_fields_live_inside_the_runtime_layer(self):
        """**混装回归**：numEnvs/seed/device 曾混在 01 环境与仿真里（任务层）。"""
        runtime = self.html.find('id="layer-runtime"')
        self.assertGreater(runtime, -1)
        for field in ('id="numEnvs"', 'id="seed"', 'id="deviceMirror"'):
            with self.subTest(field=field):
                self.assertGreater(self.html.find(field), runtime,
                                   f"{field} 必须落在运行参数段内，不能混进任务层")

    def test_physics_layer_is_read_only(self):
        """物理在页面上只能"看"：有只读面板 + 不存在物理可编辑输入。"""
        self.assertIn('id="physicsReadonly"', self.html, "缺物理只读面板")
        self.assertIn("renderPhysicsReadonly", self.html, "只读面板必须有渲染函数")
        for field in ("stiffness", "damping", "armature", "physics_hz", "control_hz"):
            with self.subTest(field=field):
                self.assertIsNone(
                    re.search(rf'<input[^>]*id="{field}"', self.html),
                    f"{field} 不该是页面上的可编辑输入（物理真值属于契约/MJCF）",
                )

    def test_task_layer_keeps_the_env_and_objective_chapters(self):
        task = self.html.find('id="layer-task"')
        self.assertGreater(task, -1)
        for chapter in ('id="ch-sim"', 'id="ch-iface"', 'id="ch-goal"', 'id="ch-robust"'):
            with self.subTest(chapter=chapter):
                self.assertGreater(self.html.find(chapter), task, f"{chapter} 应属于任务层")


if __name__ == "__main__":
    unittest.main()
