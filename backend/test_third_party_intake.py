"""第三方包「导入 → 校验 → 进索引」**全绿演示** + 反例（Phase 8 第二刀）。

`docs/plugin-protocol.md` 讲的是"三步接入"，本文件把它变成**可执行**的演示：示范包放在
`docs/examples/third_party/` 下（**不进产品面**——面板 `desktop:false`、资源包只在临时目录
里进索引、门禁只跑脚本），测试把它们"导入"到临时工作区，再用**产品同款装载器**走
"校验 → 进索引"，并逐条验证反例被拒。

口径（**不另写一条链**）：

* 面板插件 → `backend.panel_registry.load_panels` + `backend.cli_panels.resolve_provider`
  + `render_navigation`（产品三面投影用的就是这几个）；
* 资源包 → `backend.resource_packs.load_index / load_pack / validate_pack`
  （K4：清单是权威——文件在但没登记 = 未注册；登记了却不存在 = 报错）；
* 第三方门禁 → `backend.verify_catalog.load_catalog / catalog_problems`（控制面目录访问层）。

三类可扩展面各一个示范包 = Phase 8 的"示范包 3 个"；本文件 = "导入→校验→进索引 全绿演示"。
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXAMPLES = ROOT / "docs" / "examples" / "third_party"


def _temp_dir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


class PanelPluginIntakeTest(unittest.TestCase):
    """面板插件：**清单目录即索引**（导入 = 放进去；校验 = 装载器；进索引 = 三面投影）。"""

    @classmethod
    def setUpClass(cls):
        # 第三方实现放在**自己的目录**里，产品侧只多一个 sys.path 条目 —— 协议承诺的
        # "provider 可指向任何可导入模块"要在这里被真 importlib 解析验证。
        cls.provider_dir = str(EXAMPLES / "panel_hello")
        if cls.provider_dir not in sys.path:
            sys.path.insert(0, cls.provider_dir)

    @classmethod
    def tearDownClass(cls):
        while cls.provider_dir in sys.path:
            sys.path.remove(cls.provider_dir)

    def _import_demo(self) -> Path:
        tmp = _temp_dir("panel_intake_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copy(EXAMPLES / "panel_hello" / "panel_hello.json", tmp / "panel_hello.json")
        return tmp

    def test_intake_three_steps_all_green(self):
        from backend.cli_panels import resolve_provider
        from backend.panel_registry import load_panels, render_navigation

        directory = self._import_demo()
        panels = load_panels(directory)  # 校验：schema / seam / id=文件名 / provides 含自身 / entry
        self.assertEqual(["panel_hello"], [item["id"] for item in panels])
        panel = panels[0]
        self.assertIn("panel/panel_hello", panel["provides"])
        for key in ("cli", "home_card"):
            spec = panel[key]["provider"]
            self.assertRegex(spec, r"^[\w.]+:[\w]+$", "provider 必须是真 module:attr")
            payload = resolve_provider(spec)()  # 进索引：三面投影同一 provider，真解析
            self.assertIsInstance(payload, dict)
            self.assertIn("greeting", payload)
        self.assertEqual(
            [], render_navigation(panels), "desktop:false ⇒ 示范包不进导航（不许污染产品面）"
        )

    def test_negative_broken_manifests_are_rejected(self):
        from backend.panel_registry import PanelRegistryError, load_panels

        good = json.loads((EXAMPLES / "panel_hello" / "panel_hello.json").read_text(encoding="utf-8"))
        cases = {
            "schema 不在册": {**good, "schema": "legged-plugin-9.9"},
            "seam 不在册": {**good, "seam": "skill"},
            "provides 不含自身": {**good, "provides": ["panel/other"]},
            "缺 entry": {key: value for key, value in good.items() if key != "entry"},
        }
        for name, payload in cases.items():
            with self.subTest(case=name):
                tmp = _temp_dir("panel_bad_")
                self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
                (tmp / "panel_hello.json").write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                with self.assertRaises(PanelRegistryError):
                    load_panels(tmp)

    def test_negative_id_must_equal_file_name(self):
        from backend.panel_registry import PanelRegistryError, load_panels

        tmp = _temp_dir("panel_id_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        good = json.loads((EXAMPLES / "panel_hello" / "panel_hello.json").read_text(encoding="utf-8"))
        (tmp / "renamed.json").write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(PanelRegistryError):
            load_panels(tmp)

    def test_negative_unresolvable_provider_is_rejected(self):
        from backend.cli_panels import resolve_provider

        with self.assertRaises(Exception):  # noqa: B017 —— importlib 失败或包装后抛出都算
            resolve_provider("no_such_module_xyz:no_such_attr")()


class ResourcePackIntakeTest(unittest.TestCase):
    """资源包：**清单是权威**（K4）。导出/校验/索引全走产品装载器。"""

    def _import_demo(self) -> Path:
        tmp = _temp_dir("pack_intake_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for name in ("index.json", "hello_pack.json"):
            shutil.copy(EXAMPLES / "resource_pack" / name, tmp / name)
        return tmp

    def test_intake_three_steps_all_green(self):
        from backend.resource_packs import load_index, load_pack, validate_pack

        directory = self._import_demo()
        index = load_index(directory)  # 进索引：清单登记
        self.assertEqual(["hello_pack"], [item["pack_id"] for item in index["packs"]])
        pack = load_pack("hello_pack", packs_dir=directory)  # 装载
        self.assertEqual("resource-pack-1.0", pack["schema"])
        self.assertEqual([], validate_pack(pack)["problems"], "示范包必须过引用与宽度校验")

    def test_unlisted_file_is_not_registered(self):
        """K4：文件在但没登记 = 未注册（清单说了算，不扫目录）。"""
        from backend.resource_packs import load_index

        directory = self._import_demo()
        (directory / "sneaky.json").write_text(
            json.dumps({"schema": "resource-pack-1.0", "pack_id": "sneaky"}, ensure_ascii=False),
            encoding="utf-8",
        )
        index = load_index(directory)
        self.assertEqual(["hello_pack"], [item["pack_id"] for item in index["packs"]])

    def test_negative_bogus_mounts_and_width_drift(self):
        from backend.resource_packs import validate_pack

        pack = json.loads((EXAMPLES / "resource_pack" / "hello_pack.json").read_text(encoding="utf-8"))
        bogus = {**pack, "mounts": {**pack["mounts"], "observations": ["no_such_obs"]}}
        self.assertTrue(validate_pack(bogus)["problems"], "引用不存在的观测项必须判红")
        drift = {**pack, "obs_dim_delta": pack["obs_dim_delta"] + 1}
        self.assertTrue(validate_pack(drift)["problems"], "obs_dim_delta 与所挂宽度不符必须判红")


class ThirdPartyVerifyGateTest(unittest.TestCase):
    """第三方门禁：**目录即索引**（形状由控制面校验），判据 = 退出码。"""

    def _entry(self) -> dict:
        return json.loads((EXAMPLES / "verify_gate" / "verify_entry.json").read_text(encoding="utf-8"))

    def test_entry_shape_and_script_runs(self):
        from backend.verify_catalog import catalog_problems, load_catalog, planned_commands

        catalog = load_catalog(EXAMPLES / "verify_gate" / "verify_entry.json")
        self.assertEqual([], catalog_problems(catalog), "第三方门禁声明必须过控制面形状校验")
        commands = planned_commands(catalog)  # env 留空 ⇒ 属 planned（可进 unit-tests 段）
        self.assertEqual(1, len(commands))
        result = subprocess.run(
            shlex.split(commands[0]), capture_output=True, text=True, cwd=str(ROOT)
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_negative_out_of_vocabulary_seam_and_env(self):
        from backend.verify_catalog import catalog_problems

        entry = self._entry()
        for field, value in (("seam", "不存在的seam"), ("env", "不存在的env")):
            with self.subTest(field=field):
                broken = {**entry, "gates": [{**entry["gates"][0], field: value}]}
                self.assertTrue(
                    catalog_problems(broken), f"{field} 越出闭合词汇必须判红（第三方不许自造枚举）"
                )


if __name__ == "__main__":
    unittest.main()
