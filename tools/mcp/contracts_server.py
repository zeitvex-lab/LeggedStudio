"""MCP: 契约真值 查询与校验。

落点：``contracts/``（schema + 校验器）、``assets/robots/*/contract.json``、
``backend/pack_catalog.py``（Pack 引用哈希对账）。

为什么值得做成 MCP：契约是本仓的"单一事实源"，agent 每次问"这机器人的关节序/
PD/obs 维是多少"都要跨 3~4 个文件手工拼，MCP 把这层拼装固化成一次调用。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from contracts.validator import normalized_sha256  # 归一摘要唯一实现

from tools.mcp._rpc import run_server  # noqa: E402

ROBOTS_DIR = ROOT / "assets" / "robots"
PACKS_DIR = ROOT / "packs"


def _contract_path(robot: str) -> Path:
    return ROBOTS_DIR / robot / "contract.json"


def _load_contract(robot: str) -> dict:
    path = _contract_path(robot)
    if not path.is_file():
        raise FileNotFoundError(f"契约不存在: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def get_contract(robot: str, section: str = "") -> object:
    """读整份契约或其中一段（morphology / joints / actuator / observation ...）。"""
    data = _load_contract(robot)
    if not section:
        return data
    node: object = data
    for key in section.split("."):
        if not isinstance(node, dict) or key not in node:
            raise KeyError(f"{robot} 契约里没有 {section}（断在 {key}）")
        node = node[key]
    return node


def list_joints(robot: str) -> object:
    """列关节名与顺序 —— 关节序错了策略必废，这是最高频的核对项。

    契约真值 里关节有**三种序**，含义不同、不可混用（混用是 reindex bug 的源头）：
      - ``joints.actuated``：声明序（带 leg/role 语义，只有这个能按 role 查）；
      - ``action.joint_order``：**策略输出序**，部署 reindex 的判据；
      - ``joints.default_pose``：与之按位对齐的默认姿态。
    本工具默认返回 ``action.joint_order``（部署最关心的那一个），并同时给出声明序。
    """
    data = _load_contract(robot)
    actuated = (data.get("joints") or {}).get("actuated") or []
    declared = [j.get("name") if isinstance(j, dict) else j for j in actuated]
    roles = [j.get("role") for j in actuated if isinstance(j, dict)]
    action_order = (data.get("action") or {}).get("joint_order") or []
    order = action_order or declared
    return {
        "robot": robot,
        "count": len(order),
        "action_joint_order": action_order or None,
        "declared_order": declared,
        "roles": roles,
        "orders_match": bool(action_order) and action_order == declared,
    }


def list_robots() -> object:
    """已入库机型清单（有 contract.json 的目录）。"""
    robots = sorted(p.parent.name for p in ROBOTS_DIR.glob("*/contract.json"))
    return {"count": len(robots), "robots": robots}


def verify_pack(pack_id: str) -> object:
    """核 Pack 的 ``morphology_ref.sha256`` 是否与实际契约一致。

    复刻 ``backend/pack_catalog.py`` 的判据（规范化内容哈希：CRLF → LF），
    避免 agent 在本地跑出与 CI 不同的结论。
    """
    path = PACKS_DIR / f"{pack_id}.pack.json"
    if not path.is_file():
        matches = sorted(PACKS_DIR.glob(f"*{pack_id}*.pack.json"))
        if len(matches) != 1:
            raise FileNotFoundError(f"找不到唯一 Pack: {pack_id}（候选 {len(matches)} 个）")
        path = matches[0]
    pack = json.loads(path.read_text(encoding="utf-8-sig"))
    ref = pack.get("morphology_ref") or {}
    robot = ref.get("robot") or ref.get("id")
    expected = ref.get("sha256")
    if not robot or not expected:
        return {"pack": path.name, "ok": False, "reason": "morphology_ref 缺 robot/sha256"}

    # 归一摘要唯一实现见 ``contracts.validator``（此前这里自带一份 CRLF 归一键）
    actual = normalized_sha256(_contract_path(robot).read_bytes())
    return {
        "pack": path.name,
        "robot": robot,
        "ok": actual == expected,
        "expected": expected[:16],
        "actual": actual[:16],
        "hint": None if actual == expected else "跑 tools/generate_packs.py 重新对齐",
    }


TOOLS = [
    {
        "name": "list_robots",
        "description": "列出已入库机型（有 contract.json 的目录）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_contract",
        "description": "读某机型契约真值 的全部或某一段（点号路径，如 joints / actuator.by_role）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "机型目录名，如 unitree_go2"},
                "section": {"type": "string", "description": "可选，点号路径"},
            },
            "required": ["robot"],
        },
    },
    {
        "name": "list_joints",
        "description": "列某机型的关节名与顺序（策略 reindex 的最高频核对项）",
        "inputSchema": {
            "type": "object",
            "properties": {"robot": {"type": "string"}},
            "required": ["robot"],
        },
    },
    {
        "name": "verify_pack",
        "description": "核 Capability Pack 的 morphology_ref.sha256 是否过期（同 CI 判据）",
        "inputSchema": {
            "type": "object",
            "properties": {"pack_id": {"type": "string", "description": "如 go2_velocity"}},
            "required": ["pack_id"],
        },
    },
]

_DISPATCH = {
    "list_robots": lambda a: list_robots(),
    "get_contract": lambda a: get_contract(a["robot"], a.get("section", "")),
    "list_joints": lambda a: list_joints(a["robot"]),
    "verify_pack": lambda a: verify_pack(a["pack_id"]),
}


def call(name: str, args: dict) -> object:
    return _DISPATCH[name](args)


if __name__ == "__main__":
    run_server(
        "legged-studio-contracts",
        "0.1.0",
        TOOLS,
        call,
        instructions="查询 Legged Studio 契约真值：机型清单、关节序、任意字段段、Pack 哈希对账。",
    )
