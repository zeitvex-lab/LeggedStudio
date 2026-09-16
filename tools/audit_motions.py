#!/usr/bin/env python3
"""M1 Motion 注册表门禁：``registry/motions/index.json`` vs 磁盘实测。

## 为什么要有它

Motion 参考动作在 `01_项目定位` 里与 Morphology / Skill / Scenario / Policy 同级（一等资源），
但本仓此前只有**文件**没有**资源层** —— 数据散在包里、元信息（fps / dof 布局 / 坐标系 /
血缘 / 许可）写在加载器的文档串里，没有任何东西守着它们。`registry/packs/imitation_amp.json`
自己写着「仓内 motion 注册表尚未建立，缺失时挂载会失败」。

本脚本把"注册表说有什么"与"磁盘上真有什么"逐条对账：

* **覆盖**：磁盘上的每份 motion 都必须在注册表里；注册表里不许留磁盘上已不存在的条目；
  条目数与文件数一起钉（多一个少一个都判红）；
* **内容**：逐文件 sha256 对账（数据被换掉必被检出）；
* **字段**：`id/robot/source/format/fps/dof_layout/dof_dim/conventions/lineage/license/files`
  缺一即拒（校验逻辑在 :mod:`backend.motion_registry`，本脚本不另写一套）；
* **许可**：与 I5 同口径 —— 缺许可记录不得进注册表；确未取证必须显式 `status=unresolved`
  + 原因（**不许留空、也不许编**）。未取证的条目作为 **gap 如实列出**（不判红），
  但"没写许可字段"或"编了个许可"一律判红。

用法：

    python tools/audit_motions.py             # 对账（进 CI）
    python tools/audit_motions.py --json      # 机器可读
    python tools/audit_motions.py --apply     # 显式动作：按实测重写注册表
    python tools/audit_motions.py --list       # 逐条打印（人工复核用）

退出码：0 通过；1 有缺口/不一致。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import motion_registry as mr  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M1 Motion 注册表门禁")
    parser.add_argument("--apply", action="store_true", help="按实测重写 registry/motions/index.json")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--list", action="store_true", help="逐条打印注册表内容")
    args = parser.parse_args(argv)

    if args.apply:
        payload = mr.apply_registry()
        print(
            f"已写入 {mr.INDEX_PATH.relative_to(PROJECT_ROOT).as_posix()}："
            f"{payload['counts']['clips']} 条 motion / {payload['counts']['files']} 份数据文件"
        )

    report = mr.audit()

    if args.list:
        for entry in mr.derive()["motions"]:
            files = ", ".join(sorted(entry["files"]))
            print(
                f"  [{entry['robot']}/{entry['source']}] {entry['id']}\n"
                f"      {entry['format']} fps={entry['fps']} dof={entry['dof_layout']} "
                f"frames={entry['frames_min']}..{entry['frames_max']} 变体=[{files}]\n"
                f"      许可：{(entry['license'].get('spdx') or '未取证')}"
            )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("=" * 78)
    print("M1 Motion 注册表对账")
    print("=" * 78)
    print(f"条目 {report['clips']} 条 / 数据文件 {report['files']} 份")
    consumers = report.get("consumers") or {}
    if consumers:
        counts = consumers.get("counts") or {}
        print(
            "三侧消费：tracking {tracking} / amp {amp} / browser {browser}".format(
                tracking=counts.get("tracking", 0), amp=counts.get("amp", 0), browser=counts.get("browser", 0),
            )
            + (f"（另有无消费方 {len(consumers.get('unclaimed') or [])} 份）" if consumers.get("unclaimed") else "")
        )
    for entry in mr.derive()["motions"]:
        print(
            f"  {entry['robot']:<16}{entry['source']:<14}{entry['format']:<5}"
            f"fps={str(entry['fps']):<6}dof={str(entry['dof_layout']):<18}"
            f"许可={entry['license'].get('spdx') or '未取证'}"
        )
    if report["license_gaps"]:
        print(f"\n许可未取证（如实登记，不阻断）：{len(report['license_gaps'])} 条")
        for gap in report["license_gaps"]:
            print(f"  - {gap['id']}")
    if report["problems"]:
        print(f"\n✗ 不达标 {len(report['problems'])} 项：")
        for item in report["problems"]:
            print(f"  - {item}")
        return 1
    print("\n全部 motion 已登记且与磁盘逐文件一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
