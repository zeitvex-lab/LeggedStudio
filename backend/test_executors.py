"""H2：Executor 抽象的三条锁。

1. **能力声明必须挂得住锚点** —— `backend/executors.py` 里每条能力都带 `route:` / `param:` /
   `dom:` 标记，这里回真源核对：服务端路由要在 `app.openapi()` 里，浏览器 URL 参数要在
   `web/sim2sim/app.js` 的 `PAGE_PARAMS` 里，页面控件要在 `web/sim2sim/index.html` 里。
   **这条是本模块存在的理由**：能力矩阵最容易变成一页漂亮但过期的表，锚点让它改成"改代码即红"。
2. **契约取值必须表态**：`ScenarioContract.command_source` 的每个合法取值，要么至少一个执行器支持，
   要么出现在 `UNSUPPORTED_CONTRACT_OPTIONS` 里并写明理由 —— 不许"契约支持、却没人能跑"悄悄存在。
3. **选择是纯函数且 fail-closed**：prefer 落选要说原因；没人能跑要拒绝（`ok=False` + 理由），
   而不是随便挑一个跑跑看。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import get_args

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import executors  # noqa: E402

APP_JS = ROOT / "web" / "sim2sim" / "app.js"
INDEX_HTML = ROOT / "web" / "sim2sim" / "index.html"


def _anchors(prefix: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for target in executors.EXECUTORS:
        for anchor in target["anchors"]:
            if anchor.startswith(prefix):
                found.append((target["id"], anchor[len(prefix):]))
    return found


class AnchorTest(unittest.TestCase):
    def test_server_route_anchors_exist_in_openapi(self):
        from backend.api_complete import app

        paths = set(app.openapi()["paths"])
        anchors = _anchors("route:")
        self.assertGreaterEqual(len(anchors), 3, f"服务端锚点太少：{anchors}")
        for executor_id, path in anchors:
            self.assertIn(path, paths, f"{executor_id} 声明的路由 {path} 不在 app.openapi() 里")

    def test_browser_url_param_anchors_exist(self):
        source = APP_JS.read_text(encoding="utf-8")
        anchors = _anchors("param:")
        self.assertGreaterEqual(len(anchors), 5, f"浏览器参数锚点太少：{anchors}")
        for executor_id, name in anchors:
            self.assertTrue(
                f'PAGE_PARAMS.get("{name}")' in source or f'PAGE_PARAMS.has("{name}")' in source,
                f"{executor_id} 声明的 URL 参数 {name!r} 在 app.js 里没被读过（参数名写错=静默失效）",
            )

    def test_browser_dom_anchors_exist(self):
        source = INDEX_HTML.read_text(encoding="utf-8")
        anchors = _anchors("dom:")
        self.assertGreaterEqual(len(anchors), 2, f"页面控件锚点太少：{anchors}")
        for executor_id, element_id in anchors:
            self.assertIn(f'id="{element_id}"', source, f"{executor_id} 声明的控件 #{element_id} 不在页面里")


class ContractCoverageTest(unittest.TestCase):
    def test_declared_sources_match_the_contract_literal(self):
        """`CONTRACT_COMMAND_SOURCES` 与契约的 Literal **同源核对**（契约新增取值而这里没跟 ⇒ 红）。"""

        from contracts.scenario_contract import ScenarioContract

        annotation = ScenarioContract.model_fields["command_source"].annotation
        self.assertEqual(set(executors.CONTRACT_COMMAND_SOURCES), set(get_args(annotation)))

    def test_every_contract_option_is_supported_or_explicitly_unsupported(self):
        supported: set[str] = set()
        for target in executors.EXECUTORS:
            supported |= set(target["supports"]["command_sources"])
        declared_unsupported = {
            item["value"] for item in executors.UNSUPPORTED_CONTRACT_OPTIONS if item["field"] == "command_source"
        }
        for value in executors.CONTRACT_COMMAND_SOURCES:
            self.assertTrue(
                value in supported or value in declared_unsupported,
                f"契约允许 command_source={value!r}，但既没有执行器支持、也没登记为不支持"
                "（契约支持但没人能跑，不能被当成支持）",
            )
            self.assertFalse(
                value in supported and value in declared_unsupported,
                f"{value!r} 同时被声明为支持与不支持，自相矛盾",
            )
        for item in executors.UNSUPPORTED_CONTRACT_OPTIONS:
            self.assertGreater(len(item["why"]), 10, f"{item['value']!r} 的「为什么不支持」太短，等于没说")


class SelectExecutorTest(unittest.TestCase):
    def test_policy_scenario_goes_to_the_browser(self):
        """无偏好时：策略驱动 ⇒ 浏览器（唯一能做策略推理的）。"""

        result = executors.select_executor({"command_source": "policy", "perception": {"route": "external"}})
        self.assertTrue(result["ok"], result)
        self.assertEqual("browser_wasm", result["executor"]["id"])

    def test_script_scenario_goes_to_the_server(self):
        result = executors.select_executor({"command_source": "script"})
        self.assertTrue(result["ok"], result)
        self.assertEqual("server_mujoco", result["executor"]["id"])

    def test_perception_command_source_is_refused_with_reason(self):
        """两个执行器都不支持的取值 ⇒ 拒绝 + 说清是谁缺什么（而不是随便挑一个）。"""

        result = executors.select_executor({"command_source": "perception", "waypoints": [{"x": 0, "y": 0}]})
        self.assertFalse(result["ok"], result)
        self.assertIsNone(result["executor"])
        self.assertIn("没有任何执行器能跑这份场景", result["reasons"])
        for entry in result["considered"]:
            self.assertTrue(entry["gaps"], f"{entry['id']} 应报出缺口")

    def test_prefer_is_honoured_when_supported_and_explained_when_not(self):
        honoured = executors.select_executor({"command_source": "planner"}, prefer="server_mujoco")
        self.assertEqual("server_mujoco", honoured["executor"]["id"])
        self.assertEqual([], honoured["reasons"])

        fell_back = executors.select_executor({"command_source": "policy"}, prefer="server_mujoco")
        self.assertEqual("browser_wasm", fell_back["executor"]["id"])
        self.assertTrue(any("prefer" in reason for reason in fell_back["reasons"]), fell_back["reasons"])

    def test_require_filters_by_capability(self):
        """额外硬要求（如要离屏帧）⇒ 只有服务端能做。"""

        result = executors.select_executor({"command_source": "planner"}, require=("offscreen_render",))
        self.assertTrue(result["ok"], result)
        self.assertEqual("server_mujoco", result["executor"]["id"])

        none = executors.select_executor({"command_source": "policy"}, require=("offscreen_render",))
        self.assertFalse(none["ok"], none)

    def test_unknown_executor_is_rejected(self):
        with self.assertRaises(KeyError):
            executors.select_executor({"command_source": "policy"}, prefer="no_such_executor")

    def test_describe_shape(self):
        described = executors.describe()
        self.assertEqual("executor-matrix-1.0", described["schema"])
        self.assertEqual({"server_mujoco", "browser_wasm"}, {item["id"] for item in described["executors"]})


class ExecutorMatrixHttpSurfaceTest(unittest.TestCase):
    """能力矩阵必须**有 HTTP 出口**（B1）：否则它只是测试 fixture。

    防的回归：`select_executor` / `describe` 曾经零生产调用方——"契约允许但没人能跑"
    在产品上完全看不见。现在场景编辑器与仿真页都经 `GET /api/simulation/executors`
    读它，路由没了这两处立刻退化成"用镜像兜底"（功能还在，但真值源丢了）。
    """

    def test_route_is_registered_and_matches_describe(self):
        from fastapi import FastAPI

        from backend.api_complete import app as complete_app

        paths = complete_app.openapi()["paths"]
        self.assertIn("/api/simulation/executors", paths, "能力矩阵没有 HTTP 出口（B1 回潮）")

        described = executors.describe()
        for item in described["executors"]:
            for anchor in item["anchors"]:
                kind, _, value = anchor.partition(":")
                if kind == "route":
                    self.assertIn(value, paths, f"{item['id']} 的锚点路由不在 openapi 里：{value}")

    def test_browser_mirror_matches_the_matrix(self):
        """跨语言守卫：前端镜像（接口不可达时兜底）必须与 Python 矩阵逐值一致。

        镜像是 `web/sim2sim/scenario_run.js` 的 `EXECUTOR_COMMAND_SOURCES`。
        两边漂移的后果：页面上说"这个来源能跑"而矩阵说不能（或反过来）——而这种分歧
        没有任何运行时会报错。
        """

        import re

        js = (ROOT / "web" / "sim2sim" / "scenario_run.js").read_text(encoding="utf-8")
        block = js[js.index("export const EXECUTOR_COMMAND_SOURCES"):]
        block = block[:block.index("};")]
        for item in executors.EXECUTORS:
            match = re.search(rf'{item["id"]}:\s*\[([^\]]*)\]', block)
            self.assertIsNotNone(match, f"JS 镜像里没有 {item['id']}")
            mirrored = [part.strip().strip('"') for part in match.group(1).split(",") if part.strip()]
            self.assertEqual(
                list(item["supports"]["command_sources"]), mirrored,
                f"{item['id']} 的指令来源镜像与矩阵不一致",
            )


if __name__ == "__main__":
    unittest.main()
