# -*- coding: utf-8 -*-
"""插件总表（``registry/plugin-registry.json``）双向对账锁（v3.0 Phase 0c）。

总表是 seam → 文件 → schema 三元组的唯一真值（``runtime_registry`` 的档位清单、
门禁与文档都从它派生）。本测试守**双向**不漂移：

1. 磁盘上的每个注册表 JSON 都有总表条目（**新文件必须登记**，否则就是游离注册表）；
2. 总表每个条目都真实存在且 schema 与文件一致（**总表不许谎报**）；
3. seam ∈ 13 冻结清单；runtime 档位 = 三份运行时注册表；
4. manifest 目录下的每个插件清单都是合法 ``legged-plugin-1.0``（schema/seam/provides）。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REGISTRY_DIR = ROOT / "registry"
MASTER = REGISTRY_DIR / "plugin-registry.json"

FROZEN_SEAMS = {"robot", "family", "skill", "terrain", "reward", "algorithm",
                "task", "sensor", "evaluator", "panel", "controller", "pack", "profile"}


def _master() -> dict:
    return json.loads(MASTER.read_text(encoding="utf-8-sig"))


def _catalog_files() -> set[str]:
    """registry/ 下的数据目录文件（plugins/ 清单目录与总表本身除外）。"""
    return {
        p.relative_to(REGISTRY_DIR).as_posix()
        for p in REGISTRY_DIR.rglob("*.json")
        if "plugins" not in p.parts and p.name != "plugin-registry.json"
    }


def _manifest_files() -> list[Path]:
    return sorted((REGISTRY_DIR / "plugins").rglob("*.json"))


class MasterTableParityTest(unittest.TestCase):
    def test_every_catalog_file_is_registered(self):
        registered = {spec["path"] for spec in _master()["registries"].values()
                      if not spec["path"].startswith("../")}
        on_disk = _catalog_files()
        self.assertEqual(set(), on_disk - registered,
                         "游离注册表（新文件必须登记进总表）")
        self.assertEqual(set(), registered - on_disk,
                         "总表登记了不存在的文件（谎报）")

    def test_every_registered_schema_matches_file(self):
        for name, spec in _master()["registries"].items():
            with self.subTest(name=name):
                path = REGISTRY_DIR / spec["path"]
                self.assertTrue(path.is_file(), f"{name}: 文件不存在")
                doc = json.loads(path.read_text(encoding="utf-8-sig"))
                self.assertEqual(spec["schema"], doc.get("schema"),
                                 f"{name}: 总表 schema 与文件不一致")

    def test_seams_within_frozen_vocabulary(self):
        master = _master()
        self.assertEqual(sorted(FROZEN_SEAMS), master["seams"], "13 seam 冻结清单本身不许漂")
        for name, spec in master["registries"].items():
            self.assertIn(spec["seam"], FROZEN_SEAMS, f"{name}: seam 不在冻结清单")

    def test_runtime_registries_are_the_three_profiles(self):
        runtime = {name for name, spec in _master()["registries"].items() if spec.get("runtime")}
        self.assertEqual({"cameras", "motion_commands", "arrival_criteria"}, runtime)

    def test_runtime_registry_uses_master_table(self):
        from backend import runtime_registry as rr
        files = rr.runtime_registry_files()
        self.assertEqual(
            {"cameras": ("cameras.json", "camera-profile-1.0"),
             "motion_commands": ("motion_commands.json", "motion-command-profile-1.0"),
             "arrival_criteria": ("arrival_criteria.json", "arrival-criteria-1.0")},
            files)
        # 老硬编码字典必须已删除（Phase 3a 判据：grep REGISTRY_FILES == 0）
        self.assertFalse(hasattr(rr, "REGISTRY_FILES"),
                         "REGISTRY_FILES 硬编码字典必须删除（唯一真值在总表）")


class ManifestDirTest(unittest.TestCase):
    def test_every_manifest_is_legged_plugin(self):
        manifests = _manifest_files()
        self.assertTrue(manifests, "registry/plugins/ 清单目录不能为空")
        for path in manifests:
            with self.subTest(manifest=path.name):
                doc = json.loads(path.read_text(encoding="utf-8-sig"))
                self.assertEqual("legged-plugin-1.0", doc.get("schema"), path)
                self.assertIn(doc.get("seam"), FROZEN_SEAMS, path)
                self.assertTrue(doc.get("id"), path)
                self.assertIn(f"{doc['seam']}/{doc['id']}", doc.get("provides") or [],
                              f"{path}: provides 必须含自身服务键")

    def test_panel_manifests_project_four_surfaces(self):
        panels = [p for p in _manifest_files() if p.parent.name == "panel"]
        self.assertEqual(9, len(panels))
        ids = {json.loads(p.read_text(encoding="utf-8-sig"))["id"] for p in panels}
        self.assertEqual({"home", "robot", "controllers", "config", "training",
                          "simulation", "navmap", "deploy", "artifacts"}, ids)


if __name__ == "__main__":
    unittest.main()
