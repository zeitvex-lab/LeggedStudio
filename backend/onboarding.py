"""厂商适配包接入 DoD 读数（N4：onboarding DoD 清单的服务端单一真值）。

**为什么有本模块**：竞品 RoboCraft 把「自研本体快速接入」做成产品（`06` §12.2），
本仓的等价物 = 把接入判据**向导化投影**（`06` §16.2 N4）——厂商（或自己）导入一台
新机器人后，一眼看到「离进产品面还差什么」，每一步的判据都是机器读数而非口头承诺。

**四步**（与 `web/onboarding.html` 页面步骤一一对应）：

| 步 | 判据 | 实现的家（本模块只组装，不发明判据） |
|---|---|---|
| ① 包结构 | `contract_legacy_v2.json` + `robot_package.json` + 模型文件可解析 | `backend.robot_packages` 包记录 |
| ② 契约校验 | 包内 v3（`contract.json`）vs v2 快照层间一致 | `backend.deploy_pack.deploy_gate_report`（CLI `deploy gate` / HTTP `/api/deploy/gate` 同一处） |
| ③ 族判与体检 | 族通用就绪 + 五卡（质量/碰撞/惯量/电机/关节） | `backend.asset_inspection.inspect_package`（工作台「体检」页同一处） |
| ④ 冒烟可训 | `trainability.json`（导入后自动冒烟的结论） | `backend.trainability_check`（env-gated：「没测过」与「测失败」分开报，不把没测说成测过） |

**三面同源**（面板四投影纪律，`06` §14.4）：Web 页面
（`GET /api/robots/packages/{robot_id}/onboarding`）、CLI（`panel onboarding`）、
首页卡片（`home_card` provider）全部调本模块——不存在「页面看到另一套数据」。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_STEPS = ("structure", "contract", "inspection", "smoke")
_STEP_TITLES = {
    "structure": "包结构",
    "contract": "契约校验",
    "inspection": "族判与体检",
    "smoke": "冒烟可训",
}


def _package_record(robot_id: str) -> dict[str, Any] | None:
    from backend.robot_packages import list_robot_packages

    return next((p for p in list_robot_packages() if p.get("robot_id") == robot_id), None)


def _package_root(record: dict[str, Any]) -> Path:
    manifest = record.get("robot_package") or {}
    root = str(manifest.get("package_root") or "")
    if root:
        return Path(root)
    return Path(str(record.get("contract_path") or "")).parent


def _structure_step(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    """① 包结构：三件在不在（契约 v2 快照 / manifest / 模型声明可解析）。"""
    manifest = record.get("robot_package") or {}
    contract_rel = str(record.get("contract_path") or "")
    contract = root / "contract_legacy_v2.json"
    if contract_rel and not contract.is_absolute():
        contract = Path(contract_rel)
    files = {
        "contract_legacy_v2.json": contract.is_file(),
        "robot_package.json": (root / "robot_package.json").is_file(),
        "contract.json": (root / "contract.json").is_file(),
    }
    # manifest.model 是 {format, path, training_path, assets_path}（04 §2.2：训练认
    # training_path，缺它才回落 path）——判据 = 声明的模型文件真实存在。
    model_block = manifest.get("model") or {}
    model_rel = str((model_block.get("training_path") or model_block.get("path") or "") if isinstance(model_block, dict) else model_block)
    model = (root / model_rel) if model_rel else None
    files["model"] = bool(model and model.exists())
    missing = [name for name, ok in files.items() if not ok]
    return {
        "status": "pass" if not missing else "fail",
        "summary": "三件齐备（契约 v2 快照 / manifest / 模型）" if not missing else f"缺：{' / '.join(missing)}",
        "package_root": str(root),
        "files": files,
        "model_path": model_rel or None,
        "dof": record.get("dof"),
        "family": record.get("family"),
        "source": record.get("source"),
    }


def _contract_step(robot_id: str) -> dict[str, Any]:
    """② 契约校验：包内 v3 vs v2 层间一致（deploy gate 同一实现；deny 不编造通过）。"""
    from backend.deploy_pack import deploy_gate_report

    try:
        report = deploy_gate_report(robot_id)
    except Exception as exc:  # 包不存在/契约不全：如实报 fail，不静默跳过
        return {"status": "fail", "summary": f"契约校验无法执行：{exc}", "blockers": [str(exc)]}
    return {
        "status": "pass" if report.get("ok") else "fail",
        "summary": "包内 v3 契约与 v2 快照层间一致" if report.get("ok") else f"{len(report.get('blockers') or [])} 个 blocker（层间不一致）",
        "blockers": list(report.get("blockers") or []),
        "warnings": list(report.get("warnings") or []),
    }


def _inspection_step(root: Path) -> dict[str, Any]:
    """③ 族判与体检：inspect_package 同一实现（工作台体检页同源）。"""
    from backend.asset_inspection import inspect_package

    report = inspect_package(root)
    readiness = report.get("family_readiness") or {}
    cards = report.get("cards") or {}
    verdict = str(readiness.get("verdict") or "")
    worst = "pass"
    for status in ("fail", "warn"):
        if report.get("overall") == status or verdict == status:
            worst = status
            break
    both_pass = report.get("overall") == "pass" and verdict == "ready"
    return {
        "status": worst,
        "summary": "体检五卡 + 族通用就绪全过" if both_pass
            else f"体检 {report.get('overall')} · 族就绪 {verdict or '-'}",
        "overall": report.get("overall"),
        "cards": {name: {"status": card.get("status"), "summary": card.get("summary")} for name, card in cards.items()},
        "family_readiness": {
            "verdict": verdict,
            "family": readiness.get("family"),
            "checks": [
                {"id": c.get("id"), "status": c.get("status"), "summary": c.get("summary")}
                for c in (readiness.get("checks") or [])
            ],
            "trainable_terrain_profiles": list(readiness.get("trainable_terrain_profiles") or []),
        },
    }


def _smoke_step(root: Path) -> dict[str, Any]:
    """④ 冒烟可训：trainability.json（env-gated；没测过 ≠ 测失败）。"""
    from backend.trainability_check import load

    record = load(root)
    if record is None:
        return {"status": "untested", "summary": "没测过（包内没有 trainability.json；静态就绪后会自动起冒烟）"}
    status = str(record.get("status") or "")
    reason = str(record.get("reason") or "")
    if status == "passed":
        return {"status": "pass", "summary": reason or "冒烟通过（真训 1 iter）"}
    return {"status": "fail", "summary": reason or f"冒烟未通过（status={status or '未知'}）", "reason": reason}


def package_onboarding(robot_id: str) -> dict[str, Any]:
    """单包接入 DoD 四步读数（Web 页面与 CLI 详情同源）。

    包不存在 → ``KeyError``（调用方映射 404 / 退出码 1，不静默返回空）。
    """
    record = _package_record(robot_id)
    if record is None:
        raise KeyError(f"未知机器人包: {robot_id}")
    root = _package_root(record)
    steps = {
        "structure": _structure_step(root, record),
        "contract": _contract_step(robot_id),
        "inspection": _inspection_step(root),
        "smoke": _smoke_step(root),
    }
    statuses = [steps[name]["status"] for name in _STEPS]
    overall = "pass"
    for candidate in ("fail", "untested", "warn"):
        if candidate in statuses:
            overall = candidate
            break
    return {
        "robot_id": robot_id,
        "package_root": str(root),
        "steps": steps,
        "overall": overall,
        "ready": overall == "pass",
        "step_titles": dict(_STEP_TITLES),
    }


def onboarding_overview() -> dict[str, Any]:
    """全包接入 DoD 一览（CLI ``panel onboarding`` 与首页卡片同源）。

    单包读数失败（如包目录被移动）不拖垮整张表：该行如实记 ``error``，
    其余包照常——与首页聚合端点同一 fail-soft 口径（`06` §14.4 诚实禁用）。
    """
    from backend.robot_packages import list_robot_packages

    rows: list[dict[str, Any]] = []
    for record in list_robot_packages():
        robot_id = str(record.get("robot_id") or "")
        try:
            detail = package_onboarding(robot_id)
        except Exception as exc:  # noqa: BLE001 - 单包失败只降级该行
            rows.append({"robot_id": robot_id, "overall": "error", "error": str(exc)})
            continue
        rows.append({
            "robot_id": robot_id,
            "family": detail["steps"]["structure"].get("family"),
            "dof": detail["steps"]["structure"].get("dof"),
            "overall": detail["overall"],
            "steps": {name: detail["steps"][name]["status"] for name in _STEPS},
        })
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["overall"]] = counts.get(row["overall"], 0) + 1
    return {
        "packages": rows,
        "total": len(rows),
        "counts": counts,
        "ready": counts.get("pass", 0),
        "note": "四步全绿 = 可进产品面（可训练 / 可仿真 / 可部署投影）",
    }
