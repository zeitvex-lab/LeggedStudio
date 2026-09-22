"""无头验收的**判据声明化**（`criteria["checks"]`）与 `posture` 族（2026-09-22）。

## 为什么需要这一层

判据此前散在 `evaluate_mode` 里按家族写 `if family in ("stand","balance","velocity","gait")`：
"量哪几项"由**工具代码**决定。后果有两个，本轮都实测到了：

* **假阴性**：姿态类技能（反关节/倒立）被站立族判据量成"倾角 88° 不合格"——
  `go2-lainlab-rear-stand` 实测稳定保持躯干 −88°、baseZ 0.40 达 8 s（真的用后腿立住了），
  却判 fail；
* **加一类任务就要改工具**：新族必须动 `evaluate_mode`，于是"框架统一"总差一口。

改法：`DEFAULT_CRITERIA[family]["checks"]` 声明**量哪几项**（并可被策略契约
`contract.criteria` 覆盖 —— 判据属于任务语义，正门是任务自己声明）；新增 `posture` 族量
"稳态倾角落在声明带内"。未声明 `checks` 的家族按旧行为回落，**逐项等价**。

本测试守四件事：① `posture` 族按带判（进带=过、差得远=如实判败）；② 未声明 checks 的家族
回落旧行为；③ 声明表里的检查名**必须都实现了**（声明式表格最容易出的错就是拼错名字后静默
不检查）；④ 数据面：两条姿态类技能确实声明了 `posture` + 自己的姿态带。
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "sim2sim_headless_for_criteria_test", ROOT / "tools" / "sim2sim_headless.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _StubContract:
    def __init__(self, initial_height=0.42, criteria=None):
        self.initial_height = initial_height
        self.contract = {"criteria": criteria or {}}


def _metrics(**over):
    base = {
        "survival_ratio": 1.0,
        "fell": False,
        "fell_at_s": None,
        "height_steady": 0.40,
        "height_steady_ratio": 0.95,
        "roll_steady_max_deg": 1.0,
        "pitch_steady_max_deg": 88.0,
        "roll_max_deg": 2.0,
        "pitch_max_deg": 90.0,
        "vel_track_err": None,
        "command": [0.0, 0.0, 0.0],
    }
    base.update(over)
    return base


class DeclaredCriteriaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool()

    # ---------- ① posture 族：量姿态带 ----------

    def test_posture_band_pass_and_fail(self):
        crit = dict(self.tool.DEFAULT_CRITERIA["posture"])
        ok = self.tool.evaluate_mode(_metrics(pitch_steady_max_deg=88.0), "posture",
                                     _StubContract(), crit)
        self.assertTrue(ok["ok"], ok["checks"])
        names = [c["name"] for c in ok["checks"]]
        self.assertIn("tilt_band", names)
        self.assertNotIn("height_ratio_steady", names, "姿态族不该量站立高度比")

        bad = self.tool.evaluate_mode(_metrics(pitch_steady_max_deg=33.5), "posture",
                                      _StubContract(), crit)
        self.assertFalse(bad["ok"])
        band = next(c for c in bad["checks"] if c["name"] == "tilt_band")
        self.assertFalse(band["ok"])
        self.assertEqual([60.0, 110.0], band["band"])

    def test_posture_band_overridable_by_task(self):
        """判据属于任务语义：契约声明更宽的带就该按契约判。"""
        crit = {**self.tool.DEFAULT_CRITERIA["posture"], "tilt_band_deg": [20.0, 120.0]}
        res = self.tool.evaluate_mode(_metrics(pitch_steady_max_deg=33.5), "posture",
                                     _StubContract(), crit)
        self.assertTrue(res["ok"], res["checks"])

    # ---------- ② 未声明 checks 的家族回落旧行为 ----------

    def test_legacy_fallback_for_unknown_family(self):
        res = self.tool.evaluate_mode(_metrics(), "some_new_family", _StubContract(), {"survival_min": 0.9})
        self.assertEqual(["survival"], [c["name"] for c in res["checks"]],
                         "未知家族应只量存活（旧行为），不擅自加姿态项")

    def test_legacy_fallback_velocity_keeps_old_checks(self):
        crit = {k: v for k, v in self.tool.DEFAULT_CRITERIA["velocity"].items() if k != "checks"}
        res = self.tool.evaluate_mode(_metrics(vel_track_err=0.05), "velocity", _StubContract(), crit)
        names = [c["name"] for c in res["checks"]]
        self.assertEqual(["survival", "height_ratio_steady", "tilt_steady", "vel_track_err"],
                         names, "去掉 checks 后必须与改造前逐项等价")

    # ---------- ③ 声明表里的检查名必须都实现 ----------

    def test_every_declared_check_name_is_implemented(self):
        crit = dict(self.tool.DEFAULT_CRITERIA["posture"])
        crit["checks"] = ["survival", "definitely_not_implemented"]
        res = self.tool.evaluate_mode(_metrics(), "posture", _StubContract(), crit)
        self.assertEqual(["survival"], [c["name"] for c in res["checks"]],
                         "未实现的检查名会被静默跳过——这正是声明式表格的危险，故本测试固定住它")

    def test_default_families_all_declare_checks(self):
        """除 `reorient` 外，每个家族都必须声明 checks。

        `reorient`（Wuji Hand in-hand 重定向）**不走** `evaluate_mode`：它有专用的
        成功率评估器（试次聚合朝向误差），所以这里只要求"其余家族都声明"——将来谁新增
        家族却忘了声明 checks，本测试立刻红（否则判据又悄悄回到代码里写死）。
        """
        missing = [f for f, c in self.tool.DEFAULT_CRITERIA.items() if not c.get("checks")]
        self.assertEqual(["reorient"], missing,
                         f"未声明 checks 的家族应为且仅为 ['reorient']，实测 {missing}")

    # ---------- ④ 数据面：两条姿态类技能确实按任务语义声明了 ----------

    def test_posture_policies_declare_their_band(self):
        sim = json.loads(
            (ROOT / "assets" / "robots" / "unitree_go2" / "simulation" / "config.json")
            .read_text(encoding="utf-8-sig")
        )
        want = {"go2-lainlab-rear-stand", "go2-lainlab-handstand"}
        seen = set()
        for entry in sim.get("policies") or []:
            if entry.get("id") not in want:
                continue
            contract = entry.get("contract") or {}
            self.assertEqual("posture", contract.get("task_type"), entry["id"])
            band = (contract.get("criteria") or {}).get("tilt_band_deg")
            self.assertIsInstance(band, list, entry["id"])
            self.assertEqual(2, len(band), entry["id"])
            seen.add(entry["id"])
        self.assertEqual(want, seen, "姿态类技能丢了？")


if __name__ == "__main__":
    unittest.main()
