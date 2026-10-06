"""契约校验路由（v3.0 Phase 2：自 ``api_complete`` 巨石下沉的域路由）。

无副作用的两条校验端点（机器人契约 v2 / Scenario），路径与行为零变化。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from contracts.contract_legacy_v2 import ContractLegacyV2
from contracts.scenario_contract import ScenarioContract
from contracts.validator import validate_contract as validate_robot_contract

router = APIRouter(tags=["contracts"])


@router.post("/api/contracts/validate")
async def validate_robot_contract_endpoint(contract_data: dict[str, Any]) -> dict[str, Any]:
    """Validate the canonical Robot Contract v2 used by every workflow step."""
    try:
        contract = ContractLegacyV2(**contract_data)
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}

    result = validate_robot_contract(contract)
    return {
        "valid": result.valid,
        "errors": [item.message for item in result.errors],
        "warnings": [item.message for item in result.warnings],
        "robot_id": contract.robot_id,
        "contract_id": contract.contract_id,
        "schema_version": contract.schema_version,
        "actuated_joints": len(contract.joints.actuated_joints),
        "control_hz": contract.control.control_hz,
        "summary": contract.get_summary(),
    }


@router.post("/api/scenarios/validate")
async def validate_scenario(scenario_data: dict[str, Any]) -> dict[str, Any]:
    try:
        scenario = ScenarioContract(**scenario_data)
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}
    return {"valid": True, "errors": [], "warnings": [], "scenario": scenario.to_payload()}
