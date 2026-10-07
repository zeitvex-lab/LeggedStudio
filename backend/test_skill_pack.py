"""E7：Skill 包（纯 JSON）的导出 / 校验 / 导入 —— 判据是「**他人可导入并校验**」。

守三条：**摘要**（改了能查出来）、**闭环**（patch 缺基座即报）、**路径不可信**
（包来自外部，`..` 必须拒）。这三条都属于"看起来像对了、实际能被利用"的那一类，
所以每条都有对应的反例测试。

**Phase 6（2026-10-07）后夹具换了来源**：真实仓的技能注册表**只放族级基座**
（`velocity_base`），机型补丁已迁 profile 层 —— 于是"patch 语义"（带上基座 / 缺基座即
拒 / 往返）改用**合成注册表**（一个基座 + 一个补丁）钉住，不再依赖真机型补丁。
"""

import contextlib
import json
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

from backend import skill_pack

RECIPE = "velocity_base"
#: 合成样本（真实仓已无机型补丁）：`SYNTHETIC_PATCH` extends `SYNTHETIC_BASE`。
SYNTHETIC_BASE = "synthetic_base"
SYNTHETIC_PATCH = "synthetic_rough"


def _recipe(recipe_id: str, **extra) -> dict:
    return {"schema": "skill-recipe-2.0", "recipe_id": recipe_id,
            "display_name": recipe_id, **extra}


@contextlib.contextmanager
def synthetic_registry() -> Iterator[Path]:
    """临时造一个「基座 + 补丁」的技能注册表，**产出其 skills 目录**。

    `skill_pack.export_pack/import_pack` 都收显式 `skills_dir`，所以不必改全局 `SKILLS_DIR`
    （也绕开"默认参数在定义时绑定"那个坑）。补丁与基座的关系由清单的 `patch_of` 声明。
    """
    with tempfile.TemporaryDirectory() as tmp:
        skills = Path(tmp) / "skills"
        skills.mkdir()
        (skills / "index.json").write_text(json.dumps({
            "schema": "skill-index-1.0",
            "skills": [
                {"recipe_id": SYNTHETIC_BASE, "path": f"{SYNTHETIC_BASE}.json", "role": "base"},
                {"recipe_id": SYNTHETIC_PATCH, "path": f"{SYNTHETIC_PATCH}.json",
                 "role": "patch", "patch_of": SYNTHETIC_BASE},
            ],
        }), encoding="utf-8")
        (skills / f"{SYNTHETIC_BASE}.json").write_text(json.dumps(_recipe(
            SYNTHETIC_BASE, num_envs=4096, runner={"learning_rate": 0.001},
        )), encoding="utf-8")
        (skills / f"{SYNTHETIC_PATCH}.json").write_text(json.dumps(_recipe(
            SYNTHETIC_PATCH, extends=SYNTHETIC_BASE, num_envs=2048,
        )), encoding="utf-8")
        yield skills


class ExportTest(unittest.TestCase):
    def test_export_base_is_self_contained_and_verifies(self):
        pack = skill_pack.export_pack(RECIPE)
        report = skill_pack.verify_pack(pack)
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual([RECIPE], report["recipes"])
        self.assertEqual("skill-pack-1.0", pack["schema"])
        self.assertTrue(pack["digest"])

    def test_export_patch_brings_its_base_along(self):
        """**闭环**：patch 离开基座毫无意义 —— 导出时必须自动带上基座。"""
        with synthetic_registry() as skills:
            pack = skill_pack.export_pack(SYNTHETIC_PATCH, skills_dir=skills)
        ids = {record["recipe_id"] for record in pack["recipes"]}
        self.assertEqual({SYNTHETIC_PATCH, SYNTHETIC_BASE}, ids)
        self.assertTrue(skill_pack.verify_pack(pack)["ok"])

    def test_unknown_recipe_is_reported_with_available_ids(self):
        with self.assertRaises(Exception) as ctx:
            skill_pack.export_pack("no-such-recipe")
        self.assertIn("velocity_base", str(ctx.exception))


class VerifyTest(unittest.TestCase):
    @staticmethod
    def _pack() -> tuple[dict, str]:
        """合成注册表导出的 patch 包 + 其基座 id（patch 与基座都在包内）。"""
        with synthetic_registry() as skills:
            return skill_pack.export_pack(SYNTHETIC_PATCH, skills_dir=skills), SYNTHETIC_BASE

    def test_content_tampering_is_detected(self):
        """改了包里的数值 → 摘要对不上（不是"看起来像"，是可校验）。"""
        pack, base_id = self._pack()
        target = next(r for r in pack["recipes"] if r["recipe_id"] == base_id)
        target["content"]["display_name"] = "被改过的名字"
        problems = skill_pack.verify_pack(pack)["problems"]
        self.assertTrue(any("内容摘要不一致" in item for item in problems), problems)

    def test_pack_level_digest_covers_everything(self):
        """连"改了摘要字段本身"也要被抓住。"""
        pack, _ = self._pack()
        pack["exported_at"] = "1999-01-01T00:00:00+00:00"
        problems = skill_pack.verify_pack(pack)["problems"]
        self.assertTrue(any("包摘要不一致" in item for item in problems), problems)

    def test_patch_without_base_is_a_problem(self):
        """残包（只有 patch、没有基座）必须在**校验**阶段就被拒，而不是导入后才发现。"""
        pack, base_id = self._pack()
        pack["recipes"] = [r for r in pack["recipes"] if r["recipe_id"] != base_id]
        pack["digest"] = skill_pack.canonical_digest(
            {k: v for k, v in pack.items() if k != "digest"},
        )
        problems = skill_pack.verify_pack(pack)["problems"]
        self.assertTrue(any("的基座不在包内" in item for item in problems), problems)

    def test_path_traversal_is_rejected(self):
        """包是**外部输入**：`../` 必须拒，否则一个包就能写到 registry/ 之外。"""
        pack = skill_pack.export_pack(RECIPE)
        pack["recipes"][0]["path"] = "../evil.json"
        pack["digest"] = skill_pack.canonical_digest(
            {k: v for k, v in pack.items() if k != "digest"},
        )
        problems = skill_pack.verify_pack(pack)["problems"]
        self.assertTrue(any("相对路径" in item for item in problems), problems)

    def test_non_object_and_bad_schema_are_refused(self):
        self.assertFalse(skill_pack.verify_pack(["not", "an", "object"])["ok"])
        self.assertFalse(skill_pack.verify_pack({"schema": "other-1.0"})["ok"])


