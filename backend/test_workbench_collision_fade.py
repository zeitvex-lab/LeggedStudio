"""D5：3D 查看器「碰撞时外观透化」—— 结构守护测试。

背景：任务清单 D5（2026-09-14 复核）只 grep 了 web/workbench.js（无 opacity）就判
「透化未做」，但 workbench 页的查看器实现住在 web/urdf-viewer.js（页面以 <script>
把它当库加载，开关只是经 window.setRobotViewerVisibility 转发），透化其实已在
2026-09-08 223bcd6c 随「TRON1 碰撞体可见性」落地。页面是手写 JS、无编译期检查，
这条测试把三段链路钉死，防止下一次重构把透化悄悄删掉或改坏：

  ① workbench.html 的 7 个显示开关（含 toggleCollision）在位；
  ② workbench.js 把 toggleCollision 接到 window.setRobotViewerVisibility({collision})；
  ③ urdf-viewer.js 的 setVisibility 只对外观层（roles.visual）做透化：collision 开
     → opacity 压到 0.28 / transparent=true；关 → 恢复缓存的 _baseOpacity（幂等，
     绝对赋值不连乘）；网格 / 坐标轴走各自独立分支，不受透化影响。
"""

import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"

# 查看器工具条 7 个显示开关（D5 的「7 开关」前提本身也需要守护）
VIEWER_TOGGLES = (
    "toggleVisual",
    "toggleCollision",
    "toggleInertial",
    "toggleCenterOfMass",
    "toggleGrid",
    "toggleAxes",
    "toggleJointAxes",
)


class WorkbenchToggleWiringTest(unittest.TestCase):
    """①② 开关在位 + 接线：页面壳（workbench.*）必须把碰撞开关送到查看器 API。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEB / "workbench.html").read_text(encoding="utf-8")
        cls.js = (WEB / "workbench.js").read_text(encoding="utf-8")

    def test_seven_viewer_toggles_present(self):
        for toggle in VIEWER_TOGGLES:
            with self.subTest(toggle=toggle):
                self.assertIn(f'id="{toggle}"', self.html,
                              f"{toggle} 缺失——3D 查看器开关被删会静默破坏 D5 前提")

    def test_collision_toggle_wired_to_viewer_api(self):
        """接线表里 toggleCollision 必须映射到 collision 键并调用查看器可见性 API。"""
        self.assertIn("'toggleCollision', 'collision'", self.js,
                      "开关接线表丢失 toggleCollision → collision 映射")
        self.assertIn("setRobotViewerVisibility?.({ [key]: pressed })", self.js,
                      "开关点击必须转发到 window.setRobotViewerVisibility")


class CollisionFadeTest(unittest.TestCase):
    """③ 透化本体：urdf-viewer.js 的 setVisibility 在碰撞开关上压暗外观层。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.js = (WEB / "urdf-viewer.js").read_text(encoding="utf-8")

    def test_visibility_api_exported(self):
        self.assertIn("window.setRobotViewerVisibility = setVisibility", self.js,
                      "查看器必须导出 setRobotViewerVisibility，否则页面开关全是空转")

    def test_fade_hooks_on_collision_toggle_and_targets_visual_role_only(self):
        """透化块必须挂在 collision 分支内，且只迭代外观层 roles.visual。"""
        collision_branch = self.js.find("typeof options.collision === 'boolean'")
        fade_block = self.js.find("state.roles.visual.forEach((object) => {")
        self.assertGreater(collision_branch, -1, "缺 collision 开关分支")
        self.assertGreater(fade_block, collision_branch,
                           "透化必须由 collision 开关驱动（挂错分支=切别的开关也在变透明）")

    def test_fade_is_absolute_and_idempotent(self):
        """幂等守护：基准透明度只在 userData._baseOpacity 缓存一次，每次切换都是
        绝对赋值（0.28 / base）。若有人改成按当前 opacity 连乘，切几次机身就消失。"""
        self.assertIn("object.userData._baseOpacity = object.material?.opacity ?? 1",
                      self.js, "缺基准透明度缓存（恢复路径会丢原值）")
        self.assertIn("object.material.opacity = shellVisible ? Math.min(base, 0.28) : base",
                      self.js, "透化/恢复必须是绝对赋值：开→0.28，关→base")

    def test_fade_flips_transparent_flag(self):
        self.assertIn("object.material.transparent = shellVisible || base < 0.999",
                      self.js, "opacity < 1 必须同步 transparent=true 才会走透明渲染")

    def test_grid_and_axes_keep_their_own_branches(self):
        """环境 / 工具不受透化影响：网格与坐标轴各自独立分支，只切 visible。"""
        self.assertIn("state.grid.visible = options.grid", self.js)
        self.assertIn("state.axes.visible = options.axes", self.js)


if __name__ == "__main__":
    unittest.main()
