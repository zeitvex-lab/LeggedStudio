"""MCP 工具链回归：``.cnb/mcp/servers.json`` 与 ``tools/mcp/`` 的自研 server。

守三件事：
  1. ``servers.json`` 是合法 JSON 且每条 server 声明完整（name/command/description）；
  2. 自研 server 能导入、工具表结构合法（``--selftest`` 口径）且**工具名不重名**；
  3. 工具真能被调用并返回可解析结果（用仓库内已存在的真实资产，不 mock）。
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVERS_JSON = ROOT / ".cnb" / "mcp" / "servers.json"
SELF_HOSTED = ["contracts_server", "mujoco_server", "onnx_server", "resources_server"]


class McpServersJsonTest(unittest.TestCase):
    def test_servers_json_shape(self) -> None:
        data = json.loads(SERVERS_JSON.read_text(encoding="utf-8"))
        servers = data.get("mcpServers")
        self.assertIsInstance(servers, dict)
        self.assertGreaterEqual(len(servers), 10, "MCP 清单不应少于 10 条")

        for name, cfg in servers.items():
            with self.subTest(server=name):
                self.assertTrue(cfg.get("command"), f"{name} 缺 command")
                self.assertIsInstance(cfg.get("args"), list)
                self.assertTrue(cfg.get("description"), f"{name} 缺 description（选型依据必须写清）")

    def test_self_hosted_servers_declared(self) -> None:
        """``tools/mcp/*_server.py`` 都必须出现在 servers.json 里，防止加了 server 忘了登记。"""
        servers = json.loads(SERVERS_JSON.read_text(encoding="utf-8"))["mcpServers"]
        # 自研 server 用 `python -m tools.mcp.<name>` 声明，故从模块路径取名字。
        declared = {
            str(arg).rsplit(".", 1)[-1]
            for cfg in servers.values()
            for arg in cfg["args"]
            if str(arg).startswith("tools.mcp.")
        }
        self.assertEqual(declared, set(SELF_HOSTED))


class McpSelfHostedServerTest(unittest.TestCase):
    def _selftest(self, module: str) -> str:
        proc = subprocess.run(
            [sys.executable, "-m", f"tools.mcp.{module}", "--selftest"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, f"{module} 自检失败: {proc.stderr[-800:]}")
        return proc.stdout

    def test_all_servers_selftest(self) -> None:
        for module in SELF_HOSTED:
            with self.subTest(module=module):
                out = self._selftest(module)
                self.assertIn("tools:", out)

    def test_tool_names_unique_within_server(self) -> None:
        for module in SELF_HOSTED:
            with self.subTest(module=module):
                sys.path.insert(0, str(ROOT))
                mod = __import__(f"tools.mcp.{module}", fromlist=["TOOLS"])
                names = [t["name"] for t in mod.TOOLS]
                self.assertEqual(len(names), len(set(names)), f"{module} 工具名重复")

    def test_contracts_server_real_call(self) -> None:
        from tools.mcp import contracts_server

        robots = contracts_server.list_robots()
        self.assertGreaterEqual(robots["count"], 14, "14 个内置机型都应有 contract.json")

        joints = contracts_server.list_joints("unitree_go2")
        self.assertEqual(joints["count"], 12)
        self.assertTrue(joints["orders_match"], "声明序与策略输出序不一致是 reindex bug 源头")

    def test_resources_server_reads_index(self) -> None:
        from tools.mcp import resources_server

        robots = resources_server.list_robots()
        self.assertGreaterEqual(robots["count"], 14)
        hits = resources_server.search_projects(robot="zex-w")
        self.assertGreaterEqual(hits["matched"], 1, "zex-w 的移植准入证据必须可检索到")


if __name__ == "__main__":
    unittest.main()
