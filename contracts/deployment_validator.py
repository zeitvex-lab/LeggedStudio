"""Deployment Contract 校验器（对应优化清单 #9）。

背景：
    backend/deploy_pack.py 生成 deployment-contract.yaml/json，schema_version 为
    deployment-contract-1.0，但此前没有对应的 schema 真值源 / validator。
    这里补充无 torch 依赖的独立校验器，让部署契约与 Robot/Policy 契约形成
    完整三件套校验体系。

校验内容（与 contracts/schema/deployment-contract-1.0.schema.json 对齐）：
    - schema_version 必须为 deployment-contract-1.0；
    - robot_id / control / action 必须存在且类型合法；
    - action.joint_order 与 reindex_from_model / dimension 自洽；
    - control 频率字段约束。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEPLOY_CONTRACT_VERSION = "deployment-contract-1.0"
_SCHEMA = Path(__file__).resolve().parent / "schema" / "deployment-contract-1.0.schema.json"


class DeploymentContractError(ValueError):
    """部署契约不变量违背。"""


def validate_deployment_contract(contract: dict[str, Any]) -> list[str]:
    """校验一份部署契约字典，返回错误列表（空 = 通过）。

    刻意不依赖 jsonschema 库，用显式规则校验（控制面无额外依赖也可跑），
    同时与 schema 字段保持一致。
    """
    errors: list[str] = []
    if contract.get("schema_version") != DEPLOY_CONTRACT_VERSION:
        errors.append(
            f"schema_version 必须是 {DEPLOY_CONTRACT_VERSION!r}，得到 {contract.get('schema_version')!r}"
        )

    robot_id = contract.get("robot_id")
    if not isinstance(robot_id, str) or not robot_id:
        errors.append("robot_id 缺失或为空")

    control = contract.get("control") or {}
    if not isinstance(control, dict):
        errors.append("control 必须是 object")
    else:
        for key, lo, hi in (("control_hz", 10, 1000), ("physics_hz", 100, 10000)):
            value = control.get(key)
            if value is not None and not (isinstance(value, int) and lo <= value <= hi):
                errors.append(f"control.{key}={value!r} 超出 [{lo},{hi}]")

    action = contract.get("action") or {}
    if not isinstance(action, dict):
        errors.append("action 必须是 object")
    else:
        joint_order = action.get("joint_order")
        if not isinstance(joint_order, list) or not joint_order:
            errors.append("action.joint_order 缺失或为空")
        else:
            reindex = action.get("reindex_from_model")
            if reindex is not None:
                if not isinstance(reindex, list) or any(
                    not isinstance(i, int) or i < 0 for i in reindex
                ):
                    errors.append("action.reindex_from_model 必须是非负整数数组")
                elif len(reindex) != len(joint_order):
                    errors.append("action.reindex_from_model 长度 != joint_order 长度")
            dimension = action.get("dimension")
            if dimension is not None and dimension != len(joint_order):
                errors.append(f"action.dimension={dimension} != len(joint_order)={len(joint_order)}")
            scale = action.get("action_scale")
            if scale is not None and (not isinstance(scale, (int, float)) or scale <= 0):
                errors.append("action.action_scale 必须是正数")

    return errors


def load_schema() -> dict:
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))
