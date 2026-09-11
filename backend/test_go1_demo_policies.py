"""go1 演示策略准入锁（用户裁决 v0.44.0：演示策略必须有包内移植好的对应训练代码）。

现状：unitree_go1 无训练树（B14 待补）⇒ 演示策略准入为空。

撤下记录（v0.43.0 导入 → v0.44.0 依裁决撤下）：
- go1-playground-joystick（mujoco_playground 官方导出，Playwright 实测站立
  z≈0.33 / vx 追踪 92% 达标）与 go1-himloco（LeggedSkillDeploy 官方
  himloco_best.pt 官方工具重导，对拍 7e-06）均因"包内无移植训练代码"撤下；
- 完整契约与取证链归档于 git tag v0.43.0（git show v0.43.0:.../config.json）；
  onnx 原件在 resources/unitree_go1/deploy；训练任务移植（B14）后原样恢复；
- 附带修复随本轮保留：model/robot.xml 补 <actuator> 段（nu=12 锁）、
  keyframe hip 符号修正、contract default_pose 左右符号修正、
  frame_major_v1 历史布局（ObservationBuffer.get_obs_vec 语义，app.js 通路）。
"""

import json
import unittest
from pathlib import Path

import mujoco

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GO1 = PROJECT_ROOT / "assets" / "robots" / "unitree_go1"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


class Go1DemoPolicyAdmissionTests(unittest.TestCase):
    def test_no_demo_policies_without_ported_training_code(self):
        """准入裁决锁：训练树就位前，policies 必须为空。"""
        config = _read(GO1 / "simulation" / "config.json")
        self.assertEqual(
            config.get("policies") or [],
            [],
            "go1 无包内移植训练代码（B14）——演示策略不得导入；"
            "恢复路径：git show v0.43.0:assets/robots/unitree_go1/simulation/config.json",
        )
        self.assertFalse((GO1 / "simulation" / "policies" / "go1_playground_joystick.onnx").exists())
        self.assertFalse((GO1 / "simulation" / "policies" / "go1_himloco.onnx").exists())

    def test_no_stale_top_level_policy_contract(self):
        """himloco_45x1 兜底已删：包级 policy_contract 不得与 per-policy 矛盾。"""
        self.assertIsNone(_read(GO1 / "simulation" / "config.json").get("policy_contract"))


class Go1ModelFixTests(unittest.TestCase):
    """随撤下保留的模型修复锁（训练任务移植后同样需要）。"""

    def test_model_has_actuator_section(self):
        """v0.43 修复锁：模型必须有原生 position 执行器（此前 ctrl 无人消费 → 瘫倒）。"""
        model = mujoco.MjModel.from_xml_path(str(GO1 / "model" / "robot.xml"))
        self.assertEqual(model.nu, 12)

    def test_default_pose_hip_signs_follow_left_right_convention(self):
        """修正锁：按消费序（actuated_joints 字母序）解读，右 hip=+0.1、左 hip=-0.1。"""
        for name in ("contract.json", "contract_v3.json"):
            data = _read(GO1 / name)
            joints = data["joints"]
            actuated = joints.get("actuated_joints") or joints.get("actuated")
            names = [
                item["name"] if isinstance(item, dict) else str(item) for item in actuated
            ]
            pose = dict(zip(names, joints["default_pose"]))
            for side, sign in (("R", 0.1), ("L", -0.1)):
                for leg in ("FR", "FL", "RR", "RL"):
                    if not leg.endswith(side):
                        continue
                    self.assertEqual(
                        pose[f"{leg}_hip_joint"], sign,
                        f"{name}: {leg}_hip default 符号违反右+左-惯例",
                    )


if __name__ == "__main__":
    unittest.main()
