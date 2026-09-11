# 1000framesAI 公开逆向与资源归档

**目标**：分析 `https://1000framesai.com` 的公开前端、流程和可下载资源。  
**采集日期**：2026-08-31（Asia/Shanghai）  
**范围**：未登录页面、公开静态资源、匿名只读 API。未绕过认证、未调用写入接口、未保存账号或 cookie。

## 结论

1000framesAI 对外品牌是 **Locomotion Platform**，公开前端已经实现一条足式机器人工作流：机器人配置 -> 算法 -> 训练 -> 仿真验证。仿真页是浏览器本地运行的 MuJoCo WASM + ONNX Runtime Web + Three.js 组合，未登录时 `/api/play/latest` 返回 401，但页面会回退到内置 Go2 demo，因此公开 demo 可以独立运行。

站点没有发现公开源码仓库、`robots.txt`、`sitemap.xml` 或 `openapi.json`；HTML/JS/CSS 是可读的 ES module。没有发现站点许可证声明，因此下载的 ONNX、MJCF、OBJ、纹理和媒体只能作为本地研究参考，不能直接打包进 Legged Studio 发布物。

## 页面与访问控制

| 路径 | 公开状态 | 观察 |
|---|---:|---|
| `/` | 200 | 控制台、4 个内置 demo、状态摘要 |
| `/robots/` | 200（页面）；业务 API 需登录 | URDF/STEP/STL/DAE/OBJ 导入、Three.js 预览、关节映射 |
| `/algorithms/` | 200（页面）；业务 API 需登录 | 算法能力卡片、视频/封面媒体 |
| `/train/` | 200（页面）；业务 API 需登录 | run 创建、resume、取消、事件/指标、ONNX 产物 |
| `/sim2sim/` | 200 | 内置 Go2/FSDog 仿真和交互扰动 |
| `/ops/` | 200（页面）；管理员 API 需登录 | preflight、artifact、队列、孤儿 run |
| `/login/` | 200 | 登录/注册/邮箱验证表单 |

匿名只读 API 实测：`/api/health` 200、`/api/auth/me` 200（`user:null`）、`/api/play/demos` 200、`/api/billing/pricing` 200；`/api/robots`、`/api/algorithms`、`/api/runs`、`/api/play/latest`、`/api/ops/*`、`/api/billing/me` 和支付配置返回 401。所有请求均保持原始站点会话，不尝试绕过。

## 前端架构

```text
同源 HTML + ES modules
        |
        +-- shared/api.js  -> fetch + credentials: include + JSON ApiError
        +-- shared/nav.js  -> 统一导航和 requireAuth/requireAdmin
        +-- robots/app.js   -> Three.js / CAD 导入 / URDF 资源引用 / 关节 UI
        +-- train/app.js    -> run、resume、cancel、事件、指标、ONNX
        +-- sim2sim/app.js  -> MuJoCo WASM + ORT Web + Three.js + 内置 fallback
        +-- app.js          -> 控制台聚合与 demo 列表
```

共享 API 客户端统一封装 GET/POST/PUT/DELETE、查询参数、cookie 会话和非 2xx 错误。静态代码暴露的写入能力包括机器人上传/更新/删除、训练创建/取消/resume、注册和支付；本次没有调用这些接口。

## 仿真实现要点

- 默认 Go2 策略：`go2_moe_cts_high_slope_164k.onnx`，公开文件约 5.2 MB。
- 观测摘要：页面显示 45 维观测、5 帧历史、12DoF；默认动作缩放 0.25，仿真 dt 0.002 s，控制 decimation 10。
- 资源：Go2 MJCF、12 个地形 XML、16 个 OBJ mesh、4 个标签 PNG、地形/木纹纹理。
- 运行时：MuJoCo WASM 约 8.6 MB；ONNX Runtime Web threaded WASM 约 11.9 MB；Three.js module、OrbitControls、TransformControls 随站点提供。
- 未登录策略加载失败时，代码记录 `authentication required` 并使用 bundled demo；浏览器实测 MuJoCo 场景编译成功，视口持续更新，截图见 `../../output/playwright/1000framesai-sim2sim.png`。
- FSDog1 是另一个内置 12DoF 机器人，公开 `assets/fsdog1/fsdog1.xml`，默认关节角和控制参数写在仿真 JS 中。

## 本地资源

主归档目录：`legged_studio/references/1000framesai/site/`（74 个文件，约 55.71 MiB）

- 7 个页面 HTML（首页、robots、algorithms、train、sim2sim、ops、login）
- 页面和共享 JS/CSS（含机器人导入、训练流程、仿真运行时）
- Go2/FSDog1 MJCF/XML、OBJ/PNG、ONNX、MuJoCo/Three/ORT Web 运行时
- `algorithms_media/` 下的公开 WebM/WebP/PNG 算法演示媒体

匿名 API 样本目录：`legged_studio/references/1000framesai/api_samples/`

- `health.json`
- `auth_me_anonymous.json`
- `play_demos.json`
- `billing_pricing.json`

校验清单：`RESOURCE_MANIFEST.json`，记录归档文件的相对路径、字节数和 SHA-256；匿名 API 样本另有 `API_MANIFEST.json`。仿真截图：`legged_studio/output/playwright/1000framesai-sim2sim.png`。

## 对 Legged Studio 的可复用价值

1. 资产工作台可以参考其“机器人配置 -> 算法 -> 训练 -> 仿真”的导航和同源 API 客户端；不要复制其未授权的页面代码和模型资源。
2. 3D/仿真技术路线可作为验证样例：Three.js 负责交互视图，MuJoCo WASM 负责浏览器物理，ORT Web 负责 ONNX 推理；训练和评估仍应放在独立 worker。
3. 其 bundled demo/fallback 说明公开产品需要一个无需登录的确定性 smoke fixture；Legged Studio 可用自己的 Go2 fixture 和 Robot Contract 实现。
4. 其 API 分层可对照 RoboLab/UniLab 语义：控制面只传 run、policy、contract 和事件；不要把训练框架 import 到主 Web 服务。

## 复现命令

```powershell
# 校验归档哈希
$root = Resolve-Path legged_studio\references\1000framesai\site
Get-ChildItem $root -Recurse -File | ForEach-Object { Get-FileHash $_.FullName -Algorithm SHA256 }

# 公开页面浏览器 smoke（需要 Node.js/npx）
npx --yes --package @playwright/cli playwright-cli open https://1000framesai.com/sim2sim/
npx --yes --package @playwright/cli playwright-cli snapshot
npx --yes --package @playwright/cli playwright-cli close
```

本次浏览器 smoke 的已知限制是未登录后台每约 5 秒轮询 `/api/play/latest` 并得到 401；这不会阻止 bundled demo，但不应被误判为站点前端完全无错误。
