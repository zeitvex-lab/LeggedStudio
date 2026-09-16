"""B1 剩余项的 DoD：14 份 Capability Pack 全过校验、目录可列出、坏 Pack 能被抓住。

2026-09-12 实测：schema 与 14 份 Pack 已在位，缺的是「校验 + 列出」入口。本测试
同时守住 schema 与本模块校验器的漂移——合成用例逐条对应 schema 的
``required`` / ``pattern`` / ``enum`` / ``additionalProperties``。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.pack_catalog import (
    PACKS_DIR,
    WORKSPACE_ROOT,
    get_pack,
    load_packs,
    pack_catalog,
    validate_pack,
)

EXPECTED_MIN_PACKS = 14  # assets/robots 的 14 个内置机型各一份默认 Pack


def _base_pack(**overrides) -> dict:
    pack = {
        "schema_version": "capability-pack-1.0",
        "pack_id": "unitree_go2",
        "morphology_ref": {"id": "unitree_go2"},
        # skill_ref 必须能在 K4 技能注册表里解析（见 ValidatePackTest.test_dangling_skill_ref_is_rejected）：
        # 夹具用真 recipe id，否则结构性用例会先被"引用悬空"拦掉，测不到本来要测的东西。
        "skill_ref": {"id": "velocity_base"},
    }
    pack.update(overrides)
    return pack


class BuiltinPacksTest(unittest.TestCase):
    def test_all_packs_pass_validation(self) -> None:
        entries = load_packs()
        self.assertGreaterEqual(len(entries), EXPECTED_MIN_PACKS)
        for entry in entries:
            with self.subTest(pack=entry["pack_id"]):
                self.assertTrue(entry["valid"], f"{entry['file']}: {entry['errors']}")

    def test_catalog_shape_and_no_duplicates(self) -> None:
        catalog = pack_catalog()
        self.assertEqual(catalog["schema_version"], "capability-pack-catalog-1.0")
        self.assertEqual(catalog["count"], len(catalog["packs"]))
        self.assertEqual(catalog["invalid_count"], 0)
        self.assertEqual(catalog["duplicates"], [])
        for entry in catalog["packs"]:
            for key in ("pack_id", "valid", "morphology_ref", "skill_ref", "bindings", "file"):
                self.assertIn(key, entry)

    def test_morphology_ref_resolves_to_contract_v3_with_matching_hash(self) -> None:
        for entry in load_packs():
            ref = entry["morphology_ref"] or {}
            with self.subTest(pack=entry["pack_id"]):
                self.assertTrue(str(ref.get("path", "")).endswith("contract_v3.json"))
                resolved = entry["refs"]["morphology_ref"]
                self.assertTrue(resolved.get("exists"), resolved)
                self.assertTrue(resolved.get("sha256_ok"), resolved)

    def test_get_pack_returns_entry_and_unknown_is_none(self) -> None:
        entry = get_pack("unitree_go2-velocity")
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["pack_id"], "unitree_go2-velocity")
        self.assertIsNone(get_pack("no_such_pack"))


class SkillRefResolutionTest(unittest.TestCase):
    """skill_ref 必须解析到登记在册的技能（`require_refs_resolved` 从空话变成判据）。"""

    def test_every_builtin_pack_skill_ref_resolves(self) -> None:
        for entry in load_packs():
            with self.subTest(pack=entry["pack_id"]):
                recipe = (entry["refs"].get("skill_ref") or {}).get("recipe") or {}
                self.assertTrue(recipe.get("resolved"), f"{entry['file']}: {recipe}")
                self.assertEqual("velocity_base", recipe.get("id"))
                self.assertEqual("base", recipe.get("role"))

    def test_builtin_pack_skill_ref_is_hash_pinned(self) -> None:
        """引用带 path + sha256 ⇒ 与 morphology_ref 同纪律：技能文件被改必被发现。"""

        for entry in load_packs():
            ref = entry["skill_ref"] or {}
            with self.subTest(pack=entry["pack_id"]):
                self.assertTrue(str(ref.get("path", "")).endswith(".json"), ref)
                resolved = entry["refs"]["skill_ref"]
                self.assertTrue(resolved.get("exists"), resolved)
                self.assertTrue(resolved.get("sha256_ok"), resolved)

    def test_dangling_skill_ref_is_rejected(self) -> None:
        """M1 时代的 `core/velocity@2.0` 在仓库里没有实体 —— 这种悬空引用必须报错。"""

        report = validate_pack(_base_pack(skill_ref={"id": "core/velocity@2.0", "version": "2.0"}))
        self.assertFalse(report["ok"])
        self.assertTrue(any("解析不到实体" in error for error in report["errors"]), report["errors"])

    def test_contract_switch_downgrades_to_warning(self) -> None:
        """`bindings.verify.require_refs_resolved=false` 是**契约里写着的开关**，要真的起作用。"""

        report = validate_pack(_base_pack(
            skill_ref={"id": "core/velocity@2.0", "version": "2.0"},
            bindings={"verify": {"require_refs_resolved": False, "require_contract_valid": False}},
        ))
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(any("解析不到实体" in warning for warning in report["warnings"]), report["warnings"])


class ValidatePackTest(unittest.TestCase):
    def test_absolute_path_rejected(self) -> None:
        import os
        # 平台相关：Windows 上 Path("/etc/passwd").is_absolute() 为 False，须用盘符样例
        abs_path = "C:/etc/passwd" if os.name == "nt" else "/etc/passwd"
        report = validate_pack(_base_pack(morphology_ref={"id": "go2", "path": abs_path}))
        self.assertFalse(report["ok"])
        self.assertTrue(any("相对路径" in e for e in report["errors"]))

    def test_parent_path_rejected(self) -> None:
        report = validate_pack(_base_pack(morphology_ref={"id": "go2", "path": "../outside.json"}))
        self.assertFalse(report["ok"])
        self.assertTrue(any("相对路径" in e for e in report["errors"]))

    def test_stale_hash_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "m.json").write_text("{}", encoding="utf-8")
            report = validate_pack(
                _base_pack(morphology_ref={"id": "x", "path": "m.json", "sha256": "0" * 64}),
                workspace_root=root,
            )
            self.assertFalse(report["ok"])
            self.assertTrue(any("实际文件不一致" in e for e in report["errors"]))

    def test_reference_resolves_with_matching_hash(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "m.json").write_text('{"robot_id": "x"}', encoding="utf-8")
            digest = hashlib.sha256((root / "m.json").read_bytes()).hexdigest()
            report = validate_pack(
                _base_pack(morphology_ref={"id": "x", "path": "m.json", "sha256": digest}),
                workspace_root=root,
            )
            self.assertTrue(report["ok"], report["errors"])

    def test_required_refs_and_schema_version_enforced(self) -> None:
        report = validate_pack({"schema_version": "capability-pack-1.0", "pack_id": "x"})
        self.assertFalse(report["ok"])
        self.assertTrue(any("morphology_ref 缺失" in e for e in report["errors"]))
        self.assertTrue(any("skill_ref 缺失" in e for e in report["errors"]))

        report = validate_pack(_base_pack(schema_version="capability-pack-2.0"))
        self.assertFalse(report["ok"])
        self.assertTrue(any("schema_version" in e for e in report["errors"]))

    def test_pack_id_pattern_enforced(self) -> None:
        report = validate_pack(_base_pack(pack_id="Unitree Go2"))
        self.assertFalse(report["ok"])
        self.assertTrue(any("pack_id 不合法" in e for e in report["errors"]))

    def test_unknown_binding_key_and_bad_enum_rejected(self) -> None:
        report = validate_pack(_base_pack(bindings={"verify": {"nope": True}}))
        self.assertFalse(report["ok"])
        self.assertTrue(any("未声明字段" in e for e in report["errors"]))

        report = validate_pack(_base_pack(bindings={"train": {"pipeline_topology": "magic"}}))
        self.assertFalse(report["ok"])
        self.assertTrue(any("pipeline_topology" in e for e in report["errors"]))

        report = validate_pack(_base_pack(bindings={"simulate": {"executors": ["sora"]}}))
        self.assertFalse(report["ok"])
        self.assertTrue(any("executors" in e for e in report["errors"]))

    def test_duplicate_pack_id_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _base_pack()
            (root / "a.pack.json").write_text(json.dumps(payload), encoding="utf-8")
            (root / "b.pack.json").write_text(json.dumps(payload), encoding="utf-8")
            catalog = pack_catalog(root, workspace_root=WORKSPACE_ROOT)
            self.assertEqual(catalog["duplicates"], ["unitree_go2"])
            self.assertEqual(catalog["invalid_count"], 2)
            for entry in catalog["packs"]:
                self.assertTrue(any("pack_id 重复" in e for e in entry["errors"]))

    def test_unparsable_pack_is_reported_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.pack.json").write_text("{not json", encoding="utf-8")
            entries = load_packs(root)
            self.assertEqual(len(entries), 1)
            self.assertFalse(entries[0]["valid"])
            self.assertTrue(any("不可解析" in e for e in entries[0]["errors"]))


class PacksDirTest(unittest.TestCase):
    def test_packs_dir_is_repo_relative(self) -> None:
        self.assertEqual(PACKS_DIR, WORKSPACE_ROOT / "packs")
        self.assertTrue(PACKS_DIR.is_dir())


if __name__ == "__main__":
    unittest.main()
