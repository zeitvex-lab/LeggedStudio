"""MCP: ``00_resources/`` 跨库检索（77 个上游参考项目）。

落点：``00_resources/_index.json``（机器可读索引）、``00_resources/README.md``、
``tools/sync_resources.py``（生成方）。

为什么值得做成 MCP：进度流水里有大量「按字面名 grep 一遍 77 个仓」的操作
（例如找某机型的上游训练源码来满足移植准入规则 T），每次都手工 grep + 拼路径。
索引 ``_index.json`` 已经把「项目 → 机型 → 各类文件数 → 策略文件数」结构化了，
这里只是把它变成可查询的接口。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.mcp._rpc import run_server  # noqa: E402

INDEX = ROOT / "00_resources" / "_index.json"
RES = ROOT / "00_resources"


def _index() -> dict:
    if not INDEX.is_file():
        raise FileNotFoundError(f"索引不存在: {INDEX.relative_to(ROOT)}（跑 tools/sync_resources.py --reindex）")
    return json.loads(INDEX.read_text(encoding="utf-8"))


def list_robots() -> object:
    """机型 → 上游项目清单（含 label）。"""
    idx = _index()
    return {
        "generated_at": idx.get("generated_at"),
        "count": len(idx.get("robots", {})),
        "robots": {
            rid: {"label": info.get("label"), "projects": info.get("projects", [])}
            for rid, info in sorted(idx.get("robots", {}).items())
        },
    }


def search_projects(
    robot: str = "",
    keyword: str = "",
    category: str = "",
    min_policies: int = 0,
    limit: int = 30,
) -> object:
    """按机型 / 关键词 / 资源类别过滤项目。

    ``category`` 取 ``_index.json`` 的 per_category 键：
    model / contract / training / deploy / terrain_scene / motion / evaluation / misc。
    """
    idx = _index()
    projects = idx.get("projects", {})
    allowed: set[str] | None = None
    if robot:
        allowed = set(idx.get("robots", {}).get(robot, {}).get("projects", []))
        if not allowed:
            return {"robot": robot, "matched": 0, "hint": "该机型未在索引中登记（用 list_robots 看可用 id）"}

    hits = []
    for name, info in projects.items():
        if allowed is not None and name not in allowed:
            continue
        if keyword:
            haystack = f"{name} {info.get('desc', '')} {info.get('source', '')}".lower()
            if keyword.lower() not in haystack:
                continue
        if category and int(info.get("per_category", {}).get(category, 0)) <= 0:
            continue
        if min_policies and int(info.get("policy_files", 0)) < min_policies:
            continue
        hits.append({
            "project": name,
            "desc": info.get("desc"),
            "robots": info.get("robots", []),
            "policy_files": info.get("policy_files", 0),
            "kept": info.get("kept", 0),
            "size_mb": round(info.get("kept_bytes", 0) / 1e6, 1),
            "per_category": info.get("per_category", {}),
            "readme": info.get("readme"),
        })

    hits.sort(key=lambda h: (-h["policy_files"], -h["kept"]))
    return {"query": {"robot": robot, "keyword": keyword, "category": category}, "matched": len(hits), "projects": hits[:limit]}


def project_files(project: str, pattern: str = "*", limit: int = 60) -> object:
    """列某项目内的实际文件（按 glob 过滤），用于确认"这份上游证据到底在不在"。"""
    base = RES / project
    if not base.is_dir():
        candidates = [p.name for p in RES.iterdir() if p.is_dir() and project.lower() in p.name.lower()]
        return {"project": project, "error": "项目不存在", "candidates": candidates[:10]}
    files = [p for p in sorted(base.rglob(pattern)) if p.is_file()]
    return {
        "project": project,
        "pattern": pattern,
        "count": len(files),
        "files": [str(p.relative_to(RES)) for p in files[:limit]],
        "truncated": len(files) > limit,
    }


TOOLS = [
    {
        "name": "list_robots",
        "description": "列机型 → 上游项目清单（77 个项目的机器人映射）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_projects",
        "description": "按机型/关键词/资源类别过滤上游项目（可要求至少 N 个策略文件）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "机型 id，如 unitree_go2"},
                "keyword": {"type": "string", "description": "匹配项目名/描述/源路径"},
                "category": {"type": "string", "description": "model|contract|training|deploy|terrain_scene|motion|evaluation|misc"},
                "min_policies": {"type": "integer", "description": "至少多少个推理策略文件"},
                "limit": {"type": "integer", "description": "默认 30"},
            },
        },
    },
    {
        "name": "project_files",
        "description": "列某项目内文件（glob），核对上游证据是否存在",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "pattern": {"type": "string", "description": "glob，默认 *，如 **/*.py 或 **/*.onnx"},
                "limit": {"type": "integer", "description": "默认 60"},
            },
            "required": ["project"],
        },
    },
]

_DISPATCH = {
    "list_robots": lambda a: list_robots(),
    "search_projects": lambda a: search_projects(
        a.get("robot", ""), a.get("keyword", ""), a.get("category", ""),
        int(a.get("min_policies", 0)), int(a.get("limit", 30)),
    ),
    "project_files": lambda a: project_files(a["project"], a.get("pattern", "*"), int(a.get("limit", 60))),
}


def call(name: str, args: dict) -> object:
    return _DISPATCH[name](args)


if __name__ == "__main__":
    run_server(
        "legged-studio-resources",
        "0.1.0",
        TOOLS,
        call,
        instructions="00_resources 跨库检索：机型→项目映射、按类别过滤、项目内文件核对。",
    )
