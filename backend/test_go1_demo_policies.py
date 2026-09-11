"""go1 演示策略导入锁（待办 #2，v0.43.0）。

取证来源（resources/unitree_go1）：
- go1_playground_joystick.onnx：mujoco_playground experimental/sim2sim 官方导出，
  play_go1_joystick.py（同目录同源）逐行取证——obs 48 = [linvel,gyro,gravity,
  pos_rel,vel,last_act,cmd] 全裸值，action_scale=0.5，onnx 实测 [1,48]→[1,12]。
  Playwright 实测：站立 z≈0.33 稳定、vx 指令起步响应 ✓。
- contract default_pose 修正：原数组按官方模型序书写但按 actuated_joints
  字母序消费，四条 hip 符号全反（右 +0.1 / 左 -0.1 三方证据一致）。
- 模型 robot.xml 补 <actuator> 段（此前 ctrl 无人消费 -> 无力瘫倒）；
  keyframe home 后两腿 hip 符号同步修正。

himloco 恢复记录（v0.43.0，取证闭环后复活）：
- 弃用 mjswan 裸 onnx（无出生证明），改用 LeggedSkillDeploy 官方
  himloco_best.pt（resources 内置）经官方 convert_policy.py 导出（对拍 7e-06）；
- 布局 ground truth = 官方 src/scripts/observation_buffer.py
  ObservationBuffer.get_obs_vec：对 yaml 倒序表 [5,4,3,2,1,0] 做 reversed
  遍历后 torch.cat —— 整帧拼接且最新帧在前（frame_major_v1），此前四组合
  全失败即因浏览器用 term-major + 最老在前；
- 段序按部署 yaml `observations` 列表序（commands 在前）；
  关节序 = legged_gym URDF 字母序（joint_mapping [3,4,5,...] 在该序下自洽）；
  PD = rl_kp 40 / rl_kd 1（per-policy 写入模型执行器）。
  浏览器终验（Playwright 站立/追踪）待跑。
"""

import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GO1 = PROJECT_ROOT / "assets" / "robots" / "unitree_go1"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


class Go1DemoPolicyTests(unittest.TestCase):
    def test_declared_policies_with_onnx_present(self):
        config = _read(GO1 / "simulation" / "config.json")
        policies = {p["id"]: p for p in config.get("policies") or []}
        self.assertEqual(
            set(policies),
            {"go1-playground-joystick", "go1-himloco"},
            "go1 演示策略声明漂移：himloco 以官方 pt 重导恢复（取证闭环），不得擅自增删",
        )
        for policy in policies.values():
            self.assertTrue((GO1 / policy["path"]).exists(), f"{policy['id']} onnx 缺失")

    def test_himloco_contract_matches_official_deploy_chain(self):
        """himloco 契约锁：全部字段对照官方 config.yaml + observation_buffer.py。"""
        policy = next(
            p for p in _read(GO1 / "simulation" / "config.json")["policies"]
            if p["id"] == "go1-himloco"
        )
        contract = policy["contract"]
        self.assertEqual((policy["obs_dim"], policy["action_dim"], policy["history_len"]), (45, 12, 6))
        self.assertEqual(contract["observation_kind"], "himloco_45_hist6")
        self.assertEqual(contract["history_layout"], "frame_major_v1")
        self.assertEqual(contract["action_scale"], 0.25)
        self.assertEqual(
            contract["scales"],
            {"ang_vel": 0.25, "dof_pos": 1.0, "dof_vel": 0.05, "command": [2.0, 2.0, 0.25]},
        )
        # 官方 yaml 的 default_dof_pos / joint_controller_names 逐值对拍
        self.assertEqual(
            contract["default_joint_angles"],
            {
                "FR_hip_joint": 0.1, "FR_thigh_joint": 0.8, "FR_calf_joint": -1.5,
                "FL_hip_joint": -0.1, "FL_thigh_joint": 0.8, "FL_calf_joint": -1.5,
                "RR_hip_joint": 0.1, "RR_thigh_joint": 1.0, "RR_calf_joint": -1.5,
                "RL_hip_joint": -0.1, "RL_thigh_joint": 1.0, "RL_calf_joint": -1.5,
            },
        )
        self.assertEqual(
            set(contract["action_joint_order"]),
            set(contract["default_joint_angles"]),
        )
        self.assertEqual(
            set(contract["control"]["stiffness"].values()), {40.0}, "rl_kp=40"
        )
        self.assertEqual(
            set(contract["control"]["damping"].values()), {1.0}, "rl_kd=1"
        )

    def test_no_stale_top_level_policy_contract(self):
        """himloco_45x1 兜底已删：包级 policy_contract 不得再与 per-policy 矛盾。"""
        config = _read(GO1 / "simulation" / "config.json")
        self.assertIsNone(config.get("policy_contract"))

    def test_playground_contract_matches_official_export(self):
        policy = next(
            p for p in _read(GO1 / "simulation" / "config.json")["policies"]
            if p["id"] == "go1-playground-joystick"
        )
        contract = policy["contract"]
        self.assertEqual((policy["obs_dim"], policy["action_dim"]), (48, 12))
        self.assertEqual(contract["observation_kind"], "go1_playground_48")
        self.assertEqual(contract["action_scale"], 0.5)
        self.assertEqual(
            contract["scales"],
            {"ang_vel": 1.0, "dof_pos": 1.0, "dof_vel": 1.0, "command": [1.0, 1.0, 1.0]},
            "playground 观测为全裸值，缩放必须全 1",
        )

    def test_action_joint_order_is_permutation_of_model_joints(self):
        contract = _read(GO1 / "contract.json")
        model_joints = set(contract["joints"]["actuated_joints"])
        config = _read(GO1 / "simulation" / "config.json")
        for policy in config["policies"]:
            order = policy["contract"]["action_joint_order"]
            self.assertEqual(len(order), 12)
            self.assertEqual(
                set(order), model_joints,
                f"{policy['id']}: action_joint_order 不是模型关节集合的重排",
            )
            defaults = policy["contract"]["default_joint_angles"]
            self.assertEqual(set(defaults), model_joints)
            if policy["id"] == "go1-playground-joystick":
                # playground 训练序 [FR,FL,RR,RL]：与模型字母序不同，重排必须非恒等；
                # himloco 训练序即 URDF 字母序（恒等合法，yaml joint_mapping 自洽）。
                self.assertNotEqual(order, contract["joints"]["actuated_joints"])

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
