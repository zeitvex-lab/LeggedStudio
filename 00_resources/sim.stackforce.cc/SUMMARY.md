# sim.stackforce.cc 抓取报告（StackForce SimReady）

> 抓取时间：2026-09-08 · 工具：curl + Python（礼貌限速 0.4s）· 仅公开资源，未做任何鉴权绕过

## 一、站点概况

**StackForce SimReady**（标题同站名）——一个将 URDF 转换为 **Isaac Lab / Isaac Gym 训练起始工程**的在线 Sim2Sim 平台（Meta 描述原文："将 URDF 转换为 Isaac Lab/Gym 训练起始工程。"）。站点设置 `X-Robots-Tag: noindex, nofollow`，CSP `frame-ancestors 'self' https://workbench.stackforce.cc`，说明它被设计为嵌入 workbench.stackforce.cc 中使用。

关联子域（页面外链，未深度抓取）：
- `https://urdf.stackforce.cc/` — "StackForce Robot URDF Builder"（在线建模机器人，Vite 构建的 SPA）

## 二、抓取统计

- **文件总数：219 个，总大小 179 MB**（另含本报告与爬虫脚本/日志）
- 保存布局：`sim.stackforce.cc/sim.stackforce.cc/` 下保留 URL 路径结构（内层目录为上阶段脚本所建，未重构以保持一致性）

| 类型 | 数量 | 说明 |
|---|---|---|
| STL 网格 | 131 | 机器人 mesh（10.5MB~ 数百 KB 不等） |
| DAE 网格 | 33 | Collada 视觉网格（含 9.2MB 的 anymal_b base） |
| MD 占位 | 19 | 按要求为未下载的 URDF/mesh 建的占位说明 |
| JS | 17 | Next.js 前端全部 chunk（含 polyfills） |
| URDF | 8 | go1/go2/aliengo/b2/anymal_b/g1/xbot_l/qmini 等 |
| 环境脚本 | 3 | API 导出的 Isaac Lab / Isaac Gym / MJLab 环境配置 bash |
| 其它 | 8 | css、ico、png、jpg、robots.txt、_buildManifest、_ssgManifest 等 |

## 三、技术栈分析

| 项 | 结论 |
|---|---|
| 框架 | **Next.js（Pages/混合 Router，`__rewrites` 存在但 sortedPages 仅 /_app、/_error）**，`x-nextjs-cache: HIT` 表明服务端渲染/ISR |
| 前端 UI | **React**（jsx 运行时、webpackChunk_N_E），CSS 单文件 153KB（含完整设计系统） |
| 3D 渲染 | **Three.js r175/r172/r163 多版本 loader 痕迹（STLLoader、OBJLoader、ColladaLoader）** |
| 代码保护 | 主 page chunk（370KB）经 **javascript-obfuscator 混淆**（`_0x1c99b2(0x145)` 十六进制字符串表） |
| 后端 | Next.js API Routes（`/api/export/environment-script`），nginx 反代 |
| Source maps | **全站不存在**（全部 JS/CSS 的 `.map` 均 404）；混淆+无 map，原始源码不可还原 |

### 前端代码结构（已全部下载，位于 `_next/static/chunks/`）

- `webpack-05254f693c87e932.js` — runtime：懒加载映射只有 **595/726/813** 三个 chunk（均已下载），入口 chunk 272/587 内联在页面（即 index.html 已引用的 11 个文件即全部）
- `app/page-436aa2d611eaef8a.js`（370KB）— 主应用（混淆）
- `595` — URDF 解析/策略运行时（`GenericPolicyRuntimeController`、关节名 FL_hip_joint 等）
- `726` — Three.js 相关（Collada/STL/OBJ loader、ColorManagement）
- `813` — **训练工程导出器**（`Mjlab-Velocity-Flat-`、`action_dim`、`reward_scales`（action_rate_l2、angular_momentum 等）、`README.md` 模板、`actuatorMode`、`Closed-chain USD / Isaac Lab / Isaac Sim`）
- 内嵌导出工程命名：`setup_stackforce_isaac_lab_sim_env.sh` / `setup_stackforce_isaac_gym_env.sh` / `stackforce_mjlab_env.ps1`

### 版本矩阵（从混淆 JS 与导出脚本中提取）

