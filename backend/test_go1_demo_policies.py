"""go1 演示策略准入锁（用户裁决链：v0.43.x 官方取证闭环准入 → v0.44.0 收紧 → B8 规则 S 固化）。

现状（2026-09-12 同步）：unitree_go1 演示策略 = {go1-playground-joystick}。

演进记录：
- v0.43.0 导入 joystick / himloco / moe 三条；
- v0.44.0 依「演示策略必须有包内移植好的对应训练代码」裁决撤下全部（当时包内无训练树）；
- v0.44 后 joystick 经「官方 yaml / 官方消费代码 / 官方导出取证闭环」裁决恢复
  （mujoco_playground 官方 onnx + play_go1_joystick.py，实测 z≈0.334 / vx 追踪 92%）；
  moe（官方 moe_best.pt 导出对拍 6e-06）与 himloco（mjswan main.py 官方注释自证
  runtime 不支持其交错 history、demo 从未跑通）因 B8 规则 S（须有上游训练源码佐证）
  保持撤下——moe 上游只有推理产物（moe_best.pt + config.yaml），无训练源码；
  恢复路径 = 在 tools/audit_porting_admission.py::POLICY_ADMISSION 给出可核对的
  上游训练源码路径后同步 config.json 与本锁；
- B8 准入审计（tools/audit_porting_admission.py）现裁定 go1 策略准入 1 条，与本锁一致；
- 35fc4d58 起包内有 go1_velocity 训练树 + 2 个 profile（B14 大部分完成），
  B14 训练任务冒烟全绿后可再收紧为「训练代码在包内且可跑」的标准；
- 附带修复随撤下保留：model/robot.xml 补 <actuator> 段（nu=12 锁）、
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
    def test_admitted_policies_match_locked_set(self):
        """准入集合锁（B8 规则 S 固化：策略须有上游训练源码佐证，见 POLICY_ADMISSION）。"""
        config = _read(GO1 / "simulation" / "config.json")
        policies = {p["id"]: p for p in config.get("policies") or []}
        self.assertEqual(
            set(policies),
            {"go1-playground-joystick"},
            "go1 演示策略集合漂移；moe（上游仅推理产物，无训练源码）与 himloco（runtime "
            "不支持其交错 history、demo 从未跑通）已按 B8 规则 S 撤下，不得未经取证恢复",
        )
        from backend import policy_artifacts

        for policy in policies.values():
            # B10：声明只留 `id`，源路径经 policies/index.json 解析（不再读 policy["path"]）
            blob = policy_artifacts.policy_blob_path(policy, robot_dir=GO1)
            self.assertIsNotNone(blob, f"{policy['id']} 无法经出库索引解析到 onnx")
            self.assertTrue(Path(blob).exists(), f"{policy['id']} onnx 缺失")
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
        for name in ("contract_legacy_v2.json", "contract.json"):
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
