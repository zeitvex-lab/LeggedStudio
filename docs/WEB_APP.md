# Web 工作台说明（Web Workbench）

后端 `/health` 校验通过后，浏览器进入 `http://127.0.0.1:<port>/` 的 Web 工作台。这是全部业务功能的所在；桌面启动器只负责生命周期（见 [DESKTOP_APP.md](DESKTOP_APP.md)）。

## 两种界面形态

工作台有两套连通的界面：

1. **主工作台壳**（`web/workbench.html` + `workbench.js`，默认入口 `/`）：七步导航条（home / validate / config / training / simulation / settings / navmap），内嵌视图承载训练配置页与监控页，首页显示服务、运行时、适配器、资产状态和最近实验。
2. **传统多页控制台**（`dashboard.html` 及其链接的各页）：刻意保留的后备入口，供桌面启动器和外部浏览器链接直达（如 `training_create.html?embedded=1`）。两套界面共享同一套后端 API 与静态资源。

主入口路由：`/` → workbench.html；`/sim2sim/` → 浏览器仿真页（StaticFiles html 模式）。

## 五个功能区

| 区 | 页面 | 功能 |
| --- | --- | --- |
| 首页 | workbench 首屏 | 服务/运行时/适配器/资产状态、最近实验、项目 ZIP 包导出/导入、包管理入口 |
| 验证 | workbench validate 视图 + `urdf-viewer.js` | Robot Contract / 场景参数 / 资产检查；惯量盒可视化、质量/惯量表、分段电机参数卡（Kp/Kd/力矩/速度限制）；URDF/MJCF + 相对 mesh 导入生成 Contract 草稿 |
| 训练配置 | 内嵌 `training_create.html` | 五分类模块化编辑器：框架选择（MJLab 可用、UniLab 规划中）、精选参数卡片、专家模式 dot-path 覆盖完整内省配置树；JSON 导入/导出 |
| 训练 | 内嵌 `training_list.html` → `training_monitor.html` | 任务列表/创建/停止；wandb 风格监控：三段式概览侧栏、指标小倍数网格、检查点面板、日志过滤 |
| 仿真 | 内嵌 `/web/sim2sim/index.html` | MuJoCo 交互遥控（键盘 WASD + QE 已验证）、地图切换、导航会话、浏览器 sim2sim 策略回放 |
| 设置 | 内嵌 `settings.html` | 运行环境与工作区设置：GPU/CPU profile 切换与重装、后端端口、Python 覆盖、包镜像源（清华/交大/官方）、工作区清理 |
| 地图 | 内嵌 `navigation_editor.html` | 交互式导航地图编辑器：画障碍/设航点 → A*/Dijkstra 自动求路，与场景/地图库打通，可保存自定义地图 |

## 浏览器 sim2sim（重点子系统）

`web/sim2sim/` 是完全在浏览器本地运行的策略回放环境：

- **技术栈**：MuJoCo WASM + Three.js + ONNX Runtime Web（`vendor/` 下离线打包，约 25MB，无 CDN 依赖）。
- **数据流**：启动时把所选机器人包的 MJCF 与网格拷入 WASM 虚拟文件系统，随后物理推进和渲染每帧都在浏览器本地完成；后端只提供静态文件与 `browser-config` 数据。
- **实机合同对齐**：逐腿+轮关节布局、默认姿态、PD/低通参数、ONNX 输入输出顺序与训练侧一一对应；每机器人内置地形（Go2 六场景、ZEX-W flat/rough/stairs/slope、MicroDuck flat/浮雕围栏场/apartment）。
- **策略元数据校验**：加载 ONNX 时读取 `metadata_props` 盖章（`joint_names`/`joint_stiffness`/`default_joint_pos` 等）并与机器人契约比对——不一致会显示"元数据不匹配"但不阻断加载。
- **确定性回放**：`?replay=<vx>,<vy>,<wz>&seed=N` 支持固定指令回放，是"验收器通过但回放视觉不通过 = 没学会"教条的执行环节。
- **跨域隔离头**：`/web/sim2sim` 响应自动带 COOP/COEP/CORP 头以启用 SharedArrayBuffer（pthread 版 MuJoCo WASM 必需）。
- **缓存策略**：Web 资源 ETag 协商缓存（`Cache-Control: no-cache`），改动即失效、未改动 304，兼顾开发刷新与大资源体积。

## 02 验证页的 3D 模型查看器（urdf-viewer）

`web/urdf-viewer.js` 提供验证页的 Three.js 模型预览（外观/碰撞/惯性/质心/关节轴分层开关）：

- **碰撞体可视化**：开"碰撞"开关时，视觉 mesh 自动降为 ~28% 透明，让内部碰撞体（通常是嵌在实心外壳里的小圆柱/球）透出；关掉恢复完整不透明度。这对 TRON1 这类实心外壳机器人是必须的——否则碰撞体被完全不透明外壳完全遮挡，看起来"没有碰撞体"。
- **MJCF 解析注意**：`class="collision"` 的碰撞体被正确识别；但**嵌套 default class 的继承**（如 go2 的 `class="foot"` 嵌在 collision 内）在 urdf-viewer 里解析不可靠，因此足端球必须在模型里显式给 `size/group/contype`；碰撞姿态用 `quat`（MuJoCo wxyz）而非 `euler`。
- **碰撞体来源**：优先官方 URDF/MJCF 的标准 primitive（rl_sar_zoo、LeggedGym-Ex），已对齐 lite3/a1/TRON1/d1/go2。

## 后端 API 概览

控制面入口 `backend/api_complete.py`（FastAPI），关键端点：

| 用途 | 端点 |
| --- | --- |
| 健康与身份 | `GET /health` |
| 系统能力/环境/适配器状态 | `GET /api/system/capabilities` 等 |
| 资产清单 | `GET /api/assets/summary` |
| 机器人包（presets/导入/刷新/删除） | `GET /api/robots/presets`、`POST /api/robots/packages/refresh` |
| 模型导入/验证/预览 | `POST /api/models/import` / `validate` / `preview` |
| 浏览器仿真配置 | `GET /api/simulation/browser-config/{robot_id}` |
| 项目 ZIP 导入/导出 | `POST /api/project/export` / `import` |
| 训练选项/任务 | `GET /api/training/options`、`POST /api/training/create`、`GET /api/training/list` |
| 配置内省 | `GET /api/training/config-preview`、`/api/training/profile-schema` |
| 场景校验 | `POST /api/scenarios/validate` |
| 交互式 API 文档 | `GET /docs` |

完整清单见 `backend/README.md`；训练 worker 侧约定见 `adapters/mjlab/README.md`。

## 约定

- 前端为无构建步骤的原生 JS/HTML/CSS（版本号查询参数做缓存失效，如 `workbench.js?v=0.7.0`），完全离线可用。
- 视觉基线为 MJLab Play/Viser 风格的浅色工作区（白色/浅灰场景、蓝色主操作、灰色边框）。
- 所有页面与后端通信走同一套 HTTP 路由——CLI（`scripts/legged_studio_cli.py`）与前端共用，保证语义一致。
- 浏览器仿真中每一步观测/动作的语义必须与桌面验收器（`adapters/mjlab/policy_acceptance.py`）逐项一致；两侧观测构建器的差异是已知高危区，修改任一侧时同步另一侧。
