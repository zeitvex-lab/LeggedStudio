"""包定位与浏览器包 URL 的**单一来源**守卫（2026-09-19 收口）。

## 这组测试守的是什么

收口前实测取证：同一台机器 ``zex_w``（下划线）在**仿真域能开**、在**部署域 404**，
而 ``zex-w`` 是全仓唯一带连字符的 ``robot_id`` —— 两个域各写了一遍包定位，规则还不同。
浏览器包 URL 也一样：控制面 5 处各拼一遍、离线引导层的 JS 里还有一份跨语言字面量。

所以这里守两件事：

1. **定位规则唯一**：别名归一后各域必须落到同一包根，异常类型与字段稳定
   （控制面靠 ``FileNotFoundError`` 映射 404，CLI 靠 ``robot_id``/``tried`` 组织提示）；
2. **URL 形状唯一**：生成点不得再出现字面量前缀（源码级扫描 + 形状断言），
   否则"改前缀漏一处"会以"策略下载失败"这种无指向的形态炸在前端。
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api_routes import (  # noqa: E402
    BROWSER_PACKAGE_URL_PREFIX,
    browser_package_url,
    browser_package_url_prefix,
)
from backend.package_locator import (  # noqa: E402
    RobotPackageNotFound,
    normalize_robot_id,
    resolve_package_entry,
    resolve_package_root,
    robot_definition,
)
from backend.paths import DATA_DIR_ENV, WORKSPACE_ENV, api_path, data_dir, workspace_root  # noqa: E402
from backend.robot_presets import list_robot_presets  # noqa: E402

#: ``zex-w`` 是全仓唯一带连字符的 robot_id —— 别名归一是否真的生效，靠它证伪。
HYPHENATED_ROBOT_ID = "zex-w"


class PackageLocatorTest(unittest.TestCase):
    """定位规则唯一：别名归一、异常契约、跨域一致。"""

    def test_alias_normalisation_reaches_the_same_root(self) -> None:
        canonical = resolve_package_root(HYPHENATED_ROBOT_ID)
        underscored = resolve_package_root(HYPHENATED_ROBOT_ID.replace("-", "_"))
        self.assertEqual(canonical, underscored)
        self.assertTrue((underscored / "contract.json").is_file())

    def test_normalize_robot_id_folds_case_and_separators(self) -> None:
        self.assertEqual(normalize_robot_id("ZEX-W"), normalize_robot_id("zex_w"))
        self.assertEqual(normalize_robot_id(" unitree_go2 "), "unitree_go2")

    def test_every_preset_resolves_to_a_package_with_contract(self) -> None:
        for item in list_robot_presets():
            robot_id = str(item["robot_id"])
            with self.subTest(robot=robot_id):
                canonical, root, preset = resolve_package_entry(robot_id)
                self.assertEqual(canonical, robot_id)
                self.assertTrue(preset, "登记在册的包必须解析出 preset")
                self.assertTrue((root / "contract.json").is_file(), root)

    def test_missing_package_keeps_the_404_contract(self) -> None:
        """控制面靠 ``FileNotFoundError`` 把这一类映射 404；CLI 靠字段组织提示。"""

        with self.assertRaises(FileNotFoundError):
            resolve_package_root("no_such_robot_at_all")
        with self.assertRaises(RobotPackageNotFound) as ctx:
            resolve_package_root("no_such_robot_at_all")
        exc = ctx.exception
        self.assertEqual(exc.robot_id, "no_such_robot_at_all")
        self.assertFalse(exc.preset_resolved, "查无此机 ≠ 安装损坏")
        self.assertTrue(exc.tried, "必须带上尝试过的候选路径，否则排查无从下手")

    def test_deploy_and_simulation_agree(self) -> None:
        """本模块存在的**唯一理由**：两个域问"包根在哪"必须得到同一个答案。"""

        from backend.deploy_pack import resolve_package_root as deploy_root
        from backend.simulation_browser import browser_package

        for probe in ("unitree_go2", HYPHENATED_ROBOT_ID, HYPHENATED_ROBOT_ID.replace("-", "_")):
            with self.subTest(probe=probe):
                self.assertEqual(deploy_root(probe), browser_package(probe)[0])

    def test_simulation_domain_keeps_its_own_precondition(self) -> None:
        """域特有前置仍在：浏览器要 MJCF，缺模型即 404（不能被共用定位"抹平"）。"""

        from fastapi import HTTPException
        from backend.simulation_browser import browser_package

        with self.assertRaises(HTTPException) as ctx:
            browser_package("no_such_robot_at_all")
        self.assertEqual(ctx.exception.status_code, 404)


class BrowserPackageUrlSingleSourceTest(unittest.TestCase):
    """URL 形状唯一：只有一个生成点，且形状与该约定一致。"""

    def test_url_shape_and_backslash_normalisation(self) -> None:
        expected = f"{BROWSER_PACKAGE_URL_PREFIX}/unitree_go2/simulation/policies/x.onnx"
        self.assertEqual(expected, browser_package_url("unitree_go2", "simulation/policies/x.onnx"))
        # 声明里可能是 Windows 手写路径：不归一会让浏览器 404，而报错只说"策略下载失败"
        self.assertEqual(expected, browser_package_url("unitree_go2", r"simulation\policies\x.onnx"))
        self.assertEqual(expected, browser_package_url("unitree_go2", "/simulation/policies/x.onnx"))

    def test_prefix_helper_matches_concat(self) -> None:
        prefix = browser_package_url_prefix("zex-w")
        self.assertTrue(prefix.endswith("/"))
        self.assertTrue(browser_package_url("zex-w", "a.onnx").startswith(prefix))

    def test_no_literal_prefix_outside_the_contract_module(self) -> None:
        """源码级防回归：**产品代码**里除 ``backend/api_routes.py`` 外不许再出现前缀字面量。

        离线引导层的 JS 正则也算生成点 —— 它现在是**注入**的（``bundle_export``），
        所以这一条扫描对 Python 与内嵌 JS 一起有效。

        测试文件**刻意不参与扫描**：测试里显式写 URL 形状是有意的第二见证 ——
        前缀若被静默改坏，产品侧会一致地跟着改（都引用常量），只有测试里的字面量会红。
        """

        needle = f'"{BROWSER_PACKAGE_URL_PREFIX}'
        single = f"'{BROWSER_PACKAGE_URL_PREFIX}"
        offenders: list[str] = []
        for base in ("backend", "tools", "scripts", "adapters"):
            for path in sorted((ROOT / base).rglob("*.py")):
                if path.name == "api_routes.py" or path.name.startswith("test_"):
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if needle in text or single in text:
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders, f"URL 前缀字面量应只在 backend/api_routes.py：{offenders}")

    def test_offline_bootstrap_reuses_the_prefix(self) -> None:
        """离线引导层（打包给用户的 JS）必须与在线形状一致，否则包内文件必 404。"""

        from backend.bundle_export import bootstrap_js

        js = bootstrap_js({"presets": [], "configs": {}, "robot": "zex-w"})
        line = next(item for item in js.splitlines() if "assetMatch" in item and "match" in item)
        self.assertIn(BROWSER_PACKAGE_URL_PREFIX.replace("/", r"\/"), line)
        self.assertNotIn(BROWSER_PACKAGE_URL_PREFIX, line)  # 只允许转义后的形式（JS 正则字面量）


class WorkspaceRootSingleSourceTest(unittest.TestCase):
    """工作区根解析**唯一实现**（收口前 7 份实现、strip/resolve 规则不一致）。"""

    def test_every_module_resolves_the_same_root(self) -> None:
        """带空白的写法是真实踩坑形态：此前一部分模块 strip 了、一部分没有。"""

        from backend import bundle_export, model_api, project_api, quality_matrix, robot_packages, settings_api
        from scripts.legged_studio_cli import _workspace_root as cli_root

        with mock.patch.dict(os.environ, {WORKSPACE_ENV: "  /tmp/unified-ws  "}):
            values = {
                "paths": workspace_root(),
                "model_api": model_api._workspace_root(),
                "project_api": project_api._workspace_root(),
                "robot_packages": robot_packages._workspace_root(),
                "settings_api": settings_api._workspace_root(),
                "bundle_export": bundle_export._workspace_root(),
                "quality_matrix": quality_matrix._workspace_root(),
                "cli": cli_root(None),
            }
        resolved = {name: str(value) for name, value in values.items()}
        self.assertEqual(1, len(set(resolved.values())), f"工作区根解析仍有分叉：{resolved}")
        self.assertEqual(Path("/tmp/unified-ws"), values["paths"])

    def test_relative_env_is_absolutised(self) -> None:
        """相对路径形态必须绝对化：否则"同一根"会以多个字符串出现，缓存键与前缀判断失配。"""

        with mock.patch.dict(os.environ, {WORKSPACE_ENV: "relative-ws"}):
            root = workspace_root()
        self.assertTrue(root.is_absolute(), root)

    def test_blank_env_falls_back_to_repo_workspace(self) -> None:
        with mock.patch.dict(os.environ, {WORKSPACE_ENV: "   "}):
            self.assertEqual(ROOT / "workspace", workspace_root())

    def test_cli_flag_still_wins(self) -> None:
        from scripts.legged_studio_cli import _workspace_root as cli_root

        with mock.patch.dict(os.environ, {WORKSPACE_ENV: "/tmp/env-ws"}):
            self.assertEqual(Path("/tmp/flag-ws"), cli_root("/tmp/flag-ws"))

    def test_no_second_implementation_in_product_code(self) -> None:
        """源码级防回归：产品代码里只允许 ``backend/paths.py`` **读取**这两个环境变量。

        「写环境变量」（CLI 把 ``--workspace`` 同步进去给下游看）是另一回事，不在此列。
        数据目录同理：解析规则（strip → expanduser → 绝对化）只有一处，
        **默认值**由调用方给（它表达"这类数据的家在哪儿"，本就可能不同）。
        """

        read_patterns = (
            re.compile(rf'os\.environ\.get\(\s*["\'](?:{WORKSPACE_ENV}|{DATA_DIR_ENV})["\']'),
            re.compile(rf'os\.environ\[\s*["\'](?:{WORKSPACE_ENV}|{DATA_DIR_ENV})["\']\s*\]\.'),
        )
        offenders: list[str] = []
        for base in ("backend", "tools", "scripts", "adapters"):
            for path in sorted((ROOT / base).rglob("*.py")):
                if path.name in {"paths.py"} or path.name.startswith("test_"):
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if any(pattern.search(text) for pattern in read_patterns):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders, f"路径约定解析应只在 backend/paths.py：{offenders}")

    def test_data_dir_shares_the_rule_and_keeps_defaults_explicit(self) -> None:
        """数据目录：**规则**唯一（strip → expanduser → 绝对化），**默认值**由调用方给。"""

        with mock.patch.dict(os.environ, {DATA_DIR_ENV: "  ~/data-ws  "}):
            self.assertEqual(Path.home() / "data-ws", data_dir())
        with mock.patch.dict(os.environ, {DATA_DIR_ENV: "   "}):
            self.assertEqual(ROOT / "workspace", data_dir(), "空值回落工作区根")
            self.assertEqual(Path("/tmp/episodes"), data_dir(default=Path("/tmp/episodes")))
        with mock.patch.dict(os.environ, {DATA_DIR_ENV: "relative-dir"}):
            self.assertTrue(data_dir().is_absolute(), "相对值必须绝对化")

    def test_api_path_is_repo_relative_and_falls_back_to_absolute(self) -> None:
        """仓库相对 posix 路径：仓内给相对、仓外退回绝对（此前两处逐字相同的实现）。"""

        self.assertEqual("assets/robots", api_path(ROOT / "assets" / "robots"))
        outside = Path(tempfile.gettempdir()) / "outside.json"
        self.assertEqual(outside.as_posix(), api_path(outside))
        self.assertNotIn("\\", api_path(ROOT / "assets"))


class RobotDefinitionLookupTest(unittest.TestCase):
    """``robot_definition`` 的反查：工作区包 + 尊重 ``LEGGED_STUDIO_WORKSPACE``。

    取证：该反查此前自带在 ``simulation_api`` 里，硬编码 ``<repo>/workspace/packages`` ——
    多实例 / e2e 测试把工作区指到别处时，会话入口会去错的目录找包（等价于"包不存在"）。
    """

    def _make_workspace_package(self, root: Path, robot_id: str) -> Path:
        package = root / "packages" / f"{robot_id}_imported"
        package.mkdir(parents=True)
        (package / "contract_legacy_v2.json").write_text(
            json.dumps({
                "schema_version": "robot-contract-2.0",
                "robot_id": robot_id,
                "family": "Acme",
                "urdf": {"path": "model/robot.xml"},
            }),
            encoding="utf-8",
        )
        (package / "robot_package.json").write_text(json.dumps({"package_id": robot_id}), encoding="utf-8")
        return package

    def test_workspace_package_is_found_through_the_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._make_workspace_package(Path(tmp), "acme_quadruped")
            with mock.patch.dict(os.environ, {WORKSPACE_ENV: tmp}):
                found = robot_definition("acme_quadruped")
        self.assertIsNotNone(found, "工作区包必须能被反查到（此前硬编码 <repo>/workspace 会漏）")
        self.assertEqual("Acme", found["family"])
        # 与 preset 分支同口径：绝对路径（相对路径 cwd 一变就错）
        self.assertTrue(Path(found["asset_path"]).is_absolute(), found["asset_path"])
        self.assertTrue(found["asset_path"].endswith("model/robot.xml"), found["asset_path"])

    def test_registered_package_still_wins(self) -> None:
        found = robot_definition("unitree_go2")
        self.assertIsNotNone(found)
        self.assertEqual("unitree_go2", found["robot_id"])

    def test_unknown_robot_is_quietly_none(self) -> None:
        """quiet 是刻意的：会话可以不靠包建（请求自带 contract），调用方决定 404 措辞。"""

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {WORKSPACE_ENV: tmp}):
                self.assertIsNone(robot_definition("no_such_robot_at_all"))

    def test_alias_input_reaches_the_underscored_workspace_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._make_workspace_package(Path(tmp), "acme-quadruped")
            with mock.patch.dict(os.environ, {WORKSPACE_ENV: tmp}):
                found = robot_definition("acme_quadruped")
        self.assertIsNotNone(found, "下划线写法应命中间名目录（别名归一）")


if __name__ == "__main__":
    unittest.main()
