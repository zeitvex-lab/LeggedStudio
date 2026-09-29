"""地形档门禁（**静态层**）：`registry/terrains` 的声明自洽、可解析、无空条目。

## 为什么只做静态层

"能不能真装配出地形实体"需要 mjlab（训练栈）——那份检查在
`adapters/mjlab/test_terrain_profiles_assembly.py`（用适配器 venv 跑，仓库纪律同
`adapters/mjlab/test_generic_task_env_smoke.py`）。本工具跑在**零依赖**环境（CI 的
仓库 venv），负责那些不装训练栈也能判的事：

| 检查 | 判据 | 抓什么 |
|---|---|---|
| 清单权威 | `index.json` 登记的档 == `profiles.json` 里的档 | 档位写进表却没登记（静默注册） |
| 声明有据 | 每档有 `class` / `summary` / `evidence.source` | 空声明、无出处 |
| builder 自洽 | `kind ∈ {flat, mjlab_generator, family_kit}`；`mjlab_generator` 的 `cfg` 是模块路径；`family_kit` 每族的 refs 指向**存在的文件** | 档位写了却指不到构造 |
| 族维度完整 | 每档对两族都给 `ready` / `missing` | 漏声明（装配期才发现） |

**装配层（真装配 = 判据的一半）**：`ready` 必须真能装出来、`missing` 必须真装不出来——
由适配器 venv 的那份测试守着（它同时打印逐条矩阵）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab import terrain_profiles  # noqa: E402

KNOWN_KINDS = {"flat", "mjlab_generator", "family_kit"}


def _ref_exists(dotted: str) -> bool:
    """把 `a.b.c` 认成**模块**或**模块.符号**（`def`/`class` 名）——两种写法都合法。"""
    parts = [p for p in str(dotted).split(".") if p]
    for cut in (0, 1):
        module = parts[: len(parts) - cut]
        if not module:
            break
        base = ROOT.joinpath(*module)
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if not candidate.is_file():
                continue
            if cut == 0:
                return True
            symbol = parts[-1]
            text = candidate.read_text(encoding="utf-8", errors="ignore")
            return re.search(rf"^(?:def|class)\s+{re.escape(symbol)}\b", text, re.MULTILINE) is not None
    return False


def audit() -> dict:
    problems: list[str] = []
    rows: list[tuple[str, str, str]] = []

    try:
        table = terrain_profiles.profiles()
    except terrain_profiles.TerrainProfileError as exc:
        return {"ok": False, "problems": [str(exc)], "rows": []}

    for profile_id, entry in table.items():
        if not str(entry.get("class") or "").strip():
            problems.append(f"{profile_id}: 缺 class（地形轴上的归类）")
        if not str(entry.get("summary") or "").strip():
            problems.append(f"{profile_id}: 缺 summary")
        if not str((entry.get("evidence") or {}).get("source") or "").strip():
            problems.append(f"{profile_id}: 缺 evidence.source（判据要能追到出处）")

        builder = entry.get("builder") or {}
        kind = str(builder.get("kind") or "")
        if kind not in KNOWN_KINDS:
            problems.append(f"{profile_id}: 未知 builder.kind {kind!r}（可选：{', '.join(sorted(KNOWN_KINDS))}）")
        elif kind == "mjlab_generator":
            cfg = str(builder.get("cfg") or "")
            if "." not in cfg:
                problems.append(f"{profile_id}: builder.cfg 不是模块路径：{cfg!r}")
            sub = builder.get("sub_terrains")
            if sub is not None and (not isinstance(sub, list) or not all(str(x).strip() for x in sub)):
                problems.append(f"{profile_id}: sub_terrains 应为非空字符串列表（或省略 = 整族）")
        elif kind == "family_kit":
            for family in terrain_profiles.FAMILIES:
                refs = builder.get(family)
                if refs is None:
                    continue
                for key, dotted in dict(refs).items():
                    if not _ref_exists(dotted):
                        problems.append(f"{profile_id}/{family}: builder.{key} 指向不存在的模块：{dotted}")

        for family in terrain_profiles.FAMILIES:
            rows.append((profile_id, family, terrain_profiles.availability(profile_id, family)))

    return {"ok": not problems, "problems": problems, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="地形档声明的静态门禁")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    report = audit()
    if not args.quiet:
        print("[terrains/static] 档位 × 族 → 声明")
        for profile_id, family, status in report["rows"]:
            mark = "✓" if status == "ready" else "·"
            print(f"  {mark} {profile_id:18s} {family:10s} {status}")
    if report["problems"]:
        print(f"\n[terrains/static] {len(report['problems'])} 个问题：")
        for item in report["problems"]:
            print(f"  - {item}")
        return 1
    print(f"\n[terrains/static] 全部一致：{len({row[0] for row in report['rows']})} 档 × {len(terrain_profiles.FAMILIES)} 族"
          "（装配层由 adapters/mjlab/test_terrain_profiles_assembly.py 用训练栈验）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
