"""URDF 导入的自动转换（`backend/package_import.py`）。

现状与动机：通用训练路径只吃 MJCF（`build_generic_task` 明确拒绝 URDF），此前导入 URDF 只能
"收下但训不了"，要人手动跑 `tools/urdf_to_mjcf.py`。现在**导入那一刻**就用 MuJoCo 自己的
URDF 解析转一份 MJCF 作为训练模型（`urdf.path` 指向它，与 8 台内置机型"urdf.path 指 model/robot.xml"
的既有约定一致），源 URDF 原样留在包里、物理量一个没改。

守三件事：
1. 能转的：preview 与写盘**同一份判据**（`_effective_model`）——两条路径结论一致；
2. 转不了的（缺 mesh 等）：**导入照常成功**、按 URDF 原样收下，并在 warnings 里写明原因
   （不假装转换成功，也不因转换失败拒绝导入）；
3. 转换产物必须是**能编译的 MJCF**（不然训练路径照样炸，等于把问题推后）。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.package_import import _convert_urdf_to_mjcf, onboard_package  # noqa: E402

#: 无 mesh 的两关节 URDF——可独立编译，不依赖任何外部资产
#: 无 mesh 的两关节 URDF——可独立编译，不依赖任何外部资产
#: （MuJoCo 的 URDF 解析要求 `<inertial>` 里带 `<inertia>`，缺了会在转换时报 missing element）
_TWO_JOINT_URDF = """<robot name="mini_quad">
  <link name="base"><inertial><mass value="5.0"/>
    <inertia ixx="0.02" ixy="0" ixz="0" iyy="0.02" iyz="0" izz="0.02"/></inertial></link>
  <link name="leg"><inertial><mass value="0.5"/>
    <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="0.001"/></inertial></link>
  <link name="foot"><inertial><mass value="0.2"/>
    <inertia ixx="0.0002" ixy="0" ixz="0" iyy="0.0002" iyz="0" izz="0.0002"/></inertial></link>
  <joint name="hip" type="revolute">
    <parent link="base"/><child link="leg"/><axis xyz="0 1 0"/><limit lower="-1" upper="1"/>
  </joint>
  <joint name="knee" type="revolute">
    <parent link="leg"/><child link="foot"/><axis xyz="0 1 0"/><limit lower="-2" upper="0"/>
  </joint>
</robot>
"""

#: 引用了不存在的 mesh——**校验通过**（XML 层没毛病）但转换必须失败（mesh 加载不了）
_MISSING_MESH_URDF = """<robot name="missing_mesh">
  <link name="base"><inertial><mass value="5.0"/>
    <inertia ixx="0.02" ixy="0" ixz="0" iyy="0.02" iyz="0" izz="0.02"/></inertial></link>
  <link name="leg">
    <inertial><mass value="0.5"/>
      <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="0.001"/></inertial>
    <visual><geometry><mesh filename="meshes/missing.stl"/></geometry></visual>
  </link>
  <joint name="hip" type="revolute">
    <parent link="base"/><child link="leg"/><axis xyz="0 1 0"/><limit lower="-1" upper="1"/>
  </joint>
</robot>
"""


class ConvertTest(unittest.TestCase):
    def test_mesh_free_urdf_converts_and_compiles(self):
        import mujoco

        with tempfile.TemporaryDirectory() as tmp:
            urdf = Path(tmp) / "mini.urdf"
            urdf.write_text(_TWO_JOINT_URDF, encoding="utf-8")
            converted, note = _convert_urdf_to_mjcf(urdf)
            self.assertIsNotNone(converted, note)
            self.assertEqual("mini.xml", converted.name)
            self.assertIn("自动转换", note)
            model = mujoco.MjModel.from_xml_path(str(converted))
            self.assertEqual(2, model.njnt)

    def test_unconvertible_urdf_reports_reason_instead_of_raising(self):
        """真转不动的（关节指向不存在的 link）⇒ 返回原因，不抛异常。"""
        with tempfile.TemporaryDirectory() as tmp:
            urdf = Path(tmp) / "bad.urdf"
            urdf.write_text(_BROKEN_LINK_URDF, encoding="utf-8")
            converted, note = _convert_urdf_to_mjcf(urdf)
            self.assertIsNone(converted)
            self.assertIn("转换失败", note)



_BROKEN_LINK_URDF = """<robot name="broken_link">
  <link name="base"><inertial><mass value="1.0"/>
    <inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/></inertial></link>
  <joint name="j" type="revolute">
    <parent link="base"/><child link="nope"/><axis xyz="0 1 0"/><limit lower="-1" upper="1"/>
  </joint>
</robot>
"""


class OnboardPreviewTest(unittest.TestCase):
    def _preview(self, model_text: str, stem: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="urdf-import-", dir=ROOT / "workspace") as tmp:
            base = Path(tmp)
            source = base / "robot"
            source.mkdir()
            (source / f"{stem}.urdf").write_text(model_text, encoding="utf-8")
            return onboard_package(source, write=False, packages_root=base / "packages")

    def test_urdf_preview_switches_training_model_to_mjcf(self):
        report = self._preview(_TWO_JOINT_URDF, "mini")
        self.assertTrue(report.get("valid"), report.get("errors"))
        self.assertIn("自动转换", report.get("conversion") or "")
        draft = report.get("contract_draft") or {}
        self.assertTrue(str(draft["urdf"]["path"]).endswith(".xml"), draft["urdf"]["path"])
        self.assertIn("urdf-converted", draft.get("tags") or [])

    def test_missing_mesh_urdf_is_rejected_before_conversion(self):
        """缺 mesh 的 URDF 在校验期就 fail-closed（转换根本不会发生）——拒因要写具体文件名。"""
        report = self._preview(_MISSING_MESH_URDF, "missing_mesh")
        self.assertFalse(report.get("valid"))
        self.assertTrue(any("mesh file not found" in str(item) for item in report.get("errors") or []),
                        report.get("errors"))
        self.assertIsNone(report.get("conversion"))

    def test_conversion_failure_falls_back_to_the_urdf(self):
        """转换起不来 ⇒ 导入照常按 URDF 收下，warning 写明原因（不假装转换成功）。"""
        from unittest import mock

        with tempfile.TemporaryDirectory(prefix="urdf-import-", dir=ROOT / "workspace") as tmp:
            base = Path(tmp)
            source = base / "robot"
            source.mkdir()
            (source / "mini.urdf").write_text(_TWO_JOINT_URDF, encoding="utf-8")
            with mock.patch("backend.package_import._convert_urdf_to_mjcf",
                            lambda model: (None, "URDF 自动转换失败（演示：磁盘满了）")):
                report = onboard_package(source, write=False, packages_root=base / "packages")
        draft = report.get("contract_draft") or {}
        self.assertTrue(str(draft["urdf"]["path"]).endswith(".urdf"), draft["urdf"]["path"])
        self.assertNotIn("urdf-converted", draft.get("tags") or [])
        self.assertTrue(
            any("转换" in str(item) for item in report.get("warnings") or []),
            f"转换失败必须在 warnings 里写明原因：{report.get('warnings')}",
        )


if __name__ == "__main__":
    unittest.main()
