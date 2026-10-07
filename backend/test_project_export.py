# -*- coding: utf-8 -*-
"""N5 单文件工程的回归锁（`backend/bundle_export.py::export_project / verify_project`）。

判据是「**可分享的单文件**」：一个文件里装着包 + 档案 + 基线，别人拿到后 ① 能校验完整性、
② 校验走的是**同一道闸**（`verify_export`：逐条 sha256 + 角色 + 幽灵文件检查）。

三条必须守住：**摘要**（改一个字节就查得出）、**不装幽灵**（manifest 没登记的即拒）、
**路径不可信**（zip-slip 拒）。每条都有反例测试。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import bundle_export  # noqa: E402

PACK = ROOT / "packs" / "unitree_go2.pack.json"


def _baseline(tmp: Path, name: str = "sim2sim_baseline.json") -> Path:
    path = tmp / name
    path.write_text(json.dumps({"schema": "fixture", "ok": True}), encoding="utf-8")
    return path


def _rewrite(source: Path, target: Path, *, drop: str | None = None,
             replace: dict[str, bytes] | None = None, add: dict[str, bytes] | None = None) -> Path:
    """按需增删改一个 zip 的成员（用来造反例）。"""
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w") as dst:
        for info in src.infolist():
            if drop and info.filename == drop:
                continue
            payload = (replace or {}).get(info.filename, src.read(info.filename))
            dst.writestr(info, payload)
        for name, payload in (add or {}).items():
            dst.writestr(name, payload)
    return target


class ProjectExportTest(unittest.TestCase):
    def test_round_trip_exports_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "go2.zip"
            result = bundle_export.export_project(PACK, out, baselines=[_baseline(Path(tmp))])
            self.assertEqual("project", result["kind"])
            self.assertTrue(out.is_file())
            self.assertEqual(64, len(result["file_sha256"]))

            report = bundle_export.verify_project(out)
            self.assertTrue(report["ok"], report["problems"])
            self.assertEqual("project", report["kind"])
            self.assertEqual(result["file_sha256"], report["file_sha256"])
            roles = set(report["roles"])
            self.assertIn("baseline", roles)
            for role in bundle_export.REQUIRED_ROLES["project"]:
                self.assertIn(role, roles, f"缺必需角色 {role}")

    def test_baseline_is_inside_the_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "go2.zip"
            bundle_export.export_project(PACK, out, baselines=[_baseline(Path(tmp))])
            with zipfile.ZipFile(out) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))
            self.assertIn("baselines/sim2sim_baseline.json", names)
            self.assertIn(
                "baselines/sim2sim_baseline.json",
                {entry["path"] for entry in manifest["entries"]},
            )

    def test_notes_declare_the_project_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "go2.zip"
            bundle_export.export_project(PACK, out, baselines=[_baseline(Path(tmp))])
            with zipfile.ZipFile(out) as archive:
                manifest = json.loads(archive.read("manifest.json"))
        self.assertTrue(any("单文件工程" in note for note in manifest["notes"]), manifest["notes"])

    def test_content_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "go2.zip"
            result = bundle_export.export_project(PACK, out, baselines=[_baseline(Path(tmp))])
            target = next(entry["path"] for entry in result["entries"]
                          if entry["role"] == "baseline")
            tampered = _rewrite(out, Path(tmp) / "tampered.zip",
                                replace={target: b'{"schema": "fixture", "ok": false}'})
            report = bundle_export.verify_project(tampered)
        self.assertFalse(report["ok"])
        self.assertTrue(any("sha256 与 manifest 不符" in item for item in report["problems"]),
                        report["problems"])

    def test_ghost_file_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "go2.zip"
            bundle_export.export_project(PACK, out)
            ghosted = _rewrite(out, Path(tmp) / "ghost.zip", add={"extra.txt": b"not registered"})
            report = bundle_export.verify_project(ghosted)
        self.assertFalse(report["ok"])
        self.assertTrue(any("幽灵文件" in item for item in report["problems"]), report["problems"])

    def test_missing_registered_file_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "go2.zip"
            result = bundle_export.export_project(PACK, out)
            drop = result["entries"][0]["path"]
            stripped = _rewrite(out, Path(tmp) / "stripped.zip", drop=drop)
            report = bundle_export.verify_project(stripped)
        self.assertFalse(report["ok"])
        self.assertTrue(any("manifest 登记了但磁盘上没有" in item for item in report["problems"]),
                        report["problems"])

    def test_zip_slip_is_refused_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "go2.zip"
            bundle_export.export_project(PACK, out)
            escaping = _rewrite(out, Path(tmp) / "slip.zip", add={"../evil.txt": b"nope"})
            report = bundle_export.verify_project(escaping)
        self.assertFalse(report["ok"])
        self.assertTrue(any("越界路径" in item for item in report["problems"]), report["problems"])


class ProjectGuardTest(unittest.TestCase):
    def test_suffix_must_be_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                bundle_export.export_project(PACK, Path(tmp) / "go2.tar")

    def test_missing_baseline_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                bundle_export.export_project(PACK, Path(tmp) / "go2.zip",
                                             baselines=[Path(tmp) / "nope.json"])

    def test_verify_missing_file_reports(self):
        report = bundle_export.verify_project(ROOT / "definitely_not_here.zip")
        self.assertFalse(report["ok"])
        self.assertTrue(any("文件不存在" in item for item in report["problems"]))

    def test_verify_non_zip_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake.zip"
            path.write_bytes(b"definitely not a zip")
            report = bundle_export.verify_project(path)
        self.assertFalse(report["ok"])
        self.assertTrue(any("不是合法的 zip" in item for item in report["problems"]))

    def test_project_kind_is_registered(self):
        self.assertIn("project", bundle_export.EXPORT_KINDS)
        self.assertIn("project", bundle_export.REQUIRED_ROLES)
        self.assertEqual(".zip", bundle_export.PROJECT_SUFFIX)


if __name__ == "__main__":
    unittest.main()
