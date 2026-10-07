# -*- coding: utf-8 -*-
"""Phase 4 验证器事件化门禁的回归锁（`registry/verify/index.json` + `tools/audit_plugin_verify.py`）。

守三件事（判据与 `--check` **同一份纯函数**，不另写一套）：

1. 目录本身完整：schema / 形状 / `env` 闭集 / 无重复命令；
2. **覆盖率 100%**：`tools/` 下每个 `^(audit|validate|check)_*.py` 都在目录里有家
   （"没有游离的审计工具"不靠豁免清单掩盖）；
3. **清单不再手维护**：`.cnb.yml` 挂 `tools/audit_plugin_verify.py --run`，且不再出现手列的
   `python tools/audit|validate|check_*`。

外加反例注入：坏目录 / 坏 `.cnb.yml` 文本必须逐项被抓出来。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import audit_plugin_verify as apv  # noqa: E402


class CatalogGateTest(unittest.TestCase):
    def test_catalog_shape_is_valid(self):
        self.assertEqual([], apv.catalog_problems(apv.load_catalog()))

    def test_every_declared_tool_exists(self):
        self.assertEqual([], apv.existing_problems(apv.load_catalog()))

    def test_coverage_is_total(self):
        catalog = apv.load_catalog()
        self.assertEqual(set(), apv.universe_tools() - apv.declared_tools(catalog),
                         "有游离的守门工具（未登记进 registry/verify/index.json）")

    def test_runner_is_not_part_of_the_universe(self):
        self.assertNotIn(apv.RUNNER_NAME, apv.universe_tools(),
                         "audit_plugin_verify 自己是运行器，不该算门禁")

    def test_planned_and_skipped_partition_the_gates(self):
        catalog = apv.load_catalog()
        gates = [str(entry["command"]) for entry in catalog["gates"]]
        planned = apv.planned_commands(catalog)
        skipped = [command for command, _ in apv.skipped_commands(catalog)]
        self.assertEqual(set(gates), set(planned) | set(skipped))
        self.assertEqual([], sorted(set(planned) & set(skipped)), "同一条命令不能既跑又跳过")
        self.assertEqual(len(gates), len(planned) + len(skipped))

    def test_env_gated_entries_declare_a_reason(self):
        for command, env in apv.skipped_commands(apv.load_catalog()):
            with self.subTest(command=command):
                self.assertIn(env, apv.FROZEN_ENVS)


class CnbRunnerTest(unittest.TestCase):
    def test_cnb_yml_uses_derived_runner_and_has_no_hand_list(self):
        text = apv.CNB_PATH.read_text(encoding="utf-8")
        self.assertEqual([], apv.cnb_problems(text))

    def test_cnb_yml_still_lists_unrelated_checks(self):
        # 反面对照：本测试保证 `cnb_problems` 抓的是"审计/校验命令"，不是所有 python 调用
        text = apv.CNB_PATH.read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s backend", text)


class ChildEnvTest(unittest.TestCase):
    def test_pythonpath_is_repo_root(self):
        env = apv._child_env()
        paths = env["PYTHONPATH"].split(__import__("os").pathsep)
        self.assertEqual(str(ROOT), paths[0])


class InjectionTest(unittest.TestCase):
    """反例注入：坏目录必须逐项被抓出来。"""

    def _good_catalog(self) -> dict:
        return {
            "schema": apv.CATALOG_SCHEMA,
            "gates": [{"command": "python tools/audit_families.py", "seam": "family"}],
        }

    def test_good_sample_has_no_shape_problems(self):
        self.assertEqual([], apv.catalog_problems(self._good_catalog()))

    def test_wrong_schema_is_caught(self):
        catalog = self._good_catalog()
        catalog["schema"] = "nope-1.0"
        self.assertTrue(any("schema" in p for p in apv.catalog_problems(catalog)))

    def test_unknown_seam_is_caught(self):
        catalog = self._good_catalog()
        catalog["gates"][0]["seam"] = "not_a_seam"
        self.assertTrue(any("seam" in p for p in apv.catalog_problems(catalog)))

    def test_unknown_env_is_caught(self):
        catalog = self._good_catalog()
        catalog["gates"][0]["env"] = "whenever"
        self.assertTrue(any("env" in p for p in apv.catalog_problems(catalog)))

    def test_duplicate_command_is_caught(self):
        catalog = self._good_catalog()
        catalog["gates"].append(dict(catalog["gates"][0]))
        self.assertTrue(any("重复" in p for p in apv.catalog_problems(catalog)))

    def test_missing_tool_command_is_caught(self):
        catalog = self._good_catalog()
        catalog["gates"].append({"command": "python tools/audit_definitely_absent.py", "seam": "kernel"})
        self.assertTrue(any("不存在" in p for p in apv.existing_problems(catalog)))

    def test_partial_coverage_is_caught(self):
        # 只声明一个工具 ⇒ 覆盖率必然不满（宇宙是真实 tools/ 目录）
        self.assertTrue(apv.coverage_problems(self._good_catalog()))

    def test_cnb_hand_list_is_caught(self):
        problems = apv.cnb_problems("      python tools/audit_families.py\n")
        self.assertTrue(any("仍在手列" in p for p in problems))

    def test_cnb_missing_runner_is_caught(self):
        problems = apv.cnb_problems("      echo hello\n")
        self.assertTrue(any("--run" in p for p in problems))

    def test_cnb_runner_itself_is_not_flagged_as_hand_list(self):
        problems = apv.cnb_problems(f"      python {apv.RUNNER_TOKEN} --run\n")
        self.assertEqual([], problems)


class VerifyCatalogPublicSurfaceTest(unittest.TestCase):
    """Phase 8：目录是**控制面一等数据** —— 对外形态可公开（相对路径 / 派生计数），
    而仓库自身的判据（覆盖率宇宙、`.cnb.yml` 手列检查）**不在这层**（分层不许回流）。"""

    def test_summary_shape_is_public_safe(self):
        from backend import verify_catalog as vc

        payload = vc.summary()
        self.assertEqual("plugin-verify-1.0", payload["schema"])
        self.assertEqual("registry/verify/index.json", payload["catalog"])
        self.assertNotIn(str(ROOT), str(payload), "对外形态不许吐绝对路径")
        counts = payload["counts"]
        self.assertEqual(counts["total"], counts["planned"] + counts["env_gated"])
        self.assertEqual(len(payload["gates"]), counts["total"])
        for entry in payload["gates"]:
            with self.subTest(command=entry["command"]):
                self.assertTrue(entry["command"])
                self.assertIn(entry["seam"], vc.FROZEN_SEAMS)

    def test_tool_and_control_plane_share_one_implementation(self):
        from backend import verify_catalog as vc

        catalog = vc.load_catalog()
        self.assertEqual(vc.catalog_problems(catalog), [])
        # 工具是**再导出**（同名对象），不是第二份实现
        self.assertEqual(apv.CATALOG_SCHEMA, vc.CATALOG_SCHEMA)
        self.assertEqual(apv.catalog_problems(catalog), vc.catalog_problems(catalog))
        self.assertEqual(apv.planned_commands(catalog), vc.planned_commands(catalog))
        self.assertEqual(apv.skipped_commands(catalog), vc.skipped_commands(catalog))
        self.assertEqual(apv.CATALOG_PATH, vc.CATALOG_PATH)

    def test_third_party_can_point_at_their_own_catalog(self):
        """公开的访问层要能被第三方拿去读**自己的**目录（路径可覆盖）。"""
        import json
        import tempfile

        from backend import verify_catalog as vc

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps({
                "schema": "plugin-verify-1.0",
                "gates": [{"command": "python tools/x.py", "seam": "kernel"}],
            }), encoding="utf-8")
            payload = vc.summary(vc.load_catalog(path))
        self.assertEqual(1, payload["counts"]["total"])
        self.assertEqual(1, payload["counts"]["planned"])

    def test_repo_specific_judgements_stay_in_tools(self):
        from backend import verify_catalog as vc

        self.assertFalse(hasattr(vc, "universe_tools"), "覆盖率宇宙是仓库自身判据，不该进控制面")
        self.assertTrue(hasattr(apv, "universe_tools"))


if __name__ == "__main__":
    unittest.main()
