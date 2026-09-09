"""T0.2：把 16 个机器人包从契约 v2 机械迁移到契约 v3 sidecar（CLI）。

核心逻辑在 backend/contract_migration.py（与导入流程共用）：
  - 关节名 token 解析自适应大小写与腿词序；无腿 token 关节归 extra_roles
  - actuator_profile 角色收敛（冲突关节落 by_joint）；joint_ids_map → reindex_from_model
  - 观测宽度可机械定宽才声明（history/视觉类诚实留空待补）
  - ROLE_HINTS 人工校对值覆盖机械推导（zex-w 轮 velocity / ±17 N·m）

产物全部过 RoleResolver 自洽校验；失败即报错退出（fail-closed）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 统一自举：见 contracts/path_bootstrap.py。裸脚本须先把仓库根放上
# sys.path 才能 import 顶层包；此处集中这一不可避免的自举，其余路径引导
# 全部收敛到 path_bootstrap 的幂等语义。
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts.path_bootstrap import bootstrap_root

ROOT = bootstrap_root()

from backend.contract_migration import apply_role_hints, migrate_contract_dict  # noqa: E402

ROBOTS_DIR = ROOT / "assets" / "robots"


def migrate_package(package_dir: Path) -> dict:
    v2 = json.loads((package_dir / "contract.json").read_text(encoding="utf-8-sig"))
    config = json.loads(
        (package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig")
    )
    contract = migrate_contract_dict(v2, config)
    contract = apply_role_hints(contract, package_dir.name)
    out = package_dir / "contract_v3.json"
    out.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    morphology = contract["morphology"]
    return {
        "package": package_dir.name,
        "out": str(out.relative_to(ROOT)),
        "legs": morphology["legs"],
        "roles": len(morphology["leg_pattern"]),
        "extras": morphology.get("extra_roles") or [],
        "reindex": contract["action"].get("reindex_from_model") is not None,
        "obs_components": len(contract["observation"]["components"]),
        "obs_dimension": contract["observation"]["dimension"],
    }


def main() -> int:
    report = []
    for package_dir in sorted(p for p in ROBOTS_DIR.iterdir() if (p / "contract.json").exists()):
        info = migrate_package(package_dir)
        report.append(info)
        print(
            f"OK {info['package']}: legs={info['legs']} roles={info['roles']} "
            f"extras={info['extras'] or '-'} reindex={info['reindex']} "
            f"obs={info['obs_components']}项/{info['obs_dimension']}维"
        )
    print(f"\n迁移完成：{len(report)} 包 → contract_v3.json（v2 保留，消费端切换在 T0.3）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
