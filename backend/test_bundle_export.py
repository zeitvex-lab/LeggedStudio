"""B12 五类导出 + Bundle：manifest/hash 纪律、边界与 fail-closed 行为。

## 这组测试守的是什么

愿景要求导出分五类粒度（Morphology / Skill / Scenario / Policy / Bundle），Bundle 的口径是
「Pack 引用 + **被引用物的离线副本** + 哈希」。此前仓内只有 Skill 包（纯 JSON 自包含）与
Policy 出库（目录 + 索引 hash），整包项目 zip **没有哈希** —— 搬过去之后内容有没有变没人知道。

本模块钉住四条：

1. **导出物自带证据**：manifest 逐条 `{path, sha256, bytes, role}`；`verify_export()` 从磁盘重算；
2. **一个导出物只有一份 manifest**（嵌套导出不再各写一份 —— 否则"幽灵文件"检查会失效）；
3. **必需角色**：每类至少要有哪些角色由 `REQUIRED_ROLES` 规定，缺即红（不许"导出了个空包还退 0"）；
4. **绑定要真的解析**：Bundle 的 skill 必须能在 K4 技能注册表里解析；解析不到就如实进 `unresolved`，
   并且第三方拷来的导出物也验得过（判据只看磁盘与 manifest，不依赖导出时的内存状态）。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import bundle_export as bx  # noqa: E402
from backend import policy_artifacts as pa  # noqa: E402


def _produced_artifact_id() -> str | None:
    for artifact_id, entry in sorted(pa.load_index().items()):
        if entry.get("kind") == "produced":
            return artifact_id
    return None


class MorphologyExportTest(unittest.TestCase):
    def test_exports_contract_and_model_without_training_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = bx.export_morphology("zex-w", Path(tmp) / "morph")
            roles = {entry["role"] for entry in manifest["entries"]}
            self.assertIn("package_manifest", roles)
            self.assertIn("contract", roles)
            self.assertIn("model", roles)
            paths = [entry["path"] for entry in manifest["entries"]]
            # 形态包**不含训练源码与策略权重**：那属别的粒度（Skill / Policy / Bundle）
            self.assertFalse(any("/training/" in path or path.endswith(".onnx") for path in paths), paths)
            self.assertTrue(bx.verify_export(Path(tmp) / "morph")["ok"])

    def test_unknown_robot_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                bx.export_morphology("no_such_robot", Path(tmp) / "morph")


class SkillAndScenarioExportTest(unittest.TestCase):
    def test_skill_export_matches_registry_payload(self):
        from backend import skill_pack

        with tempfile.TemporaryDirectory() as tmp:
            manifest = bx.export_skill("velocity_base", Path(tmp) / "skill")
            written = json.loads((Path(tmp) / "skill" / "skill.json").read_text(encoding="utf-8"))
            self.assertEqual(skill_pack.export_pack("velocity_base"), written)
            self.assertEqual("velocity_base", manifest["refs"]["skill"]["id"])
            self.assertTrue(bx.verify_export(Path(tmp) / "skill")["ok"])

    def test_unknown_recipe_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                bx.export_skill("no_such_recipe", Path(tmp) / "skill")

    def test_scenario_export_validates_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps({"scenario_id": "flat-demo", "map_id": "flat"}), encoding="utf-8")
            manifest = bx.export_scenario(good, Path(tmp) / "out")
            self.assertEqual("flat-demo", manifest["refs"]["scenario"]["id"])
            self.assertTrue(bx.verify_export(Path(tmp) / "out")["ok"])

    def test_invalid_scenario_fails_closed(self):
        """非法场景（scenario_id 不合 pattern）不许导出半成品。"""

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"scenario_id": "Bad Id!"}), encoding="utf-8")
            with self.assertRaises(Exception):
                bx.export_scenario(bad, Path(tmp) / "out")


class PolicyExportTest(unittest.TestCase):
    def test_policy_export_copies_blob_and_metadata(self):
        artifact_id = _produced_artifact_id()
        if artifact_id is None:
            self.skipTest("出库索引里没有 produced 产物（先在容器里跑一次训练）")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = bx.export_policy(artifact_id, Path(tmp) / "policy")
            roles = {entry["role"] for entry in manifest["entries"]}
            self.assertIn("policy", roles)
            self.assertIn("policy_meta", roles)
            report = bx.verify_export(Path(tmp) / "policy")
            self.assertTrue(report["ok"], report["problems"])

    def test_unknown_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                bx.export_policy("no_such_artifact", Path(tmp) / "policy")


class BundleExportTest(unittest.TestCase):
    """Bundle = Pack 引用 + **被引用物离线副本** + 哈希。"""

    def test_bundle_carries_pack_referenced_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", Path(tmp) / "bundle")
            roles = {entry["role"] for entry in manifest["entries"]}
            self.assertLessEqual({"pack", "package_manifest", "contract", "skill"}, roles)
            self.assertEqual([], manifest["unresolved"], "可解析的 Pack 不该有未解析项")
            report = bx.verify_export(Path(tmp) / "bundle")
            self.assertTrue(report["ok"], report["problems"])

    def test_bundle_has_exactly_one_manifest(self):
        """嵌套导出不许各写一份 manifest：多份会让'幽灵文件'检查失去意义。"""

        with tempfile.TemporaryDirectory() as tmp:
            bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", Path(tmp) / "bundle")
            found = sorted(path.relative_to(Path(tmp) / "bundle").as_posix() for path in (Path(tmp) / "bundle").rglob("manifest.json"))
            self.assertEqual(["manifest.json"], found)

    def test_nested_payload_paths_are_not_double_prefixed(self):
        """回归：嵌套导出曾把前缀写重（`morphology/morphology/…`、`policy/policy/…`）。

        成因是"子导出自带前缀 + Bundle 再加前缀"。后果不只是难看：R1 回放就绪检查按
        `morphology/contract_legacy_v2.json` 找文件，找不到就判"不就绪"—— 一个路径拼接 bug 会伪装成
        "这个包不能回放"。
        """

        with tempfile.TemporaryDirectory() as tmp:
            manifest = bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", Path(tmp) / "bundle")
            paths = [entry["path"] for entry in manifest["entries"]]
            for path in paths:
                head = path.split("/", 1)[0]
                if path.count("/") >= 1 and head in {"morphology", "policy", "skill", "scenario"}:
                    rest = path.split("/", 1)[1]
                    self.assertFalse(rest.startswith(f"{head}/"), f"前缀写重了：{path}")
            # Bundle 采用**包布局**（根目录即可被验收器/产出端消费，R1/R2 的前提）
            self.assertIn("contract_legacy_v2.json", paths)
            self.assertIn("simulation/config.json", paths)

    def test_dangling_skill_ref_is_recorded_not_hidden(self):
        """Pack 若指向注册表里没有的技能，Bundle 必须把"没带进去"写进 unresolved，而不是假装完整。"""

        with tempfile.TemporaryDirectory() as tmp:
            pack = json.loads((ROOT / "packs" / "zex-w.pack.json").read_text(encoding="utf-8"))
            pack["skill_ref"] = {"id": "core/velocity@2.0", "version": "2.0"}  # M1 时代的悬空命名
            dangling = Path(tmp) / "dangling.pack.json"
            dangling.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
            manifest = bx.export_bundle(dangling, Path(tmp) / "bundle")
            reasons = [item["reason"] for item in manifest["unresolved"]]
            self.assertTrue(any("core/velocity@2.0" in reason for reason in reasons), reasons)
            self.assertTrue(bx.verify_export(Path(tmp) / "bundle")["ok"], "未解析项本身不该让导出物不自洽")

    def test_bundle_is_a_runnable_package_layout(self):
        """Bundle 根目录本身要是一个能被验收/产出端消费的**机器人包布局**（R1/R2 的前提）。

        2026-09-16 之前形态文件套在 `morphology/` 子目录里、运行配置根本不在包里 ——
        于是"Bundle 在干净机器可跑"只能停在口号上（实测跑不起来）。
        """

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", out)
            for required in ("robot_package.json", "contract_legacy_v2.json", "model/robot.xml", "simulation/config.json"):
                self.assertTrue((out / required).is_file(), f"缺 {required}（Bundle 不是可跑的包布局）")

    def test_policy_placement_does_not_concat_filename_as_prefix(self):
        """回归：onnx 落点曾被当成目录前缀拼接，产出 `policy.onnxartifact.json` 这种垃圾名。

        成因是把"元数据前缀"和"onnx 落点"两个概念混成一个参数。现在分开：元数据跟 prefix，
        onnx 跟 onnx_path。
        """

        artifact_id = _produced_artifact_id()
        if artifact_id is None:
            self.skipTest("出库索引里没有 produced 产物")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", Path(tmp) / "bundle", artifact_id=artifact_id)
            paths = [entry["path"] for entry in manifest["entries"]]
            self.assertFalse([path for path in paths if ".onnx" in path and not path.endswith(".onnx")], paths)
            onnx = [path for path in paths if path.endswith(".onnx")]
            self.assertTrue(onnx, paths)
            self.assertTrue(onnx[0].startswith("simulation/policies/"), onnx)

    def test_missing_pack_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                bx.export_bundle(Path(tmp) / "nope.pack.json", Path(tmp) / "bundle")


class VerifyExportTest(unittest.TestCase):
    """verify 的三重判据：内容、角色、幽灵文件。"""

    def _bundle(self, tmp: str) -> Path:
        out = Path(tmp) / "bundle"
        bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", out)
        return out

    def test_missing_manifest_is_not_an_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = bx.verify_export(Path(tmp))
            self.assertFalse(report["ok"])
            self.assertIn("manifest.json", report["problems"][0])

    def test_tampered_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._bundle(tmp)
            target = next(path for path in out.rglob("skill.json"))
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            report = bx.verify_export(out)
            self.assertFalse(report["ok"])
            self.assertTrue(any("sha256" in problem for problem in report["problems"]), report["problems"])

    def test_ghost_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._bundle(tmp)
            (out / "extra.txt").write_text("junk", encoding="utf-8")
            report = bx.verify_export(out)
            self.assertFalse(report["ok"])
            self.assertTrue(any("幽灵文件" in problem for problem in report["problems"]), report["problems"])

    def test_missing_required_role_is_rejected(self):
        """删掉形态文件 ⇒ Bundle 不再具备形态角色，必须红（而不是"少了点东西也还行"）。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = self._bundle(tmp)
            for name in ("contract_legacy_v2.json", "contract.json", "robot_package.json"):
                (out / name).unlink()
            for path in sorted((out / "model").rglob("*"), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            report = bx.verify_export(out)
            self.assertFalse(report["ok"])
            self.assertTrue(any("缺文件" in problem or "必需角色" in problem for problem in report["problems"]), report["problems"])

    def test_bad_schema_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._bundle(tmp)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            manifest["schema_version"] = "whatever-1.0"
            (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            report = bx.verify_export(out)
            self.assertFalse(report["ok"])
            self.assertTrue(any("schema_version" in problem for problem in report["problems"]), report["problems"])

    def test_verify_is_independent_of_export_time_state(self):
        """把导出目录整体拷到别处再验 —— 判据只看磁盘与 manifest，所以照样通过。"""

        import shutil

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            out = self._bundle(tmp)
            moved = Path(other) / "copied"
            shutil.copytree(out, moved)
            self.assertTrue(bx.verify_export(moved)["ok"])


class ScenarioImportTest(unittest.TestCase):
    """H5「Scenario 包可导出/**导入**」的导入半边（此前只有导出）。

    守四条：① 导出→导入**往返一致**（不是"能读个大概"）；② 三种实际会被递过来的形态都认
    （导出目录 / Bundle 内嵌 / 裸 JSON）；③ 完整性被破坏就**拒绝**（从别处拷来的包也要可信）；
    ④ 形态不对时明确报错、不做猜测性兼容；⑤ 落盘默认不覆盖别人的场景。
    """

    def _scenario_file(self, tmp: str) -> Path:
        path = Path(tmp) / "source.json"
        path.write_text(
            json.dumps({"scenario_id": "flat-demo", "map_id": "flat", "mode": "basic"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_round_trip_export_then_import_is_identical(self):
        """往返一致：导入出来的载荷 == 导出时校验过的规范化载荷。"""

        from contracts.scenario_contract import ScenarioContract

        with tempfile.TemporaryDirectory() as tmp:
            source = self._scenario_file(tmp)
            out = Path(tmp) / "pack"
            bx.export_scenario(source, out)
            result = bx.import_scenario(out)
            expected = ScenarioContract(**json.loads(source.read_text(encoding="utf-8"))).to_payload()
            self.assertEqual(expected, result["scenario"], "导出→导入必须逐字段一致")
            self.assertEqual("export_dir", result["form"])
            self.assertEqual("flat-demo", result["scenario_id"])
            self.assertIsNotNone(result["integrity"])
            self.assertTrue(result["integrity"]["ok"])

    def test_bare_json_is_accepted(self):
        """裸场景 JSON 也认（手写/从别处贴来的），此时没有 manifest 可验，如实回 None。"""

        with tempfile.TemporaryDirectory() as tmp:
            result = bx.import_scenario(self._scenario_file(tmp))
            self.assertEqual("bare_json", result["form"])
            self.assertIsNone(result["integrity"])
            self.assertEqual("flat-demo", result["scenario_id"])

    def test_import_accepts_a_bundle_embedded_scenario(self):
        """Bundle 里内嵌的场景（`scenario/scenario.json`，没有自己的 manifest）也能导入。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", out, scenario_path=str(self._scenario_file(tmp)))
            self.assertTrue((out / "scenario" / "scenario.json").is_file(), "Bundle 应内嵌场景")
            result = bx.import_scenario(out)
            self.assertEqual("bundle_embedded", result["form"])
            self.assertEqual("flat-demo", result["scenario_id"])
            # Bundle 的完整性验的是**整包**，比只看场景文件更严
            self.assertEqual("bundle", result["integrity"]["kind"])

    def test_tampered_scenario_pack_is_refused(self):
        """场景文件被改过（sha256 与 manifest 不符）⇒ 拒绝导入，不当成可信场景跑起来。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pack"
            bx.export_scenario(self._scenario_file(tmp), out)
            target = out / "scenario.json"
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["map_id"] = "warehouse"  # 改内容不改 manifest
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                bx.import_scenario(out)
            self.assertIn("完整性", str(ctx.exception))

    def test_non_scenario_export_is_refused_with_reason(self):
        """拿形态包当场景 ⇒ 明确说"里面没有场景"，而不是猜。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "morph"
            bx.export_morphology("zex-w", out)
            with self.assertRaises(ValueError) as ctx:
                bx.import_scenario(out)
            self.assertIn("没有场景", str(ctx.exception))

    def test_unrecognised_source_is_refused(self):
        """两种错**分开报**：路径不存在 ⇒ FileNotFoundError；存在但不是场景 ⇒ 说"认不出"。"""

        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty-dir"
            empty.mkdir()
            with self.assertRaises(ValueError) as ctx:
                bx.import_scenario(empty)
            self.assertIn("认不出", str(ctx.exception))
            with self.assertRaises(FileNotFoundError):
                bx.import_scenario(Path(tmp) / "no-such-dir")

    def test_dest_is_not_clobbered_without_force(self):
        """导入落盘默认不覆盖：静默覆盖别人的场景是不可接受的。"""

        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            bx.export_scenario(self._scenario_file(tmp), pack)
            dest = Path(tmp) / "workspace"
            first = bx.import_scenario(pack, dest=dest)
            self.assertTrue(first["written"].endswith("scenario.json"))
            landed = Path(tmp) / "workspace" / "scenario.json"
            self.assertTrue(landed.is_file())
            with self.assertRaises(FileExistsError):
                bx.import_scenario(pack, dest=dest)
            second = bx.import_scenario(pack, dest=dest, force=True)
            self.assertEqual(first["scenario"], second["scenario"])
            # 落盘的也必须能再过一次契约（导入的是"可用场景"，不是一段 JSON 文本）
            self.assertEqual(second["scenario"], json.loads(landed.read_text(encoding="utf-8")))

    def test_invalid_scenario_is_rejected_by_the_same_gate_as_export(self):
        """非法场景：导入与导出走**同一道闸**（否则"能导出不能导入"这类不对称迟早出现）。"""

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"scenario_id": "Bad Id!"}), encoding="utf-8")
            with self.assertRaises(Exception):
                bx.import_scenario(bad)


if __name__ == "__main__":
    unittest.main()

