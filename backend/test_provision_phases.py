"""A1：环境供应四段的**结构契约**（可在 CI 跑，不代替 Windows 实机验证）。

## 这组测试守的是什么

A1 的四段落点只能在 Windows 上真跑，而"只能人工验"的功能最容易悄悄退化：少一个镜像档位、
回退路径被删、离线档又开始联网。这里把四段的**结构契约**钉成机器判据，并守住两条底线：

1. **离线必须是真的离线**：`--no-index` 与 `--find-links` 必须在，且缺 wheelhouse 时**明确报错**
   （不静默联网 —— 否则"我离线跑通了"是假的）；
2. **门禁绿 ≠ 实机验证过**：报告里必须带 `windows_e2e_verified=False` 这个事实，
   免得有人把静态绿读成"Windows 上验证过了"。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "tools"))
import audit_provision_phases as gate  # noqa: E402


class ProvisionPhaseGateTest(unittest.TestCase):
    def setUp(self):
        self.report = gate.audit()

    def test_four_phases_are_structurally_present(self):
        self.assertTrue(self.report["ok"], self.report["problems"])
        phases = {item["phase"] for item in self.report["checks"]}
        self.assertEqual({"1-只读启动", "2-显式配置", "3-镜像切换", "4-离线wheelhouse"}, phases)

    def test_gate_states_that_windows_is_not_verified(self):
        """**门禁绿 ≠ 实机验证过**：这个事实必须出现在报告里（不能靠读文档的人自己想起来）。"""

        self.assertIn("windows_e2e_verified", self.report)
        self.assertFalse(self.report["windows_e2e_verified"], "静态门禁不该声称实机验证过")

    def test_offline_mode_is_a_hard_guarantee(self):
        script = (ROOT / "scripts" / "provision_windows_runtime.ps1").read_text(encoding="utf-8")
        self.assertIn("'--no-index'", script, "离线必须显式 --no-index（否则会联网）")
        self.assertIn("'--find-links'", script)
        self.assertIn("MirrorProfile=offline 需要", script, "离线档缺 wheelhouse 要报错，不能静默联网")
        self.assertIn("wheelhouse 目录不存在", script, "给了不存在的目录要报错")

    def test_mirror_profiles_and_fallback(self):
        script = (ROOT / "scripts" / "provision_windows_runtime.ps1").read_text(encoding="utf-8")
        for profile in ("'cn'", "'official'", "'custom'", "'offline'"):
            self.assertIn(profile, script)
        self.assertIn("MirrorProfile=custom 需要", script, "custom 档必须显式给源")
        self.assertIn("official-fallback", script, "国内镜像失败要回退官方源并留下痕迹")

    def test_launcher_does_not_auto_provision(self):
        """启动路径**不许**自动下载：provision 只能由显式 IPC 触发（第 1 段）。"""

        launcher = (ROOT / "electron" / "launcher" / "main.js").read_text(encoding="utf-8")
        self.assertIn("'environment:provision-windows'", launcher)
        self.assertIn("runtime-progress", launcher, "配置过程要有进度（否则用户面对黑屏）")
        # 别用"子串没出现"这种粗判据：`function provisionWindowsRuntime()` 这行本身也是子串命中。
        # 精确判据在门禁里（调用点集合必须恰好是 IPC 那一处 + 函数定义行），这里复用它。
        checks = [item for item in self.report["checks"] if item["check"].startswith("启动路径不自动下载")]
        self.assertTrue(checks, "门禁里缺「启动路径不自动下载」这一条")
        self.assertTrue(checks[0]["ok"], f"启动路径疑似自动下载：{checks[0]}")


if __name__ == "__main__":
    unittest.main()
