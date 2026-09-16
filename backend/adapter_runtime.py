"""适配器运行时的**单一实现**：怎么找到能跑 mujoco 的解释器，怎么在它里面跑一个脚本。

## 为什么要有它

"跑 mujoco 的 python 在哪"此前散在三处、各写一套：

* `backend/simulation_api.py`（验收评估：找到就用，找不到**静默退回当前解释器**）；
* `tools/replay_gate.py`（确定性回放：`--venv` > 环境变量 > path_bootstrap > 当前解释器，**要过探测**）；
* B11 的八指标评测也要一份。

三套的差别不是风格问题：**静默退回**会把"环境没准备好"伪装成 `ImportError`；而**不探测**会把
"解释器存在但没装 mujoco"当成可用环境。这里统一成一条，并写死判据：

1. 候选顺序：显式参数 > `LEGGED_STUDIO_MJLAB_VENV` > `contracts.path_bootstrap.adapter_python` > 当前解释器；
2. **每个候选都要过 `import mujoco` 探测**（当前解释器也是候选之一 —— CI 的验收作业就是裸 python
   直跑 MuJoCo）；
3. 全都不行 ⇒ 抛出带**可执行修法**的异常，调用方把它变成 501/blocked 之类的如实状态，
   **绝不退回一个跑不了的解释器**。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class AdapterUnavailable(RuntimeError):
    """找不到能跑 mujoco/onnxruntime 的解释器（或脚本执行失败）。"""


def adapter_interpreter(explicit: Path | str | None = None, *, probe: str = "import mujoco, onnxruntime") -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("LEGGED_STUDIO_MJLAB_VENV")
    if env:
        candidates.append(Path(env))
    try:
        from contracts.path_bootstrap import adapter_python

        candidates.append(Path(adapter_python(default=ROOT / "adapters" / "mjlab" / ".venv")))
    except Exception:
        pass
    candidates.append(Path(sys.executable))

    considered: list[str] = []
    for candidate in candidates:
        for python in (candidate, candidate / "bin" / "python", candidate / "Scripts" / "python.exe"):
            if not python.is_file():
                continue
            considered.append(str(python))
            completed = subprocess.run([str(python), "-c", probe], capture_output=True, text=True)
            if completed.returncode == 0:
                return python
    raise AdapterUnavailable(
        "找不到可用的适配器解释器（需要能 import mujoco/onnxruntime）。候选：" + (", ".join(considered) or "（无）")
        + "。修法：设 LEGGED_STUDIO_MJLAB_VENV=/path/to/adapter/venv，或把 --venv 指到 venv 目录/解释器"
    )


def run_json_script(
    script: Path | str,
    args: list[str],
    *,
    interpreter: Path | str | None = None,
    timeout: float = 900.0,
    cwd: Path | str | None = None,
) -> dict[str, Any]:
    """在适配器解释器里跑一个**输出 JSON 到 stdout** 的脚本，返回解析后的对象。

    失败时抛 :class:`AdapterUnavailable`（带 stderr 末尾若干行）—— 调用方据此记 blocked/501，
    而不是拿一堆噪声当日志。
    """

    python = adapter_interpreter(interpreter)
    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = ROOT / script_path
    command = [str(python), str(script_path), *[str(item) for item in args]]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=str(cwd or ROOT))
    except subprocess.TimeoutExpired as exc:
        raise AdapterUnavailable(f"适配器脚本超时（>{timeout:.0f}s）：{script_path.name}") from exc
    if completed.returncode not in (0, 1):
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-6:]
        raise AdapterUnavailable(f"适配器脚本失败（exit={completed.returncode}）：" + " | ".join(tail))
    raw = (completed.stdout or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        tail = (completed.stderr or "").strip().splitlines()[-4:]
        raise AdapterUnavailable(f"适配器脚本输出不是 JSON：{exc}（stderr: {' | '.join(tail)}）") from exc
