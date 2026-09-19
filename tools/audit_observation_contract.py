"""观测契约缺口审计（**静态**：不建环境、不跑仿真、不 import torch/mjlab）。

E4 的观测映射板已经能判"缺什么"，但它只在**页面/端点**上出现 —— 于是缺口要靠人肉去看
（E4 当初就是这么发现"14 机型动作侧 0 问题、观测侧 11 个只声明宽度、3 个缺五元组字段"的）。
这里把它变成**常备检查**：一句话给出"谁缺组件、谁缺五元组字段、谁维度不符"。

用法::

    python tools/audit_observation_contract.py            # 报告
    python tools/audit_observation_contract.py --strict   # 有缺口即 exit 1（可作门禁）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.policy_artifacts import ROBOTS_DIR  # noqa: E402
from backend.training.obs_board import board  # noqa: E402


def contracts() -> list[tuple[str, dict]]:
    """**契约真值在包内** ``assets/robots/<robot>/contract.json``（E4 端点就是这么读的）。

    注意别用预设里的 ``contract`` —— 那是**摘要**、没有 ``components``，用它会把
    "14/14 都没声明组件"报成事实（本审计第一版正是这么错的，被"3 个已声明组件"的既有记录顶回来）。
    """
    found: list[tuple[str, dict]] = []
    for path in sorted(ROBOTS_DIR.glob("*/contract.json")):
        try:
            found.append((path.parent.name, json.loads(path.read_text(encoding="utf-8-sig"))))
        except (OSError, json.JSONDecodeError):
            continue
    return found


def audit() -> dict:
    """逐机型跑映射板，归类缺口。"""
    rows: list[dict] = []
    for robot_id, contract in contracts():
        report = board(contract)
        observation = report["observations"]
        rows.append({
            "robot": robot_id,
            "components": observation["components_declared"],
            "declared_dimension": observation["declared_dimension"],
            "components_total": observation["components_total"],
            "deployment_dimension": observation["deployment_dimension"],
            "no_components": observation["components_declared"] == 0,
            "missing_fields": sorted({
                field for item in observation["components"] for field in item["missing_fields"]
            }),
            "dimension_mismatch": any("不符" in item for item in observation["problems"]),
            "action_problems": report["actions"]["problems"],
            "problems": report["problems"],
        })
    return {
        "total": len(rows),
        "no_components": [row for row in rows if row["no_components"]],
        "missing_fields": [row for row in rows if row["missing_fields"]],
        "dimension_mismatch": [row for row in rows if row["dimension_mismatch"]],
        "action_problems": [row for row in rows if row["action_problems"]],
        "rows": rows,
    }


def main() -> int:
    report = audit()
    print(f"机型 {report['total']} 个")
    print(f"  只声明宽度、未声明组件：{len(report['no_components'])}"
          f"  {[row['robot'] for row in report['no_components']]}")
    print(f"  声明了组件但五元组缺字段：{len(report['missing_fields'])}"
          f"  {[row['robot'] for row in report['missing_fields']]}")
    print(f"  维度不符：{len(report['dimension_mismatch'])}"
          f"  {[row['robot'] for row in report['dimension_mismatch']]}")
    print(f"  动作侧有问题：{len(report['action_problems'])}"
          f"  {[row['robot'] for row in report['action_problems']]}")

    if report["missing_fields"]:
        print("\n声明了组件但缺五元组字段（部署观测过滤无从执行）：")
        for row in report["missing_fields"]:
            print(f"  ✗ {row['robot']:<22} 组件 {row['components']} 个 / 声明宽度 {row['declared_dimension']}"
                  f"  缺 {row['missing_fields']}")
    if report["no_components"]:
        print("\n未声明组件（只能给出声明宽度，五元组与部署宽度无从校验）：")
        for row in report["no_components"]:
            print(f"  ⚠ {row['robot']:<22} 声明宽度 {row['declared_dimension']} / 动作维 {row['action_problems'] or 'ok'}")
    for row in report["rows"]:
        for problem in row["problems"]:
            if "不符" in problem or "joint_order" in problem or "动作维度" in problem:
                print(f"  ! {row['robot']}: {problem}")

    gaps = len(report["no_components"]) + len(report["missing_fields"]) + \
        len(report["dimension_mismatch"]) + len(report["action_problems"])
    print(f"\n合计缺口 {gaps} 项")
    return 1 if (gaps and "--strict" in sys.argv) else 0


if __name__ == "__main__":
    raise SystemExit(main())
