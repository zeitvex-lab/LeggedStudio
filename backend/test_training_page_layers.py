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


class ExpertModePanelTest(unittest.TestCase):
    """E6 逃生门（点路径覆盖）：**面板必须走后端校验**，不能前端自判。

    前端自判一次，就多一份与后端分叉的白名单 —— 那时"页面能改、后端说未知"这类
    最难查的不一致就会回来。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_panel_exists_with_its_own_layer_block(self):
        self.assertIn('id="layer-expert"', self.html)
        self.assertIn('id="expertOverrides"', self.html)
        self.assertIn('id="expertValidate"', self.html)
        self.assertIn("validateExpertOverrides", self.html)

    def test_validation_goes_through_the_backend(self):
        self.assertIn("/api/training/validate-overrides", self.html,
                      "必须调后端校验端点（目录在后端）")
        self.assertNotIn("STATIC_READONLY", self.html,
                         "前端不得自己复制一份只读白名单（会与后端分叉）")

    def test_ui_states_the_all_or_nothing_rule_and_physics_readonly(self):
        self.assertIn("整批拒绝", self.html, "必须写明失败时整批拒绝")
        self.assertIn("只读", self.html, "必须写明物理/契约类只读")
        self.assertIn("不会生效", self.html)


if __name__ == "__main__":
    unittest.main()
