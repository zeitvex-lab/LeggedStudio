# 1000framesai.com 全站抓取与分析报告

- 抓取日期：2026-09-08（两轮：公开抓取 + 用户本人账号登录后抓取）
- 入口地址：`https://1000framesai.com`（实际可达的唯一地址）
  - `https://www.1000framesai.com` → 连接失败（无响应）
  - `http://1000framesai.com` → 301 跳转到 `https://1000framesai.com/`
  - `http://www.1000framesai.com` → 连接失败
- 服务器：nginx，HTTP 响应带严格 CSP（所有资源同源 `'self'`，无第三方 CDN）
- 站点性质：**Locomotion Platform** —— 面向人形/四足/轮腿机器人的强化学习训练与 sim2sim 仿真平台（中文界面），类似"机器人训练控制台"的公开前端

---

## 一、抓取统计

| 类别 | 数量 | 大小 |
|---|---|---|
| HTML 页面 | 7 | 68.9 KB |
| JS（含 vendor 库） | 13 | 2,080.5 KB |
| CSS | 7 | 120.2 KB |
| MuJoCo 场景/模型 XML | 13 | 126.0 KB |
| OBJ 三维网格 | 16 | 27,743.3 KB |
| PNG 图片 | 7 | 975.8 KB |
| JPG（QQ 群二维码） | 1 | 572.3 KB |
| WebM 视频 | 4 | 251.1 KB |
| WebP 海报图 | 4 | 39.0 KB |
| ONNX 模型 | 1 | 5,064.6 KB |
| WASM | 3 | 43,298.3 KB |
| MJS（ORT worker） | 3 | 117.4 KB |
| JSON（公开 API 响应） | 3 | 1.4 KB |
| **合计** | **82 文件** | **78.57 MB** |

抓取方式：Python BFS 爬虫（限速 0.4–0.5 秒/请求，单线程，礼貌抓取）+ 针对性资源清单下载。
全部请求均记录状态码；未出现网络错误，所有失败均为服务器明确返回 404/401。

## 二、目录树概览

```
1000framesai.com/
├── index.html                  # 首页（控制台 dashboard）
├── app.js                      # 首页逻辑
├── support-qq-group.jpg        # 售后 QQ 群二维码
├── api_health.json             # /api/health 响应（已存档）
├── api_billing_pricing.json    # /api/billing/pricing 响应（已存档）
├── api_play_demos.json         # /api/play/demos 响应（已存档）
├── login/                      # 登录/注册页
│   ├── index.html
│   └── app.js                  # 邮箱注册 + 用户名/邮箱登录 + 邮箱验证
├── algorithms/                 # 算法能力页
│   ├── index.html / app.js / styles.css
│   └── media/                  # 4 组演示视频 webm + 海报 webp + 1 png
├── robots/                     # 机器人配置页（URDF 管理）
│   └── index.html / app.js / styles.css
├── train/                      # 训练任务页
│   └── index.html / app.js
├── sim2sim/                    # 仿真验证页（核心，浏览器端仿真）
│   ├── index.html / app.js / styles.css
│   ├── models/go2_moe_cts_high_slope_164k.onnx   # Go2 RL 策略权重
│   ├── assets/
│   │   ├── go2/                # Unitree Go2 MuJoCo 模型：go2.xml + 11 个地形 XML
│   │   │   ├── assets/         # 16 个 OBJ 网格 + height_field.png + wood.png
│   │   │   └── imgs/           # 4 个 label 标签贴图
│   │   └── fsdog1/fsdog1.xml   # FSDog 机器人 MuJoCo 模型
│   └── vendor/                 # 本地自托管依赖
│       ├── three/              # Three.js r160（three.module.js + Orbit/TransformControls）
│       ├── mujoco/             # MuJoCo WASM（mujoco.js 294KB + mujoco.wasm 8.6MB）
│       └── onnxruntime-web/    # onnxruntime-web（ort.wasm.min.mjs + simd-threaded wasm 共 42MB）
├── ops/                        # 上线检查页（需管理员，静态文件公开）
│   └── index.html / app.js / styles.css
└── shared/
    ├── api.js                  # 全站统一 API 客户端（核心）
    ├── nav.js / nav.css        # 导航组件
    └── styles.css              # 全站样式（含 email-auth 版本变体）
```

## 三、技术栈与代码实现分析

