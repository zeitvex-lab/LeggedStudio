"""H5 CLI：``import-scenario``（离线命令）—— 导出的**对偶**。

**为什么库测试之外还要单独钉 CLI 一层**：判据（三种形态 / 完整性 / 契约）已在
`backend/test_bundle_export.py::ScenarioImportTest` 钉过；但库对了而**接线错**（子命令没进
dispatcher、参数名写错、退出码写反、`--offline` 语义漏了）在库测试里**完全看不出来**。
本仓对离线命令的一贯做法是 subprocess 真调 `scripts/legged_studio_cli.py`（与用户用法完全一致），
见 `test_cli_lists` / `test_cli_deploy` / `test_cli_onboard_verify`。

守三条：

1. **往返**：`export scenario` → `import-scenario` 退出码 0，且 `--json` 输出可解析；
2. **如实**：裸 JSON 形态明确标注"无 manifest 可验"，不假装验过；导出目录则报完整性通过；
3. **可当门禁**：判据不通过（被改过的包）⇒ **退出码非 0**；落盘默认**不覆盖**已存在文件。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "legged_studio_cli.py"
#: 控制面 venv 的 python（测试正是跑在里面）；不存在则退回当前解释器。
_VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.is_file() else sys.executable


def _run(*args: str) -> subprocess.CompletedProcess:
    """真调 CLI。**显式 UTF-8**：脚本输出含中文，按 locale 解码在 Windows 会抛错（今日刚修过的缺陷类）。"""

    return subprocess.run(
        [PYTHON, str(CLI), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
    )


class ImportScenarioCliTest(unittest.TestCase):
    def _scenario(self, tmp: str) -> Path:
        path = Path(tmp) / "source.json"
        path.write_text(
            json.dumps(
                {"scenario_id": "warehouse_demo", "map_id": "warehouse", "mode": "navigation",
                 "waypoints": [{"x": 0, "y": 0}, {"x": 2, "y": 1}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_export_then_import_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            exported = _run("export", "scenario", "--scenario", str(self._scenario(tmp)), "--out", str(pack))
            self.assertEqual(0, exported.returncode, exported.stdout + exported.stderr)
            imported = _run("import-scenario", str(pack), "--json")
            self.assertEqual(0, imported.returncode, imported.stdout + imported.stderr)
            payload = json.loads(imported.stdout)
            self.assertEqual("export_dir", payload["form"])
            self.assertEqual("warehouse_demo", payload["scenario_id"])
            self.assertTrue(payload["integrity"]["ok"])
            self.assertEqual("warehouse", payload["scenario"]["map_id"])

    def test_bare_json_is_honest_about_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run("import-scenario", str(self._scenario(tmp)))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("bare_json", result.stdout)
            self.assertIn("无 manifest 可验", result.stdout, "裸 JSON 不许假装验过完整性")

    def test_tampered_pack_exits_nonzero(self):
        """被改过的包 ⇒ 退出码非 0（可当门禁用），而不是"打印个警告继续退 0"。"""

        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            _run("export", "scenario", "--scenario", str(self._scenario(tmp)), "--out", str(pack))
            target = pack / "scenario.json"
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["map_id"] = "flat"
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = _run("import-scenario", str(pack))
            self.assertNotEqual(0, result.returncode)
            self.assertIn("完整性", result.stdout + result.stderr)

    def test_out_lands_and_does_not_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            _run("export", "scenario", "--scenario", str(self._scenario(tmp)), "--out", str(pack))
            dest = Path(tmp) / "landed"
            first = _run("import-scenario", str(pack), "--out", str(dest))
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            landed = dest / "scenario.json"
            self.assertTrue(landed.is_file())
            self.assertEqual("warehouse_demo", json.loads(landed.read_text(encoding="utf-8"))["scenario_id"])
            # 默认不覆盖：再导一次必须被挡住（退出码非 0）
            second = _run("import-scenario", str(pack), "--out", str(dest))
            self.assertNotEqual(0, second.returncode)
            # 显式 --force 才允许覆盖
            forced = _run("import-scenario", str(pack), "--out", str(dest), "--force")
            self.assertEqual(0, forced.returncode, forced.stdout + forced.stderr)


if __name__ == "__main__":
    unittest.main()
