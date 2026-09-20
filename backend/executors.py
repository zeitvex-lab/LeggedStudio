"""Executor 抽象（H2）：**同一份 Scenario，两个执行器**。

愿景口径（`02` §2.4 / `06` §5）：WASM 与服务端 MuJoCo 是同一 Scenario 的两个 executor，
"服务器仿真"不是一个独立概念。本模块把这句话变成**可核对的数据 + 一个纯函数**：

* :data:`EXECUTORS` —— 两个执行器及其**能力矩阵**。**每条能力都挂锚点**（服务端挂路由路径、
  浏览器挂 URL 参数或页面控件），由 `backend/test_executors.py` 回真源核对（路由不在
  `app.openapi()` 里、参数不在 `app.js` 里，测试就红）。
* :func:`select_executor` —— 按场景挑执行器；**挑不出来就如实说缺什么**（fail-closed），
  而不是"随便挑一个跑跑看"。

## 为什么必须有这个模块（而不是继续散着）

两个执行器**不是功能对等的两套**，各自侧重不同（实测）：

| | 服务端 MuJoCo | 浏览器 WASM |
|---|---|---|
| 输入 | `scenario` **全载荷**（`ScenarioContract`） | URL 参数（由 scenario 推导） |
| 驱动 | **指令/动作驱动**（`command` / `action`），**会话内不做策略推理** | **策略推理**（ONNX in WASM）+ 手动指令 |
| 渲染 | 离屏（`/render`，需 GL 后端） | 实时（页面） |
| 确定性 | `seed` | `seed` + `replay` 确定性回放 |

"策略推理只在浏览器侧"这条差异以前只存在于人脑里：写文档的说"两端都能跑同一 Scenario"，
真去服务端会话里找策略推理却找不到。**抽象的价值就是把这类差异写下来并让机器守住。**

## 缺口（本模块刻意暴露）

契约允许的取值里，有**两个执行器都不支持**的（见 :data:`UNSUPPORTED_CONTRACT_OPTIONS`）。
不把它们藏起来：`select_executor` 会明确拒绝并给理由，测试也会要求"契约新增取值时必须同时
表态"—— 这样"契约支持、但没人能跑"不会被误当成"支持"。
"""

from __future__ import annotations

from typing import Any

#: 两个执行器。能力矩阵里的 `anchors` 是**回真源核对用**的标记（不是文档链接）：
#: `route:` 前缀 ⇒ 必须在 FastAPI 的 `app.openapi()["paths"]` 里；`param:` ⇒ 必须在
#: `web/sim2sim/app.js` 的 `PAGE_PARAMS.get(...)` 里；`dom:` ⇒ 必须在 `web/sim2sim/index.html` 里。
EXECUTORS: tuple[dict[str, Any], ...] = (
    {
        "id": "server_mujoco",
        "label": "服务端 MuJoCo（无头）",
        "kind": "server",
        "entrypoint": "POST /api/simulation/sessions",
        "scenario_input": "scenario（ScenarioContract 全载荷，直接进请求体）",
        "mode": "会话式：create → step… → close",
        "anchors": (
            "route:/api/simulation/sessions",
            "route:/api/simulation/sessions/{session_id}/step",
            "route:/api/simulation/sessions/{session_id}/reset",
            "route:/api/simulation/sessions/{session_id}/render",
        ),
        "supports": {
            "command_sources": ("planner", "script"),
            "perception_routes": ("external",),
            "live_render": False,
            "offscreen_render": True,
            "policy_inference": False,
            "deterministic_replay": True,
        },
        "limitations": (
            "**会话内不做策略推理**：`step` 吃 `command`（任意 vx/vy/wz）或 `action`（直接关节动作）；"
            "ONNX 推理走另一条链（POST /api/simulation/policies/acceptance 的验收评估）。",
            "离屏渲染依赖 GL 后端（EGL/OSGB），无显示环境时按 backend/gl_env.py 的规则降级。",
        ),
    },
    {
        "id": "browser_wasm",
        "label": "浏览器 MuJoCo WASM",
        "kind": "browser",
        "entrypoint": "web/sim2sim/index.html（可经 web/advanced_sim.html 的 Scenario 编辑器启动）",
        "scenario_input": "URL 参数（由 scenario 推导：web/sim2sim/scenario_editor.js::toSimParams）",
        "mode": "实时：页面内每帧推进",
        "anchors": (
            "param:robot",
            "param:policy",
            "param:terrain",
            "param:seed",
            "param:nav",
            "param:nav_waypoints",
            "param:replay",
            "dom:velCmdEnable",
            "dom:playButton",
        ),
        "supports": {
            "command_sources": ("policy", "teleop", "planner"),
            "perception_routes": ("external", "obs"),
            "live_render": True,
            "offscreen_render": False,
            "policy_inference": True,
            "deterministic_replay": True,
        },
        "limitations": (
            "**没有脚本化指令序列**（`command_source=script`）：页面给的是手动档（cruise-speed 按钮 /"
            " 速度指令面板），没有\"按时间轴回放一串指令\"的入口。",
            "离屏渲染没有（渲染即页面；要出帧走服务端 `/render`）。",
        ),
    },
)