### 前端
- **无框架原生 JavaScript（ES Modules）**：未使用 React/Vue/Next 等，也没有 Webpack/Vite 打包痕迹——所有 JS 都是**未经打包的源码直接发布**（有版本号查询串如 `?v=wheel-leg-jump-1` 做缓存失效）。**未发现任何 source map（`.js.map`/`.css.map` 均 404），但也不需要——下载到的 JS 本身就是原始源码**。
- **Three.js r160**（importmap 引入，自托管于 `/sim2sim/vendor/three/`）：用于 sim2sim 3D 视口和 robots 页 URDF 预览（OrbitControls + TransformControls）。
- **MuJoCo WASM**（Google `mujoco_wasm`，版本字符串 16.04.4，自托管）：浏览器内物理仿真。
- **onnxruntime-web**（wasm 后端，`numThreads=1` 单线程，自托管）：在浏览器内直接运行 ONNX 强化学习策略。
- **原生 CSS**（注释明言 `no-tailwind`），无 UI 组件库；无任何第三方统计/分析服务（无 GA/百度统计等）；CSP 也证实无外部 connect-src。
- 页面为传统多页应用（MPA）：`/`、`/algorithms/`、`/robots/`、`/train/`、`/sim2sim/`、`/ops/`、`/login/`，每页自带独立 `app.js`。

### 后端（从前端代码推断）
- `404` 响应体为 `{"detail":"Not Found"}` → **Python FastAPI**（或兼容框架）风格。
- 鉴权：**Cookie Session**（`credentials: 'include'`），支持邮箱注册/登录、邮箱验证 token、管理员角色（`requireAdmin()`）。无 OAuth/第三方登录。
- 训练计费：按 GPU 秒实时计费（`billing_mode: "live"`，30 秒结算间隔），支持 4090D/5090/H800 等 GPU 规格，支持微信支付 Native 下单。
- sim2sim 页面把内置 MuJoCo 资源 fetch 到 `/working/` 路径（后端工作目录），说明前端与后端同域部署。

### 代码规模
- 站点自研 JS 源码约 21 万字符（不含 vendor），最大的是 `sim2sim/app.js`（完整浏览器端仿真管线：加载 MuJoCo → 运行 ORT 推理 → 三维渲染）、`train/app.js`（训练任务创建/轮询/奖励函数编辑）、`ops/app.js`（运维面板）。

## 四、API 端点清单（提取自 shared/api.js）

Base: `/api`，鉴权均为 Cookie Session。标注 🔓 的为本次实测公开可访问：

**meta**：`GET /api/health` 🔓（`{"status":"ok"}`）

**auth**：`POST /api/auth/login`、`/api/auth/register`、`/api/auth/verify-email`、`/api/auth/resend-verification`、`/api/auth/logout`；`GET /api/auth/me`

**robots**：`GET /api/robots`、`GET/PUT/DELETE /api/robots/{id}`、`POST /api/robots/deduplicate`、`POST /api/robots/urdf/upload|folder|step|step-folder|step/inspect|step/assembly`、`GET /api/robots/urdf/preview-mesh`、`GET /api/robots/urdf/packages/{name}/files/{path}`、`GET /api/robots/urdf/assemblies/{id}/meshes/{mesh}`

**algorithms**：`GET /api/algorithms`、`GET /api/algorithms/{id}`、`POST /api/algorithms`

**runs（训练任务）**：`GET /api/runs`、`GET /api/runs/{id}`、`POST /api/runs`（带 `Idempotency-Key` 头）、`POST /api/runs/{id}/cancel`、`POST /api/runs/{id}/resume`、`GET /api/runs/{id}/events`、`GET /api/runs/{id}/metrics`

**play（sim2sim 播放）**：`GET /api/play/latest`、`GET /api/play/{runId}`、`GET /api/play/demos` 🔓（返回 4 个内置演示：Go2 / P1 AMP-CTS / Y1 / W1W 轮腿）、`GET /api/ops/runs/{id}/deployment-bundle`

**ops（需管理员）**：`GET /api/ops/preflight|artifacts|artifacts/cleanup-plan|algorithms|queue`、`POST /api/ops/artifacts/cleanup-local|cleanup-remote-checkpoints|runs/mark-orphans`

**billing**：`GET /api/billing/pricing` 🔓（GPU 单价：4090D ¥3/h、v-48g-350w ¥3.5/h、v-48g 与 v-32g-p ¥4/h、5090-p ¥6/h、H800 ¥15/h；GPU 数 1/2/4）、`GET /api/billing/me|users`、`POST /api/billing/topup`

**payments**：`GET /api/payments/wechat/config|orders`、`POST /api/payments/wechat/native`（微信扫码支付）

**第三方服务：无**。CSP `connect-src 'self'` + 代码检查确认全部请求同源；无 CDN、无分析统计、无外部支付 SDK（微信支付走自有后端代理）。

## 五、可下载资源清单

