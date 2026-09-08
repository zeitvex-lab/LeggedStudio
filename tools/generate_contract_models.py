"""从契约 schema 真值源再生成 Python / TypeScript 产物。

真值源：contracts/schema/robot-contract-3.0.schema.json
产物：
  - contracts/generated/robot_contract_v3.py   （datamodel-code-generator）
  - web/shared/generated/types.d.ts            （json-schema-to-typescript，经 npx）

用法（需要网络，一次性拉取工具）：
  uvx datamodel-code-generator \
      --input contracts/schema/robot-contract-3.0.schema.json \
      --input-file-type jsonschema \
      --output contracts/generated/robot_contract_v3.py \
      --output-model-type pydantic_v2.BaseModel

  npx --yes json-schema-to-typescript contracts/schema/robot-contract-3.0.schema.json \
      > web/shared/generated/types.d.ts

直接运行本脚本会探测这两个工具；不可用时打印上面的命令并退出——
签入的生成产物是与 schema 手工对齐的等价实现（含 parity 测试守护），
改动 schema 后必须同步两个产物并跑 contracts 测试。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "schema" / "robot-contract-3.0.schema.json"
PY_OUT = ROOT / "contracts" / "generated" / "robot_contract_v3.py"
TS_OUT = ROOT / "web" / "shared" / "generated" / "types.d.ts"

DATAMODEL_CMD = [
    "uvx", "datamodel-code-generator",
    "--input", str(SCHEMA.relative_to(ROOT)),
    "--input-file-type", "jsonschema",
    "--output", str(PY_OUT.relative_to(ROOT)),
    "--output-model-type", "pydantic_v2.BaseModel",
]
JSTS_CMD = [
    "npx", "--yes", "json-schema-to-typescript",
    str(SCHEMA.relative_to(ROOT)),
]


def main() -> int:
    if not SCHEMA.exists():
        print(f"schema 不存在: {SCHEMA}")
        return 1

    if shutil.which("uvx"):
        print("+ datamodel-code-generator 生成 Python 模型 ...")
        result = subprocess.run(DATAMODEL_CMD, cwd=ROOT, check=False)
        if result.returncode != 0:
            print("datamodel-code-generator 失败，请手工核对 Python 产物")
            return result.returncode
    else:
        print("uvx 不可用，跳过 Python 生成：", " ".join(DATAMODEL_CMD))

    if shutil.which("npx"):
        print("+ json-schema-to-typescript 生成 TS 类型 ...")
        result = subprocess.run(JSTS_CMD, cwd=ROOT, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr)
            return result.returncode
        TS_OUT.parent.mkdir(parents=True, exist_ok=True)
        TS_OUT.write_text(result.stdout, encoding="utf-8")
    else:
        print("npx 不可用，跳过 TS 生成：", " ".join(JSTS_CMD))

    print("完成。请运行 contracts 测试核对 parity。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