#: 契约里**合法但没有执行器**的取值（`ScenarioContract.command_source` 的 Literal）。
#: 逐项说明"为什么现在没人跑"：不写下来，它就会被当成"支持"。
UNSUPPORTED_CONTRACT_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "field": "command_source",
        "value": "perception",
        "why": "感知决策（B 类）要求外部模块输出目标/分段，两端都还没有该编排（H2 的抽象先把缺口标出来，不假装支持）。",
    },
)

#: 契约 `command_source` 的全部合法取值（与 `contracts/scenario_contract.py` 的 Literal 同源）。
#: **抄一份在这里是有代价的**（两处要同步），所以测试会拿它跟契约比对：契约新增取值而这里没跟 ⇒ 红。
CONTRACT_COMMAND_SOURCES: tuple[str, ...] = ("policy", "planner", "perception", "script", "teleop")


def executor(executor_id: str) -> dict[str, Any]:
    for item in EXECUTORS:
        if item["id"] == executor_id:
            return item
    raise KeyError(f"未知 executor：{executor_id!r}（可选：{[item['id'] for item in EXECUTORS]}）")


def _support_gaps(scenario: dict[str, Any], target: dict[str, Any]) -> list[str]:
    """这个执行器跑不了该场景的**具体原因**（空列表 = 支持）。"""

    supports = target["supports"]
    gaps: list[str] = []
    sources = supports["command_sources"]
    command_source = str(scenario.get("command_source") or "")
    if command_source and command_source not in sources:
        gaps.append(
            f"command_source={command_source!r} 不在 {target['id']} 的 {list(sources)} 内"
        )
    perception = scenario.get("perception") or None
    if isinstance(perception, dict):
        route = str(perception.get("route") or "external")
        if route not in supports["perception_routes"]:
            gaps.append(f"perception.route={route!r} 不在 {target['id']} 的 {list(supports['perception_routes'])} 内")
    return gaps


def select_executor(
    scenario: dict[str, Any] | None, *, prefer: str | None = None, require: tuple[str, ...] = ()
) -> dict[str, Any]:
    """按场景挑执行器（纯函数）。**挑不出来就拒绝**，并列出每个执行器缺什么。

    * ``prefer`` 指定的执行器**支持**该场景时优先选它；不支持则退回按能力选（并说明 prefer 为何落选）。
    * ``require`` 是额外硬要求（能力名，如 ``"offscreen_render"``）：不满足的执行器直接出局。
    * 返回值形状稳定：``{"ok", "executor", "reasons", "considered", "unsupported_contract_options"}``。
    """

    payload = scenario or {}
    considered: list[dict[str, Any]] = []
    for target in EXECUTORS:
        gaps = _support_gaps(payload, target)
        missing = [name for name in require if not target["supports"].get(name)]
        gaps.extend(f"缺能力 {name}" for name in missing)
        considered.append({"id": target["id"], "ok": not gaps, "gaps": gaps})

    usable = [item for item in considered if item["ok"]]
    reasons: list[str] = []
    if prefer:
        preferred = next((item for item in considered if item["id"] == prefer), None)
        if preferred is None:
            raise KeyError(f"未知 executor：{prefer!r}")
        if preferred["ok"]:
            chosen = preferred
        else:
            chosen = next((item for item in usable if item["id"] != prefer), None)
            reasons.append(f"prefer={prefer!r} 不支持该场景：{preferred['gaps']}，已按能力改选")
    else:
        # 无偏好时的确定性顺序：策略驱动/交互场景优先浏览器（唯一能做策略推理的），
        # 其余优先服务端（可脚本化、可离屏）。
        wants_policy = str(payload.get("command_source") or "") == "policy"
        order = ["browser_wasm", "server_mujoco"] if wants_policy else ["server_mujoco", "browser_wasm"]
        chosen = next((item for item in usable if item["id"] == order[0]), None) or next(iter(usable), None)

    if chosen is None:
        reasons.append("没有任何执行器能跑这份场景")
    return {
        "ok": chosen is not None,
        "executor": executor(chosen["id"]) if chosen else None,
        "reasons": reasons,
        "considered": considered,
        "unsupported_contract_options": [dict(item) for item in UNSUPPORTED_CONTRACT_OPTIONS],
    }


def describe() -> dict[str, Any]:
    """执行器矩阵摘要（稳定形状，供文档/页面读）。"""

    return {
        "schema": "executor-matrix-1.0",
        "executors": [dict(item) for item in EXECUTORS],
        "unsupported_contract_options": [dict(item) for item in UNSUPPORTED_CONTRACT_OPTIONS],
        "contract_command_sources": list(CONTRACT_COMMAND_SOURCES),
    }