- **策略权重**：`sim2sim/models/go2_moe_cts_high_slope_164k.onnx`（5.0MB，Go2 MoE-CTS 164k iteration）
- **MuJoCo 模型**：Go2 完整模型（go2.xml + 16 OBJ 网格 + 11 个地形场景 XML + 贴图）、FSDog 模型（fsdog1.xml）
- **演示视频**：4 个 webm（go2_rl_gym / np3o / parkour / quadrupedal_agility）+ 4 个 webp 海报 + 1 个 png
- **运行时库**：mujoco.js + mujoco.wasm（8.6MB）、onnxruntime-web 全套（ort.wasm.min.mjs + ort-wasm-simd-threaded[-jsep].wasm，共 42MB）、Three.js r160 + 2 个控件
- **公开数据 JSON**：health / pricing / play demos 三个响应已存档
- 无 PDF/zip/csv/txt 等文档类下载

## 六、未能抓取的资源及原因

| 资源 | 状态 | 原因 |
|---|---|---|
| `/robots.txt`、`/sitemap.xml` | 404 | 站点未提供 |
| `/favicon.ico`、`favicon.svg`、`apple-touch-icon.png` | 404 | 站点无 favicon |
| `/manifest.json`、`/.well-known/assetlinks.json`、`/.well-known/security.txt`、`/humans.txt` | 404 | 不存在 |
| `/sim2sim/assets/fsdog1/{地形}.xml`（11 个） | 404 | FSDog 地形文件不在静态目录（代码显示由 `/api/play/{id}` 动态下发或与 go2 共用 go2.xml 模板替换生成） |
| `/working/fsdog1.xml` | 404 | 后端运行时工作路径，静态不可访问 |
| URDF 引用的 `meshes/base.stl`（多种推测路径） | 404 | 该 STL 由 URDF 包上传接口动态提供，非静态资源 |
| `/api/algorithms`、`/api/robots`、`/api/play/latest`、`/api/ops/*`、`/api/billing/me` | 401 | 需登录/管理员会话（按要求未尝试登录或绕过） |
| `/register/`、`/verify-email/` 等独立页 | 404 | 注册/验证是 `/login/` 页内的 tab 模式，无独立路由 |
| `/ops/` 页面数据 | — | 页面 JS 已抓到（静态公开），但渲染数据需管理员权限，未触碰 |

抓取覆盖率评估：全站 7 个公开路由（首页、算法、机器人、训练、仿真、运维、登录）的 HTML、全部自研 JS/CSS 源码、全部 JS 引用到的静态资源（含按需加载的 wasm/onnx/obj/xml）均已获取，**公开静态内容覆盖率约 100%**。

---
*抓取过程礼貌限速（0.4–0.5s/请求，单线程），未尝试任何登录、付费或鉴权绕过。*

---

# 七、登录后抓取（2026-09-08 第二轮）

## 登录过程

- 使用用户本人提供的账号（eatzio02@gmail.com）通过 `/login/` 页面的**正常表单流程**登录：填入邮箱 + 密码 → 点击"登录" → 200 成功跳转回首页。
- **未遇到验证码，也未触发邮箱验证码环节**（该账号 email_verified 已为 true）。未做任何绕过。
- 会话机制确认：登录后服务端下发 `ploco_session` Cookie（HttpOnly，document.cookie 不可见），配合 `credentials: 'include'` 使用。
- 账号身份（`/api/auth/me`）：`usr_1788174694_e36fa133`，角色 `user`（普通用户，非管理员），余额 `balance_cents: 0`，注册开放模式 `email`。

## 新抓取内容（新增 30 个文件 / 25.23 MB）

### 1. 登录态渲染 HTML（authenticated/，6 个）
| 文件 | 说明 |
|---|---|
| `authenticated/index.html` | 首页登录态渲染（含完整导航、用户名、¥0.00 钱包入口、4 个 Demo 卡片、13 个算法卡片、系统状态面板） |
| `authenticated/robots.html` | 机器人配置页渲染（Three.js URDF 预览加载完成态） |
| `authenticated/algorithms.html` | 算法页渲染 |
| `authenticated/train.html` | 训练页渲染（含机器人/算法/任务选择器、GPU 选项、奖励函数编辑器） |
| `authenticated/wallet.html` | **钱包充值页（登录后才在导航出现的隐藏页面）** |
| `authenticated/sim2sim.html` | 仿真页渲染（仅加载页面本身，**未启动任何仿真/未加载任何策略，未产生消耗**） |

