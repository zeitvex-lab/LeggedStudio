"""按策略增益声明的**定位与对账**：它是「上游档位断言 + 溯源」，不是"能调节的开关"。

## 为什么要有这组测试（2026-09-14 的两次追问）

用户问了两句，都击中要害：

1. *"11 条声明了的物理是什么"* —— 答案：那些策略实际跑的是 **MJCF 执行器的 kp/kv**
   （非力矩接口下我们只写位置/速度目标），声明**不参与物理**。
2. *"声明和实机不好多一致吗，那你声明干什么"* —— 对：**不一致的声明就是假信息**；
   而"让它生效"这条路已被本仓明确关闭（运行时改写执行器**已退役**，见
   `contracts/physics_binding.py` 的 `LEGACY_CONFIG_PHYSICS_KEYS` 注释与
   `policy_acceptance.load_package_model`：真值只在契约、MJCF 由它固化，
   **漂移由校验器报、不静默修**）。

于是声明的正当定位只剩一个：**它是"这条策略取自上游哪个档位"的断言，必须与机器人级真值
一致**；不一致就该被判「假声明」。力矩接口下它本来就是控制器增益真值（实测修好了
`go2-moe-cts` / `g1-velocity` 两条零力矩），定位不变、只是同一字段多了一层用途。
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.audit_policy_gains import _declared_gain, audit

ROOT = Path(__file__).resolve().parents[1]
LITE3 = ROOT / "assets" / "robots" / "deeprobotics_lite3"
#: 契约真值里 hipx stiffness = 30（官方导出脚本同值，见任务清单 ★ 行的三向对照）
TRUE_STIFFNESS = 30.0


class DeclaredGainTest(unittest.TestCase):
    def test_absent_joint_is_none_not_zero(self):
        """"没声明"与"声明为 0"必须分得开 —— 混了就会造出假漂移。"""
        self.assertIsNone(_declared_gain({}, "FL_HipX_joint"))
        self.assertEqual(0.0, _declared_gain({"FL_HipX_joint": 0.0}, "FL_HipX_joint"))

    def test_exact_name_wins_over_substring(self):
        table = {"fl_hipx_joint": 30.0, "hipx": 99.0}
        self.assertEqual(30.0, _declared_gain(table, "FL_HipX_joint"))

    def test_case_insensitive_substring_fallback(self):
        """同 `PackageContract.gain_for`：精确名优先、再做子串匹配（大小写不敏感）。"""
        self.assertEqual(20.0, _declared_gain({"wheel": 20.0}, "FR_wheel_joint"))


class FakeDeclarationDriftTest(unittest.TestCase):
    """**假声明**（声明值与真值不符）必须被检出。"""

    @staticmethod
    def _package(root: Path, declared: float) -> None:
        robot = root / "deeprobotics_lite3"
        (robot / "simulation").mkdir(parents=True)
        shutil.copy(LITE3 / "contract_v3.json", robot / "contract_v3.json")
        contract = json.loads((LITE3 / "contract_v3.json").read_text(encoding="utf-8-sig"))
        order = list((contract.get("action") or {}).get("joint_order") or [])
        (robot / "simulation" / "config.json").write_text(
            json.dumps({
                "actuator_interface": "position_target",
                "policies": [{
                    "id": "p",
                    "contract": {
                        "action_joint_order": order,
                        "control": {
                            "stiffness": {joint: declared for joint in order},
                            "damping": {joint: 1.0 for joint in order},
                        },
                    },
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_declaration_matching_truth_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root, declared=TRUE_STIFFNESS)
            self.assertEqual([], audit(robots_dir=root)["drifted"])

    def test_declaration_off_from_truth_is_flagged(self):
        """lite3-benchmark 曾经的 40 就是这种：两个来源都不是它 → 假声明。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root, declared=40.0)
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["drifted"]))
            problems = report["drifted"][0]["declaration_drift"]
            self.assertTrue(problems)
            self.assertTrue(any("≠ 真值" in item for item in problems))

    def test_real_repo_has_no_fake_declaration(self):
        """**真实仓不变量**：11 条按策略声明都与机器人级真值一致（对账结果必须为空）。"""
        self.assertEqual([], audit()["drifted"])


if __name__ == "__main__":
    unittest.main()