class RoundTripTest(unittest.TestCase):
    """**判据本体**：他人拿到包 → 校验通过 → 导入自己的注册表。"""

    @staticmethod
    def _empty_registry(root: Path) -> Path:
        skills = root / "skills"
        skills.mkdir(parents=True)
        (skills / "index.json").write_text(
            json.dumps({"schema": "skill-index-1.0", "skills": []}), encoding="utf-8",
        )
        return skills

    def test_import_into_fresh_registry_then_export_again(self):
        with synthetic_registry() as source, tempfile.TemporaryDirectory() as tmp:
            skills = self._empty_registry(Path(tmp))
            pack = skill_pack.export_pack(SYNTHETIC_PATCH, skills_dir=source)

            dry = skill_pack.import_pack(pack, skills_dir=skills)          # 预演不落盘
            self.assertTrue(dry["ok"], dry["problems"])
            self.assertEqual([], dry["written"])
            self.assertFalse((skills / "patches").exists())

            result = skill_pack.import_pack(pack, skills_dir=skills, write=True)
            self.assertTrue(result["ok"], result["problems"])
            self.assertEqual(2, len(result["written"]))
            self.assertTrue(result["index_updated"])

            # 导入方现在能**自己**导出同一个包（往返一致 = 真的自包含）
            again = skill_pack.export_pack(SYNTHETIC_PATCH, skills_dir=skills)
            self.assertEqual(
                {r["recipe_id"]: r["sha256"] for r in pack["recipes"]},
                {r["recipe_id"]: r["sha256"] for r in again["recipes"]},
            )
            self.assertTrue(skill_pack.verify_pack(again)["ok"])

    def test_existing_different_skill_is_not_silently_overwritten(self):
        """导入不能悄悄改掉别人已有的技能 —— 必须显式 overwrite。"""
        with tempfile.TemporaryDirectory() as tmp:
            skills = self._empty_registry(Path(tmp))
            pack = skill_pack.export_pack(RECIPE)
            base = next(r for r in pack["recipes"] if r["recipe_id"] == RECIPE)
            target = skills / base["path"]

            self.assertTrue(skill_pack.import_pack(pack, skills_dir=skills, write=True)["ok"])
            target.write_text(
                json.dumps({**base["content"], "display_name": "本地改过的版本"},
                           ensure_ascii=False), encoding="utf-8",
            )

            refused = skill_pack.import_pack(pack, skills_dir=skills, write=True)
            self.assertFalse(refused["ok"])
            self.assertTrue(any("overwrite" in item for item in refused["problems"]))
            self.assertIn("本地改过的版本", target.read_text(encoding="utf-8"))

            forced = skill_pack.import_pack(pack, skills_dir=skills, overwrite=True, write=True)
            self.assertTrue(forced["ok"], forced["problems"])

    def test_broken_pack_never_touches_disk(self):
        """fail-closed：校验不过，**一个字节都不写**。"""
        with tempfile.TemporaryDirectory() as tmp:
            skills = self._empty_registry(Path(tmp))
            pack = skill_pack.export_pack(RECIPE)
            pack["recipes"][0]["sha256"] = "0" * 64              # 篡改
            result = skill_pack.import_pack(pack, skills_dir=skills, write=True)
            self.assertFalse(result["ok"])
            self.assertEqual([], result["written"])
            self.assertFalse((skills / "velocity_base.json").exists())


class RealRegistryTest(unittest.TestCase):
    """**真实仓不变量**：清单里每个技能都能导出成可校验的包。"""

    def test_every_registered_skill_exports_and_verifies(self):
        from backend.skill_registry import skill_manifest

        entries = skill_manifest()["skills"]
        self.assertTrue(entries, "技能注册表不能为空")
        for item in entries:
            recipe_id = str(item["recipe_id"])
            with self.subTest(recipe=recipe_id):
                pack = skill_pack.export_pack(recipe_id)
                report = skill_pack.verify_pack(pack)
                self.assertTrue(report["ok"], report["problems"])


if __name__ == "__main__":
    unittest.main()
