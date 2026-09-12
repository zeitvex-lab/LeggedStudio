# 云原生开发环境

点仓库页面的 **「Legged Studio 开发」** 按钮，即可获得一个开箱即用的在线开发环境：

- 依赖（`backend/requirements.txt` + `onnxruntime`）已固化在镜像里，**每次进入都不用重新配环境**；
- Chromium + Playwright 预装，浏览器 sim2sim 可直接看、可直接截图；
- 后端在 `0.0.0.0:8765` 自动拉起。

## 入口与预览地址

| 用途 | 地址 |
|---|---|
| 工作台 | `${CNB_VSCODE_PROXY_URI/\{\{port\}\}/8765}/web/workbench.html` |
| sim2sim | `${CNB_VSCODE_PROXY_URI/\{\{port\}\}/8765}/web/sim2sim/index.html` |
| API 文档 | `${CNB_VSCODE_PROXY_URI/\{\{port\}\}/8765}/docs` |

`CNB_VSCODE_PROXY_URI` 形如 `https://xxx-{{port}}.cnb.run`，把 `{{port}}` 换成 `8765`。
也可以在 WebIDE 的 **PORTS** 面板手动添加 `8765` 端口映射。

> 服务必须监听 `0.0.0.0`（不能是 `127.0.0.1`），否则预览 URL 打不开。
> 后端已按此启动，无需手工调整。

## 环境结构

```
.ide/Dockerfile      # 唯一环境事实源：云原生开发与 CI 共用同一镜像
.cnb.yml  $: vscode  # 启动流程：起后端 + 打印预览地址（不做重复安装）
.cnb/settings.yml    # 入口按钮名称 / CPU 核数 / 自动打开 WebIDE
```

依赖与浏览器都在镜像层，`stages` 里**不放安装命令**，所以进入环境是秒级的。

## 浏览器验证（浏览器是刚需）

`?debug=1` 会暴露一套调试 API，供人肉排查与自动化截图调试复用：

| API | 作用 |
|---|---|
| `window.__sim2simDebug.state()` | 模型/几何/状态的完整快照 |
| `window.__sim2simDebug.sample()` | 单帧物理+策略状态（基座高度、姿态、指令） |
| `window.__sim2simDebug.fastForward(seconds)` | 同步快进仿真（墙钟远快于实时） |
| `window.__sim2simDebug.setPaused(bool)` | 暂停/恢复渲染循环 |
| `window.__probe` | 渲染循环持续写入的骨盆高度/动作探针 |

确定性回放：`?replay=vx,vy,wz&seed=N` —— 同一策略 + 模型 + seed
在任何机器上回放出同一条轨迹，因此**截图可以直接当回归判据**。

### E2E 测试

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt
playwright install chromium
pytest tests/e2e -v
```

用例覆盖：页面加载 + 调试探针可用、确定性回放两次采样一致、回放 2 秒不摔并落截图
（截图写到 `workspace/e2e-screenshots/`，可直接读图判断策略行为）。

## 与 CI 的关系

云原生开发与云原生构建底层是同一套引擎，这里共用 `.ide/Dockerfile`，
所以「开发环境里能跑通的」和「CI 里跑的」是同一套依赖，不会出现环境漂移。

| CI 任务 | 内容 |
|---|---|
| `backend-test` | 语法、契约漂移、单测、**openapi 契约冒烟**、移植准入、Pack 校验 |
| `headless-sim2sim-gate` | 47 条策略的 CPU 无头验收，对照基线只拦**新增退化** |
| `frontend-check` | web JS 语法 + vendor 资产冒烟 |

基线文件：`tools/baselines/sim2sim_headless_baseline.json`。
仓库现存 3 条既存失败（go2 特技/跑酷量化判据未过）已记录在基线里，
门禁只守「不许新增失败」。刷新基线：

```bash
python tools/sim2sim_headless.py --seconds 3 --write-baseline tools/baselines/sim2sim_headless_baseline.json
```
