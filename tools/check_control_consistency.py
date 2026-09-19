#!/usr/bin/env python3
"""控制三件套口径一致性检查（P2）。

背景（2026-09-13 实测）
----------------------
同一个物理量在三处出现，而且**并不总是一致**：

* **契约真值** ``control.{control_hz, physics_hz, decimation}`` —— 唯一真值（训练/验收/浏览器/工作台都读它）；
* **契约 v2** ``contract_legacy_v2.json`` 的 ``control`` 块 —— 工作台手上只有这份；保存链曾无条件把它写回 v3
  （go2 实测 v2=1000/20 vs v3=500/10）→ 点一次保存就把物理频率改成 2 倍。该回写已在
  ``PUT /api/robots/packages/<id>`` 里**关闭**（改为只对照回报）；
* **训练侧** ``training/profiles/*.json`` 的 ``decimation`` 与任务源码里的 ``sim.mujoco.timestep``
  （go2/zex-w 实测 decimation=4 + timestep=0.005 → 200 Hz）。

判定分两档
----------
* **硬性失败（exit 1）**：v3 自身不自洽 —— ``physics_hz != control_hz × decimation``。
  这一定是错：三者的关系是定义式的（decimation 是派生量）。
* **报告项（exit 0，但必须列出来）**：v2 与 v3 不一致、训练 profile 与 v3 不一致。
  这是"已知差异 / 待决"，不是错误；但不该是**静默**的——本脚本的职责就是让它可见。

用法
----
    python tools/check_control_consistency.py            # 表格
    python tools/check_control_consistency.py --json     # 机器可读
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"
RATE_KEYS = ("control_hz", "physics_hz", "decimation")


def _read_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _profile_decimations(package: pathlib.Path) -> list[int]:
    """训练 profile（可打包那份）声明的 decimation；源码里的 timestep 不在本检查范围。"""
    values: list[int] = []
    for path in sorted((package / "training" / "profiles").glob("*.json")):
        value = _read_json(path).get("decimation")
        if isinstance(value, int):
            values.append(value)
    return sorted(set(values))


def check_package(package: pathlib.Path) -> dict:
    v3 = _read_json(package / "contract.json").get("control") or {}
    v2 = _read_json(package / "contract_legacy_v2.json").get("control") or {}
    rates = {key: v3.get(key) for key in RATE_KEYS}
    control_hz, physics_hz, decimation = rates["control_hz"], rates["physics_hz"], rates["decimation"]

    # 硬性：v3 自洽（decimation 是派生量）
    self_consistent: bool | None = None
    expected = None
    if isinstance(control_hz, int) and isinstance(decimation, int) and decimation > 0:
        expected = control_hz * decimation
        if isinstance(physics_hz, int):
            self_consistent = abs(physics_hz - expected) <= 1  # 允许整数取整差 1

    v2_differs = [key for key in RATE_KEYS if key in v2 and v2.get(key) != v3.get(key)]
    profile_decimations = _profile_decimations(package)
    profile_differs = [d for d in profile_decimations if decimation is not None and d != decimation]

    return {
        "robot_id": package.name,
        "v3": rates,
        "v2": {key: v2.get(key) for key in RATE_KEYS},
        "expected_physics_hz": expected,
        "self_consistent": self_consistent,
        "v2_differs": v2_differs,
        "profile_decimations": profile_decimations,
        "profile_differs": profile_differs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="控制三件套口径一致性检查（P2）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    packages = sorted(p for p in ROBOTS.glob("*") if (p / "contract.json").is_file())
    reports = [check_package(p) for p in packages]
    hard = [r for r in reports if r["self_consistent"] is False]
    drift = [r for r in reports if r["v2_differs"] or r["profile_differs"]]

    if args.json:
        print(json.dumps({"packages": reports, "hard_failures": [r["robot_id"] for r in hard]}, ensure_ascii=False, indent=2))
        return 1 if hard else 0

    print(f"控制三件套一致性（{len(reports)} 个包）")
    print(f"{'包':24s} {'control_hz':>10s} {'physics_hz':>10s} {'decimation':>10s}  {'自洽':^8s} v2/训练差异")
    for report in reports:
        rates = report["v3"]
        mark = "✅" if report["self_consistent"] else ("❌" if report["self_consistent"] is False else "?")
        notes = []
        if report["v2_differs"]:
            notes.append("v2:" + ",".join(f"{k}={report['v2'][k]}" for k in report["v2_differs"]))
        if report["profile_differs"]:
            notes.append("训练 profile decimation=" + ",".join(str(d) for d in report["profile_differs"]))
        print(
            f"{report['robot_id']:24s} {str(rates['control_hz']):>10s} {str(rates['physics_hz']):>10s} "
            f"{str(rates['decimation']):>10s}  {mark:^8s} {' ; '.join(notes) or '—'}"
        )
    print()
    if hard:
        print(f"❌ 硬性失败 {len(hard)} 个：{'、'.join(r['robot_id'] for r in hard)}")
        for report in hard:
            print(f"   {report['robot_id']}: physics_hz={report['v3']['physics_hz']} 但 control_hz×decimation={report['expected_physics_hz']}")
    else:
        print("✅ 契约真值 自身全部自洽（physics_hz == control_hz × decimation）")
    if drift:
        print()
        print(f"⚠️  口径差异 {len(drift)} 个（**已登记、非错误**——见任务清单「待决 #7」与 P2 记录）：")
        for report in drift:
            bits = []
            if report["v2_differs"]:
                bits.append("v2 与 v3 不同")
            if report["profile_differs"]:
                bits.append("训练 profile 与 v3 不同")
            print(f"   {report['robot_id']}: {'、'.join(bits)}")
        print("   注：v3 是唯一真值；保存链已不再用 v2 覆盖 v3（PUT 只对照回报）。")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
