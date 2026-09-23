# `.cnb/mcp/` — Legged Studio 的开发期 MCP 工具链

> **定位**：MCP server 是**开发期工具**，不是运行期依赖。因此**不预装进环境**，
> 而是随仓库走，由云原生开发环境（`.cnb.yml` 的 `vscode` 事件）读 `servers.json` 装配。
> `npx` / `uvx` 两个 runner 底座由 CNB 默认镜像提供，本仓不再自建镜像。

配置入口：[`servers.json`](./servers.json)（标准 `mcpServers` 结构，任意支持 MCP 的客户端可直接引用）。

---

## 一、为什么是这 11 条

选型标准只有一条：**每条都必须对着本仓一个真实痛点，并留下文件级落点**。
凡是「别的项目也装了所以我们也装」的一律不收（见 §四 放弃清单）。

### 通用系（6）

| MCP | 解决什么 | 本仓落点 |
|---|---|---|
| `filesystem` | 工作区文件读写 | `backend/settings_api.py` 的工作区解析；`assets/robots/*` 契约与模型批量核对 |
| `git` | diff / log / blame | 云原生开发里全靠手敲；PR 与 `00_know/05_任务清单.md` 需要真实提交证据 |
| `github` | 上游项目检索 | `tools/sync_resources.py::PROJECTS` 的 89 个项目溯源；`registry/porting_evidence.json` |
| `fetch` | 抓上游文档 | 官方部署协议/README 真值核对（进度流水里反复出现的「以官方仓为权威」） |
| `playwright` | **本仓最刚需** | `web/sim2sim` 的全部结论都是浏览器实测（lite3 yaw −0.25°、m20 前进 3.9 m）；镜像已预装 Chromium |
| `sqlite` | run 元数据查询 | `backend/training/artifacts.py` 的 `runs/<id>/`；`workspace/` 产物 |

### 机器人专用系（5）

| MCP | 解决什么 | 本仓落点 |
|---|---|---|
| `tensorboard` | 训练诊断曲线 | `backend/tb_events.py`、`web/training_monitor.html` 五大仪表盘 |
| `mujoco` | 加载 MJCF / 查关节序 / 跑无头稳定测试 | `tools/sim2sim_headless.py`、`adapters/mjlab/scene_builder.py` |
| `onnx` | 查模型输入输出维 / 单帧推理对拍 | `tools/evaluator.py`、60 份 `sim_policies_onnx`（59 条策略声明）契约核验 |
| `resources` | `00_resources` 跨库检索 | `00_resources/README.md`、`tools/sync_resources.py` |
| `contracts` | 契约真值 查询与校验 | `contracts/`、`backend/pack_catalog.py`、`assets/robots/*/contract.json` |

后 4 条是**本仓自研 server**，实现在 [`../../tools/mcp/`](../../tools/mcp/)：

```
tools/mcp/
├─ mujoco_server.py      # load_mjcf / list_joints / stability_probe
├─ onnx_server.py        # inspect_model / infer_once / compare_io
├─ resources_server.py   # search_projects / list_robots / project_files
└─ contracts_server.py   # get_contract / list_joints / verify_pack
```

---

## 二、本地接入

```bash
# 通用系（需要网络，首次拉取稍慢）
npx -y @modelcontextprotocol/server-filesystem /workspace
uvx mcp-server-git --repository /workspace
uvx mcp-server-fetch

# 机器人专用系（零额外依赖：控制面 requirements.txt 已含 mujoco 与 onnxruntime）
python -m tools.mcp.mujoco_server       # 走 stdio
python -m tools.mcp.contracts_server
```

把 `servers.json` 的 `mcpServers` 段整段贴进客户端的 MCP 配置即可；
`${GITHUB_TOKEN}` 是唯一需要自备的环境变量（不填则 `github` 这条降级不可用，其余不受影响）。

它与**发布镜像**用的是**同一个 PAT** —— 都存在密钥仓库 [`zeitvex/github-secrets`](https://cnb.cool/zeitvex/github-secrets/-/blob/main/github-secrets.yaml) 里，由 `.cnb.yml` 的 `.github-mirror` 锚点经 `imports` 注入到发布流水线。
开发环境里这份不会自动注入（`imports` 只覆盖流水线），要用时自己 `export GITHUB_TOKEN=...`，
或在个人环境变量里配一份 —— 见 [`docs/cloud-dev.md`](../../docs/cloud-dev.md) 的「自动上传 GitHub」一节。

---

## 三、云原生开发环境里怎么用

`.cnb.yml` 的 `vscode` 事件在起后端之后，会：

1. 打印 `servers.json` 的绝对路径，方便 WebIDE 的 MCP 面板一键引用；
2. 做一次 `python -m tools.mcp.*_server --selftest`，确认自研 server 可导入（防止镜像里少了依赖却到用的时候才发现）。

> 自研 server **不引入新依赖**（只用 `mujoco` / `onnxruntime` / 标准库），
> 因此 `backend/requirements.txt` 不变，`.cnb.yml` 的 `by` 清单也不用改。

---

## 四、明确不做的两条（取舍理由）

| 不做 | 为什么 |
|---|---|
| 真机部署 / CAN 总线 MCP | 真机走桌面形态（`electron/launcher/`），容器里的 agent 够不到硬件，装了是摆设 |
| 仿真编排 MCP | 后端自己就是仿真编排者（`backend/simulation_api.py`），agent 直连 HTTP API 更直接，套一层 MCP 是多余抽象 |