| 环境 | 组件版本 |
|---|---|
| Isaac Lab | Isaac Sim 5.1.0 · Isaac Lab v2.3.2 (pip 2.3.2.post1) · Python 3.11 · Torch 2.7.0 cu128 · rsl_rl（LeggedGym-Ex 捆绑版） |
| Isaac Gym | Preview 4 / 1.0rc4 · Python 3.8 · Torch 2.4.1 cu121 |
| MJLab | Python 3.12 · mjlab 1.5.3 · MuJoCo 3.10.x · rsl_rl 5.4.0 · CPU smoke 支持 |

## 四、API 端点

| 端点 | 方法 | 状态 | 说明 |
|---|---|---|---|
| `/api/export/environment-script?target={isaac_lab\|isaac_gym\|mjlab}` | GET | 200 | 导出训练环境 bootstrap 脚本；响应头 `X-SimReady-File-Name` 携带文件名。三个脚本已存档于 `sim.stackforce.cc/api_snapshots/` |
| 其它 target 值 | GET | 400 | `{"error":"Unsupported environment script target."}` |

页面渲染过程中未发现其它后端 API 调用或 WebSocket——机器人 URDF/mesh 全部为**静态文件直链**（`/examples/robots/...`），推理控制（`GenericPolicyRuntimeController`）在浏览器本地运行。

## 五、机器人资源清单（25 个内置机器人）

**已下载（9 个，含 URDF+网格）**：go1、go2（dae 目录）、aliengo、b2、anymal_b、g1（mesh 404）、xbot_l（86 文件最全）、robotamer_qmini、gr1

**按要求仅建占位（16 个，见各目录 `_NOT_DOWNLOADED_占位.md`）**：宇树A1、anymal_c、逐际带脚底板双足、逐际点足、逐际轮足、lite3、x30、solo12、12自由度菠萝狗、菠萝狗、SF双足带脚底板、SF双足点足、SF大轮足、SF小轮足、SF舵机四轮足、anymal-softfoot-q（闭链USD）、simplified-quadruped（闭链USD）

**部分缺失**：g1_description 的 27 个 STL 服务器 404；go2 的 base.dae/thigh_mirror.dae 传输中断

URL 模式：`https://sim.stackforce.cc/examples/robots/<robot>/(urdf/<name>.urdf|meshes/*.STL|dae/*.dae)`；中文名机器人使用 URL 编码。闭链机器人（softfoot-q、simplified-quadruped）用 USD 而非 URDF。

## 六、未能抓取的资源及原因

| 资源 | 原因 |
|---|---|
| sitemap.xml / manifest.json / 404.html | 404 |
| favicon.svg | 404（仅 ico 存在） |
| 全部 `.js.map` | 404（未发布 source maps） |
| g1 网格 27 个 STL | 服务器 404 |
| `urdf.stackforce.cc`（在线建模器） | 仅抓取入口 HTML 级确认，未展开（属另一子域，可按需补抓） |
| workbench.stackforce.cc | 主工作台，需登录（未触碰） |

## 七、界面文字提取（_analysis/）

由于主应用 JS 经混淆、source map 不存在，为便于阅读界面文案，已从各 chunk 中提取全部可读字符串（中英文）到 `_analysis/` 目录：

| 文件 | 条数 | 内容 |
|---|---|---|
| `ui_strings_page.txt` | 653 | 主应用全部界面文字，含 233 条中文（奖励函数各项说明、导入导出提示、错误信息等） |
| `ui_strings_chunk813.txt` | 8 | 训练工程导出器（Isaac Gym / Isaac Lab / MJLab 目标校验提示） |
| `ui_strings_chunk595.txt` | 22 | Sim2Sim 策略运行时提示（ONNX 策略路径、观测项说明） |
| `ui_strings_chunk520.txt` | 180 | three.js 全家桶（URDFLoader/GLTFLoader/ColladaLoader/STLLoader/OrbitControls）+ R3F（React Three Fiber） |
| `ui_strings_chunk117.txt` | 41 | Next.js 框架运行时错误信息 |
| `ui_strings_chunk862.txt` / `ui_strings_layout.txt` | 17 | 布局侧边栏分组名（训练与导出/示例与模型/结构配置等） |

提取脚本：`_extract_strings.py`（可重跑）。

> 520 中出现 `R3F.createRoot`、`URDFLoader`，确认 3D 栈为 **React Three Fiber + three.js + URDFLoader/GLTFLoader/ColladaLoader/STLLoader**。

## 八、根目录辅助文件

- `_crawl2.py` / `_fetch.py` — 上阶段爬虫脚本；`_dl_log.jsonl` / `_dl_log2.jsonl` — 下载日志（含全部 URL 与状态码）；`_crawl2_out.log`、`_urls.txt` — 过程产物
