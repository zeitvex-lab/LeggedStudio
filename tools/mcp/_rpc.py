"""极简 stdio MCP 骨架：JSON-RPC 2.0 over stdin/stdout（newline-delimited）。

只实现本仓需要的最小子集：``initialize`` / ``tools/list`` / ``tools/call``。
不引 ``mcp`` 官方 SDK —— 控制面依赖越轻越好，而开发期工具用不到 notification、
sampling、roots 这些能力。

用法::

    from tools.mcp._rpc import run_server

    TOOLS = [{
        "name": "ping",
        "description": "返回 pong",
        "inputSchema": {"type": "object", "properties": {}},
    }]

    def call(name, args):
        if name == "ping":
            return {"pong": True}
        raise KeyError(name)

    if __name__ == "__main__":
        run_server("legged-studio-ping", "0.1.0", TOOLS, call)

``--selftest`` 只做导入 + 工具表自检并退出 0，供 CI / 云原生开发环境做冒烟。
"""
from __future__ import annotations

import json
import sys
from typing import Callable

PROTOCOL_VERSION = "2024-11-05"


def _send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(req_id, result):
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str):
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def run_server(
    name: str,
    version: str,
    tools: list[dict],
    call: Callable[[str, dict], object],
    instructions: str = "",
) -> None:
    """跑一个 stdio MCP server。

    ``call`` 抛 ``KeyError`` → method not found；抛其它异常 → tool 执行错误，
    以 ``isError=True`` 的文本结果返回（MCP 语义：工具失败不改协议层状态）。
    """
    known = {t["name"] for t in tools}

    if "--selftest" in sys.argv:
        # 自检：工具表结构合法 + 工具名可枚举。不调用 call（避免真跑物理/推理）。
        for t in tools:
            assert t["name"] and t["description"], f"tool 缺少 name/description: {t}"
            assert t["inputSchema"]["type"] == "object", f"{t['name']} 的 inputSchema 必须是 object"
        print(f"[{name}] {len(known)} tools: {', '.join(sorted(known))}")
        return

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            _result(req_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": name, "version": version},
                "instructions": instructions,
            })
        elif method == "tools/list":
            _result(req_id, {"tools": tools})
        elif method == "tools/call":
            params = req.get("params") or {}
            tool = params.get("name")
            if tool not in known:
                _error(req_id, -32601, f"unknown tool: {tool}")
                continue
            try:
                out = call(tool, params.get("arguments") or {})
                text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=2)
                _result(req_id, {"content": [{"type": "text", "text": text}]})
            except Exception as exc:  # noqa: BLE001 - 工具失败以结果返回，不炸协议层
                _result(req_id, {
                    "content": [{"type": "text", "text": f"tool '{tool}' failed: {exc}"}],
                    "isError": True,
                })
        elif method in ("notifications/initialized", "notifications/cancelled"):
            continue
        else:
            if req_id is not None:
                _error(req_id, -32601, f"method not implemented: {method}")
