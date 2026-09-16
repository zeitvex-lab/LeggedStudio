"""I4：Bundle 内置离线播放器（"无本仓库机器可打开试玩"）。

## 这组测试守的是什么

`web/sim2sim/app.js` 启动时要问后端两件事（`GET /api/robots/presets` 与
`GET /api/simulation/browser-config/<robot>`），离线机器上没后端。补的做法是**引导层**：

* **配置形状仍由后端产出**（`simulation_api.browser_simulation_config`），只把 URL 换成本地相对路径
  —— 不另写一套"离线版配置形状"，否则在线页面与离线包必然漂移；
* 引导层必须在 app.js **之前**加载（否则拦不住启动时的请求）；
* 页面必须经 HTTP 打开（`file://` 下 fetch/模块/wasm 会被浏览器拦），所以随包给 stdlib 的
  `serve.py` 并补 `.wasm`/`.mjs` 的 MIME。

这里钉住的是"**离线能不能起得来**"这条链上可自动化的部分：配置本地化、引导层位置、
manifest 自洽（同一路径不许出现两条条目）、播放器缺件必红。
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


class OfflinePayloadTest(unittest.TestCase):
    def test_config_shape_comes_from_the_backend_builder(self):
        """离线配置的**形状**必须与在线一致（字段来自 `browser_simulation_config`）。"""

        payload = bx.offline_payload("zex-w", policy_rel="simulation/policies/policy.onnx")
        self.assertEqual("zex-w", payload["robot"])
        self.assertEqual(["zex-w"], [item["robot_id"] for item in payload["presets"]])
        config = payload["configs"]["zex-w"]
        for key in ("robot", "policy", "sim"):
            self.assertIn(key, config, f"配置缺 {key}（形状与在线不一致）")

    def test_all_urls_are_localised(self):
        payload = bx.offline_payload("zex-w", policy_rel="simulation/policies/policy.onnx")
        blob = json.dumps(payload["configs"])
        self.assertNotIn("/api/simulation/browser-package", blob, "还有没本地化的包内 URL")
        self.assertEqual("../simulation/policies/policy.onnx", payload["configs"]["zex-w"]["policy"]["onnx_url"])
        self.assertFalse(payload["configs"]["zex-w"]["policy"]["disabled"])

    def test_bootstrap_answers_the_two_boot_requests(self):
        js = bx.bootstrap_js(bx.offline_payload("zex-w"))
        self.assertIn('path === "/api/robots/presets"', js)
        self.assertIn("browser-config", js)
        self.assertIn("browser-package", js)
        self.assertIn("realFetch", js)
        # 其余 /api/* 明确回 501（不静默失败成"页面白屏查不出原因"）
        self.assertIn("501", js)


class PlayerSourceFilesTest(unittest.TestCase):
    def test_excludes_demo_models_and_generated_entry(self):
        names = {path.name for path in bx.player_source_files()}
        self.assertNotIn("index.html", names, "入口页是生成物，不该拷贝（重复条目会让自校验红）")
        self.assertNotIn("assets", {path.parts[-1] for path in bx.player_source_files()})
        for required in ("app.js", "styles.css"):
            self.assertIn(required, names)


class PlayerExportTest(unittest.TestCase):
    def _export(self, tmp: str) -> Path:
        out = Path(tmp) / "bundle"
        bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", out, with_player=True)
        return out

    def test_player_files_and_manifest_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._export(tmp)
            self.assertTrue((out / "play" / "index.html").is_file())
            for required in ("offline-bootstrap.js", "serve.py", "offline-payload.json"):
                self.assertTrue((out / "play" / required).is_file(), required)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            roles = {entry["role"] for entry in manifest["entries"]}
            self.assertIn("player", roles)
            self.assertIn("player_asset", roles)
            # 回归：同一路径不许出现两条条目（曾因"先拷 index.html 再改写"踩到）
            paths = [entry["path"] for entry in manifest["entries"]]
            self.assertEqual(len(paths), len(set(paths)), "manifest 里有重复路径")
            self.assertTrue(bx.verify_export(out)["ok"])

    def test_verify_reports_player_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._export(tmp)
            report = bx.verify_export(out)
            self.assertIsNotNone(report["player"])
            self.assertTrue(report["player"]["ready"], report["player"]["problems"])
            self.assertIn("play/serve.py", report["player"]["how_to_open"])

    def test_bootstrap_is_injected_before_the_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._export(tmp)
            html = (out / "play" / "index.html").read_text(encoding="utf-8")
            self.assertLess(
                html.find("offline-bootstrap.js"), html.find('<script type="module"'),
                "引导层没有排在 app 之前 ⇒ 拦不住启动请求",
            )

    def test_missing_bootstrap_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._export(tmp)
            (out / "play" / "offline-bootstrap.js").unlink()
            player = bx.verify_player(out)
            self.assertFalse(player["ready"])
            self.assertTrue(any("offline-bootstrap.js" in problem for problem in player["problems"]))

    def test_pointer_to_a_policy_outside_the_bundle_is_red(self):
        """引导层指向的策略不在包里 ⇒ 离线机器上必然加载失败，必须如实报红。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = self._export(tmp)
            payload_path = out / "play" / "offline-payload.json"
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            payload["configs"]["zex-w"]["policy"]["onnx_url"] = "../simulation/policies/missing.onnx"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            player = bx.verify_player(out)
            self.assertFalse(player["ready"])
            self.assertTrue(any("不在包里" in problem for problem in player["problems"]), player["problems"])

    def test_player_leaves_no_ghost_files(self):
        """播放器写进去的每个文件都要登记进 manifest（否则 verify 会判幽灵文件）。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = self._export(tmp)
            self.assertTrue(bx.verify_export(out)["ok"])


if __name__ == "__main__":
    unittest.main()
