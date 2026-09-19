"""从 contracts/schema/ 生成的跨语言类型包。

真值源：contracts/schema/robot-contract-3.0.schema.json
再生成：python tools/generate_contract_models.py（需 datamodel-code-generator /
json-schema-to-typescript，见脚本内说明）。当前签入的模块与 schema 逐字段对齐，
由 contracts/tests/test_role_resolver_v3.py 的 parity 测试守护。
"""

from .robot_contract import (
    ActuatorParamsV3,
    ActuatorProfileV3,
    ActionSpecV3,
    ControlSpecV3,
    JointEntryV3,
    MorphologySpec,
    ObservationComponentV3,
    ObservationSpecV3,
    PassiveJointV3,
    RobotContractV3,
    TaskRequirements,
    dump_v3,
    load_schema,
    parse_contract,
)

__all__ = [
    "ActuatorParamsV3",
    "ActuatorProfileV3",
    "ActionSpecV3",
    "ControlSpecV3",
    "JointEntryV3",
    "MorphologySpec",
    "ObservationComponentV3",
    "ObservationSpecV3",
    "PassiveJointV3",
    "RobotContractV3",
    "TaskRequirements",
    "dump_v3",
    "load_schema",
    "parse_contract",
]