### 2. API GET 快照（api_snapshots/，14 个 JSON，只存读取类接口）
| 文件 | 端点 | 关键内容 |
|---|---|---|
| `auth_me.json` | GET /api/auth/me | 用户对象：id/username/email/email_verified/role/balance_cents/created_at；`registration_open: true, registration_mode: "email"` |
| `algorithms_list.json` | GET /api/algorithms | **13 个内置算法完整定义（270KB）**，含 manifest：runtime（python 路径、环境变量）、contract（obs_dim=45、history_len=5、action_dim=12、ONNX 输入输出张量形状）、entrypoints（训练/评估 shell 命令模板，暴露 GPU 侧目录 `/opt/go2_rl_gym`、`/opt/isaacgym`、miniconda 路径）、tasks（任务 id、默认超参 num_envs=8192/max_iterations=150000、**14 项 reward_scales 权重**）、capabilities、compatible_robots |
| `robots_list_auth.json` + `robot_*.json` | GET /api/robots、/api/robots/{id} | 11 个内置机器人（Go2/Go1/A1/Aliengo/B1/B2/FSDog1/Y1/Y2/W1W/P1），含 joint_order、default_joint_angles、joint_limits（lower/upper/effort/velocity）、control_defaults、morphology（quadruped_12dof / wheel_leg_16dof_v1） |
| `runs_list_auth.json` | GET /api/runs | `[]`（该账号无训练任务） |
| `play_latest.json` | GET /api/play/latest | 全 null（无可播放策略），`sim_engine: "mujoco"` |
| `billing_me.json` | GET /api/billing/me | `{"balance_cents": 0, "transactions": []}` |
| `payments_wechat_config.json` | GET /api/payments/wechat/config | 充值档位 1/10/50/100 元，单笔上限 5 万元，订单有效期 900 秒 |
| `payments_wechat_orders.json` | GET /api/payments/wechat/orders | `{"orders": [], "latest_pending": null}` |
| `ops_preflight.json` | GET /api/ops/preflight | **403** `"admin privileges required"`（普通账号无权限，正确拒绝） |

### 3. 可下载资源（authenticated/urdf_go2/，8 个文件 24.75MB）
之前发现的 URDF 包接口带 session 后可访问（无 session 返回 401）：
- `go2.urdf`（20KB，完整 URDF：12 个 revolute 关节、惯性参数、collision 几何、Head_upper/lower、IMU、radar link）
- `dae/`：base.dae(10.7MB)、hip.dae(4.7MB)、thigh.dae(3.9MB)、thigh_mirror.dae(3.9MB)、calf.dae(1.1MB)、calf_mirror.dae(1.1MB)、foot.dae(0.5MB)——**完整 Go2 视觉网格**

### 4. wallet 页专属代码（wallet/）
- `app.js`（16.6KB，微信 Native 扫码充值流程、订单轮询）+ `styles.css`（9.7KB）

## 登录后抓取统计

| 类别 | 数量 | 大小 |
|---|---|---|
| DAE 网格 | 7 | 24.73 MB |
| JSON（API 快照） | 14 | 0.31 MB |
| 渲染 HTML | 6 | 0.14 MB |
| URDF | 1 | 0.02 MB |
| JS/CSS（wallet） | 2 | 0.03 MB |
| **新增合计** | **30 文件** | **25.23 MB** |
| **两轮总计** | **112 文件** | **103.79 MB** |

## 未能抓取的内容及原因（登录后轮）

| 内容 | 原因 |
|---|---|
| `/ops/` 页面数据 | 该账号 role=user 非管理员：页面 `requireAdmin()` 直接重定向回首页；`/api/ops/preflight` 等返回 403 `"admin privileges required"`。未尝试提权 |
| 训练 runs / 事件 / 指标数据 | 账号名下无任何训练任务（runs=[]），无数据可抓 |
| deployment-bundle | 端点格式为 `/api/ops/runs/{id}/deployment-bundle`，属 ops 管理接口且无 run id，未触碰 |
| sim2sim 实际仿真过程数据 | **主动不加载**：仿真需加载 ONNX 策略并启动 MuJoCo 会话（平台 GPU 按秒计费、浏览器仿真也消耗资源），为避免任何消耗性操作只保存了页面本身 |
| 微信支付下单接口 | 属 POST 消耗性操作，严禁触发，未调用 |
| 机器人 URDF 包中其余 10 个机器人的网格 | 仅下载了页面实际加载演示的 go2 包（其余机器人未逐个打开预览，接口模式已确认一致：`/api/robots/urdf/packages/{pkg}/files/{path}`，如需可按同模式扩展） |

## 安全与礼貌性说明

- 全程仅使用用户本人账号 + 浏览器正常登录流程；仅执行 GET 读取类请求 + 登录 POST 一次；未点击任何"创建训练/充值/开始仿真"等会产生扣费或消耗的按钮。
- 请求间隔 0.4–0.5 秒，单线程。
- 会话 Cookie 仅用于本次抓取请求，未写入报告正文之外的文件（除抓取请求头）。
