"""契约产物生成器 / 防漂移一致性校验。

真值源：contracts/schema/robot-contract-3.0.schema.json
产物：
  - contracts/generated/robot_contract_v3.py   （Pydantic v2 模型）
  - web/shared/generated/types.d.ts            （TypeScript 类型）

两种运行模式：

1) 默认 ``--check``（CI gate，推荐）：
   不写文件，仅校验「schema 中定义的每个顶层字段」与「关键嵌套字段」在当前签入的
   Pydantic 模型与 TS 类型中是否有对应声明，任何缺失即非零退出。这消除了历史上
   "schema 改了但产物没跟上" 的漂移（此前靠手工种子 + parity 测试守护）。

   校验范围：
   - 顶层：schema 根 properties 的每个字段（RobotContractV3）；
   - 嵌套：``$defs/observation``（components/normalizer/history_*/conditional_fields/
     recurrent_state）与 ``$defs/action``（dimension/joint_order/action_scale 等）
     的字段级表述——即 PolicyContract 观测字段级收敛的防漂移 gate。

   注：签入产物是经过人工对齐的等价实现（含中文注释与类型别名），并非
   json-schema-to-typescript / datamodel-code-generator 的机械输出；因此
   ``--check`` 做的是**语义字段覆盖校验**，而不是逐字节 diff。

   另：``--write`` 已在可联网环境用工具机械生成核对过（npx json-schema-to-typescript
   输出 /tmp/gen_ts.d.ts），字段与签入语义化版本一致；因格式差异不直接覆盖签入产物。

2) ``--write``（需要网络，一次性拉取工具）：
   在可联网、可验证的环境里用真实工具重新生成产物，供人工核对后手动同步。
   （机械生成与签入的语义对齐版本存在格式差异，不建议直接覆盖签入产物。）

用法：
  python tools/generate_contract_models.py            # check（默认）
  python tools/generate_contract_models.py --write    # regenerate to stdout/写盘
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "schema" / "robot-contract-3.0.schema.json"
PY_OUT = ROOT / "contracts" / "generated" / "robot_contract_v3.py"
TS_OUT = ROOT / "web" / "shared" / "generated" / "types.d.ts"

# 嵌套模型字段级校验：验证 schema $defs 的关键嵌套字段与 Pydantic/TS 子模型是否同步。
# 让 --check 不只守护顶层字段，还能守护 PolicyContract 字段级表述（观测组件/历史帧/
# 归一化/条件字段/循环状态）这类**嵌套字段**的同步防漂移。
# 结构：(schema_def_key, py_class, ts_interface, 需校验的字段清单或 None=全字段)
NESTED_CHECKS = [
    # $defs/observation 的关键字段（PolicyContract 字段级表述收敛）
    ("observation", "ObservationSpecV3", "ObservationSpecV3",
     ["kind", "components", "dimension", "normalizer",
      "history_length", "history_order", "history_reset",
      "conditional_fields", "recurrent_state"]),
    # $defs/action 的关键字段（含动作缩放）
    ("action", "ActionSpecV3", "ActionSpecV3",
     ["dimension", "joint_order", "reindex_from_model",
      "action_scale", "action_clip"]),
]


def _load_schema() -> dict:
    if not SCHEMA.exists():
        raise SystemExit(f"schema 不存在: {SCHEMA}")
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _top_level_fields(schema: dict) -> list[str]:
    """返回 schema 根 properties 的字段名（含 $ref 直连式）。"""
    props = schema.get("properties") or {}
    return list(props.keys())


def _collect_class_fields(py_text: str, class_name: str) -> set[str]:
    """提取 Pydantic 模型类中一行一字段的声明名（忽略 Optiona: t = ...）。"""
    fields: set[str] = set()
    # 匹配 class <Name>(_V3Model): 块内的 "    <field>: ..." 顶层字段
    pattern = re.compile(
        rf"class {re.escape(class_name)}\(.*?\):\n(.*?)(?=\nclass |\Z)",
        re.DOTALL,
    )
    match = pattern.search(py_text)
    if not match:
        return fields
    body = match.group(1)
    for line in body.splitlines():
        m = re.match(r"^    ([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
        if m:
            fields.add(m.group(1))
    return fields


def _collect_ts_interface_fields(ts_text: str, interface_name: str) -> set[str]:
    """提取 TS interface 的字段名。"""
    fields: set[str] = set()
    pattern = re.compile(
        rf"export interface {re.escape(interface_name)} \{{(.*?)\n\}}",
        re.DOTALL,
    )
    match = pattern.search(ts_text)
    if not match:
        return fields
    body = match.group(1)
    for line in body.splitlines():
        m = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*)\??:", line)
        if m:
            fields.add(m.group(1))
    return fields


def check() -> int:
    schema = _load_schema()
    top = _top_level_fields(schema)

    py_text = PY_OUT.read_text(encoding="utf-8")
    ts_text = TS_OUT.read_text(encoding="utf-8")

    # 根模型的类名 / interface 名
    py_root_classes = ["RobotContractV3"]
    ts_root_interfaces = ["RobotContractV3"]

    errors: list[str] = []
    for cls in py_root_classes:
        have = _collect_class_fields(py_text, cls)
        for field in top:
            if field not in have:
                errors.append(f"Pydantic {cls} 缺少 schema 顶层字段: {field}")
    for iface in ts_root_interfaces:
        have = _collect_ts_interface_fields(ts_text, iface)
        for field in top:
            if field not in have:
                errors.append(f"TS {iface} 缺少 schema 顶层字段: {field}")

    # 嵌套模型字段级校验（PolicyContract 字段级表述收敛）。
    defs = schema.get("$defs") or {}
    for def_key, py_class, ts_iface, fields in NESTED_CHECKS:
        schema_fields = (defs.get(def_key) or {}).get("properties") or {}
        py_have = _collect_class_fields(py_text, py_class)
        ts_have = _collect_ts_interface_fields(ts_text, ts_iface)
        for field in fields:
            if field in schema_fields and field not in py_have:
                errors.append(f"Pydantic {py_class} 缺少 schema $defs/{def_key} 字段: {field}")
            if field in schema_fields and field not in ts_have:
                errors.append(f"TS {ts_iface} 缺少 schema $defs/{def_key} 字段: {field}")

    if errors:
        print("契约产物漂移检测：未通过")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        f"契约产物一致性通过：schema 顶层 {len(top)} 个字段均已同步 "
        f"到 Pydantic ({', '.join(py_root_classes)}) 与 TS ({', '.join(ts_root_interfaces)})。"
    )
    return 0


_DATAMODEL_CMD = [
    "uvx", "datamodel-code-generator",
    "--input", str(SCHEMA.relative_to(ROOT)),
    "--input-file-type", "jsonschema",
    "--output", "/tmp/robot_contract_v3.py",
    "--output-model-type", "pydantic_v2.BaseModel",
]
_JSTS_CMD = [
    "npx", "--yes", "json-schema-to-typescript",
    str(SCHEMA.relative_to(ROOT)),
]


def write() -> int:
    """用真实工具重新生成（输出到 stdout 路径以人工核对，不覆盖签入产物）。"""
    print(">>> 注意：机械生成与签入的语义对齐版本存在格式差异，仅供人工核对，不覆盖签入产物。")
    if shutil.which("uvx"):
        print("+ datamodel-code-generator 生成 Python 模型（写 /tmp/robot_contract_v3.py）...")
        result = subprocess.run(_DATAMODEL_CMD, cwd=ROOT, check=False)
        if result.returncode != 0:
            print("datamodel-code-generator 失败，请手工核对 Python 产物")
            return result.returncode
    else:
        print("uvx 不可用，跳过 Python 生成。")

    if shutil.which("npx"):
        print("+ json-schema-to-typescript 生成 TS 类型（写 /tmp/gen_ts.d.ts）...")
        result = subprocess.run(_JSTS_CMD, cwd=ROOT, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr)
            return result.returncode
        Path("/tmp/gen_ts.d.ts").write_text(result.stdout, encoding="utf-8")
        print("  -> /tmp/gen_ts.d.ts")
    else:
        print("npx 不可用，跳过 TS 生成。")

    print("完成。请手工核对 /tmp 产物后，若有必要的语义字段更新请同步到签入文件。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="契约产物生成 / 防漂移一致性校验")
    parser.add_argument("--write", action="store_true", help="用真实工具重新生成（默认仅 check）")
    args = parser.parse_args()
    if args.write:
        return write()
    return check()


if __name__ == "__main__":
    sys.exit(main())
