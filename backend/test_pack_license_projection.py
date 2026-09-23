"""I5 后半：许可取证层 → 包清单的投影与对账。

守四件事：
1. **8 份包清单都带 license 块**（family-arch 收敛后的 8 机型），且与
   `registry/licenses.json` 的取证逐项一致；
2. **非商用披露机制仍生效**：注入 CC-BY-NC 依据 ⇒ 再分发口径必须投影为
   `restricted-noncommercial`，清单写 allowed 会被判红（保留机型目前**没有**非商用
   上游——原 g1 的 CC-BY-NC 用例已随包出库，故用派生数据副本等价构造，不碰仓库真实 pack）；
3. **取不到证据时是 unknown，绝不默认 allowed**（zex-w 一条许可依据都取不到）；
4. **漂移会判红**：清单被手改成别的口径 ⇒ 对账失败（这是"缺许可不得静默"的落地点）。
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import audit_licenses as al  # noqa: E402


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        self.derived = al.derive()

    def test_every_manifest_carries_license_matching_evidence(self):
        problems = al.audit_pack_manifests(self.derived)
        self.assertEqual([], problems)

    def test_noncommercial_upstream_is_disclosed(self):
        """非商用上游 ⇒ 再分发口径必须是"受限"（restricted-noncommercial），不能写成 allowed。

        family-arch 收敛（2026-09）后保留的 8 机型**均无非商用上游**（原 unitree_g1 的
        CC-BY-NC-4.0 上游已随包出库）⇒ 按等价构造验证机制本身：在 `derive()` 结果的
        **派生副本**上注入一条 CC-BY-NC 依据（纯内存 fixture，不碰 registry 与 packs）。
        """

        derived = copy.deepcopy(self.derived)
        derived["unitree_b2"]["components"].append({
            "root": "00_resources/__fixture_nc_upstream",
            "path": "00_resources/__fixture_nc_upstream/LICENSE",
            "sha256": "0" * 64,
            "spdx": "CC-BY-NC-4.0",
            "name": "Creative Commons Attribution-NonCommercial 4.0（fixture 注入）",
            "evidence_files": 1,
        })
        projection = al.project_license("unitree_b2", derived["unitree_b2"])
        self.assertEqual("restricted-noncommercial", projection["redistribution"])
        # 投影口径与仓库真实清单（allowed）不同 ⇒ 对账必须判红，不许静默
        problems = al.audit_pack_manifests(derived)
        self.assertTrue(
            any("unitree_b2" in item and "redistribution" in item for item in problems), problems
        )

    def test_unknown_never_defaults_to_allowed(self):
        """**取不到证据就是 unknown** —— 给它一个 allowed 是假话。zex-w 一条许可依据都取不到。"""

        projection = al.project_license("zex-w", self.derived["zex-w"])
        self.assertEqual("unknown", projection["redistribution"])
        self.assertEqual([], projection["components"], "zex-w 确实没有可主张的许可依据")
        self.assertTrue(projection["unresolved"], "未取证必须如实披露缺口")

    def test_missing_registry_entry_is_unknown_with_reason(self):
        """注册表里没有的包 ⇒ unknown + 说明原因（不许悄悄给个 allowed）。"""

        projection = al.project_license("unknown_robot", None)
        self.assertEqual("unknown", projection["redistribution"])
        self.assertIn("不在 registry/licenses.json", projection["unresolved"][0]["reason"])

    def test_noncommercial_detection_covers_nc_family(self):
        """NC 族判定要宽：漏一个就是"悄悄允许商用"，比多判一个严重。"""

        for spdx in ("CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "CC-BY-NC-ND-4.0", "CC-BY-NC"):
            self.assertTrue(al._is_noncommercial(spdx), spdx)
        for spdx in ("Apache-2.0", "MIT", "BSD-3-Clause", "CC-BY-4.0", None):
            self.assertFalse(al._is_noncommercial(spdx), spdx)


class DriftDetectionTest(unittest.TestCase):
    """漂移必须判红 —— 否则清单会慢慢变成"对外说错话"的地方。

    family-arch 收敛（2026-09）后原靶子 unitree_g1 已出库，重锚到保留机型
    unitree_b2；"受限口径被写成 allowed"这一最危险改法用**派生副本注入 NC 依据**
    等价构造（不碰仓库真实 pack）。
    """

    def _problems_with_manifest(self, mutate, derived=None) -> list[str]:
        derived = derived if derived is not None else al.derive()
        source = json.loads((ROOT / "packs/unitree_b2.pack.json").read_text(encoding="utf-8"))
        mutated = mutate(copy.deepcopy(source))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unitree_b2.pack.json"
            path.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(al, "packs_dir", lambda: Path(tmp)):
                return al.audit_pack_manifests(derived)

    def test_redistribution_drift_is_caught(self):
        """把受限口径改成 allowed（最危险的一种改法：对外变成"随便用"）⇒ 判红。"""

        derived = copy.deepcopy(al.derive())
        derived["unitree_b2"]["components"].append({
            "root": "00_resources/__fixture_nc_upstream",
            "path": "00_resources/__fixture_nc_upstream/LICENSE",
            "sha256": "0" * 64,
            "spdx": "CC-BY-NC-4.0",
            "name": "Creative Commons Attribution-NonCommercial 4.0（fixture 注入）",
            "evidence_files": 1,
        })
        expected = al.project_license("unitree_b2", derived["unitree_b2"])
        self.assertEqual("restricted-noncommercial", expected["redistribution"], "注入前提不成立")
        # 仓库真实清单写的是 allowed ⇒ 与注入后的取证层不一致，必须判红
        problems = self._problems_with_manifest(lambda pack: pack, derived)
        self.assertTrue(any("redistribution" in item for item in problems), problems)

    def test_missing_license_block_is_caught(self):
        def mutate(pack):
            pack.pop("license", None)
            return pack

        problems = self._problems_with_manifest(mutate)
        self.assertTrue(any("缺 license 块" in item for item in problems), problems)

    def test_component_count_drift_is_caught(self):
        def mutate(pack):
            pack["license"]["components"] = pack["license"]["components"][:1]
            return pack

        problems = self._problems_with_manifest(mutate)
        self.assertTrue(any("components 条数" in item for item in problems), problems)


class SchemaDeclarationTest(unittest.TestCase):
    def test_pack_schema_declares_license_via_evidence(self):
        """schema 有类型化声明，且是**从取证层派生的字段**（不是随手加的）。"""

        schema = json.loads((ROOT / "contracts/schema/capability-pack-1.0.schema.json").read_text(encoding="utf-8"))
        license_prop = schema["properties"]["license"]
        self.assertEqual(["allowed", "restricted-noncommercial", "unknown"],
                         license_prop["properties"]["redistribution"]["enum"])
        self.assertIn("绝不默认 allowed", license_prop["description"])

    def test_pack_catalog_knows_license_is_declared(self):
        """pack_catalog 的硬编码字段表必须认识 license（否则每份包都刷无意义告警）。"""

        source = (ROOT / "backend/pack_catalog.py").read_text(encoding="utf-8")
        unknown_set = source.split("unknown = sorted(set(pack) - {")[1].split("}")[0]
        self.assertIn('"license"', unknown_set, "license 已进 schema，硬编码字段表也要同步")


class ScaffoldDeclaresNothingTest(unittest.TestCase):
    """脚手架**不替包作者主张许可**。

    原实现给新包硬写 ``{"spdx": "MIT", "redistribution": "allowed"}`` —— 那是
    "我们核验过你可以再分发"的声明，而实际上谁都没核验过。这一条把它钉住。
    """

    def test_scaffolded_manifest_declares_unknown_license(self):
        from backend import plugin_protocol

        with tempfile.TemporaryDirectory() as tmp:
            # scaffold_package 会在 target_dir 下再套一层 package_id，用返回值定位更稳
            created = plugin_protocol.scaffold_package(Path(tmp), "brand_new_robot")
            manifest_path = Path(created) / "robot_package.json"
            self.assertTrue(manifest_path.is_file(), "脚手架产物里应有 robot_package.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            license_block = manifest["license"]
            self.assertIsNone(license_block["spdx"], "不许替作者写一个 SPDX")
            self.assertEqual("unknown", license_block["redistribution"],
                             "未声明的再分发口径必须如实写 unknown")
            self.assertEqual({"spdx", "source", "redistribution"}, set(license_block),
                             "robot-package-1.1 要求的三个键都要在")


if __name__ == "__main__":
    unittest.main()
