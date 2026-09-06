# Sim2Sim 查看器 mjswan 借鉴优化实施清单

实施日期：2026-09-05。目标文件：`web/sim2sim/app.js`、`index.html`、`styles.css`（app.js 缓存版本号升到 `?v=0.8.0`）。
约束遵守：未改动任何 `build*Observation` 观测构造器、动作映射（reindex/scale/filter）与 PD 控制逻辑。
每个批次均通过 `node --check web/sim2sim/app.js` 语法校验。

| # | 优化项 | 状态 | 关键改动点 |
|---|--------|------|-----------|
| 1 | 暂停时保持渲染 | 完成（原有行为已满足，补充语义注释） | `frame()` 中 `syncVisualScene + renderer.render` 本就不受 `sim.paused` 影响；在 `frame()` 内补充注释固化该语义（对齐 mjswan pause 语义），未发现需要改动的逻辑。 |
| 2 | 主循环异常自愈 | 完成 | `frame()` 的 catch 不再 `sim.paused = true` 永久卡死；改为记录错误、`sim.accumulator = 0`（防错误后爆发补步）、状态条显示「仿真异常 · 自动重试中（N）」，连续成功后自动恢复「MuJoCo 已就绪」。 |
| 3 | 相机平行跟踪基座 | 完成 | `updateFollowCamera()` 改为读取 `sim.data.xpos[sim.baseBodyId*3..]`（自由关节根 body），把位移 delta 同时加到 `view.controls.target` 与相机位置（视线角/缩放不变）；沿用页脚「跟随」开关（默认开启）作为可开关项，并加了 `xpos` 缺失时回退 `qpos` 的保护。 |
| 4 | 键盘快捷键 C / R | 完成 | `keydown` 处理器新增 C=隐/显控制面板（`toggleControlPanel()`，所有断点生效的 `body.panel-hidden`）、R=`resetSimulation()`；新增 `isEditableElement()` 守卫（input/textarea/select/contentEditable 聚焦时不触发；按钮/链接聚焦时 C/R 仍可用，与移动键的旧守卫区分）。工具栏按钮加了 title 提示（Space / R）。 |
| 5 | URL 状态持久化 | 完成 | 新增纯函数 `readViewerStateFromUrl(params)` 与 `writeViewerStateToQuery(params, state)`（读写各一），外加 `applyViewerStateFromUrl()`（init 时应用）与 `syncViewerStateToUrl()`（replaceState 回写，不动历史栈）。持久化状态：`panel=0/1`（面板显隐）、`trail=0/1`（轨迹拖尾）。 |
| 6 | WASM OOM 友好报错 | 完成 | 新增 `isWasmOom()`（匹配 `MjModel loading returned null / Could not allocate memory / memory allocation failed / bad_alloc / lodepng / Cannot enlarge memory / array buffer allocation failed`）与 `describeLoadError()`（统一转成「超出 WebAssembly 内存上限（约 2 GB）…」中文提示）；接入 init、loadTerrain、switchPolicy、策略初始化四处错误路径。 |
| 7 | frameCamera 自适应取景 | 完成 | 新增 `frameCameraToModel()` + `modelBoundingBox()`：按机器人（非 world body）geom 包围盒计算 fitDistance（fov/aspect 保守拟合 × 1.12 边距），保持当前视线方向仅调距离；排除 90m 地面避免取景过远。接入：loadTerrain 加载后自动执行一次、`legged-studio:fit-view` 消息、页脚新增「取景」按钮；原 `fitViewerCamera()` 保留为无动态 geom 时的回退。 |
| 8 | 重置时清策略状态 | 完成 | `resetSimulation()` 新增 `sim.g1PhaseS = 0`（G1 mjlab velocity 步态相位时钟）、`cancelDragInteraction()`（清 xfrc_applied + 恢复轨道控制 + 藏力箭头）、`resetTrail()`（清轨迹缓冲）。既有 `resetPolicyState()`（ONNX RNN 隐状态 + epoch）、action/appliedAction/filteredAction、IMU 历史、history、gait/jump 时钟、weights/estimatedVel/latent 清零均已存在并核实。 |
| 9 | 鼠标拖拽施力 | 完成 | `initDragInteraction()` 在 OrbitControls 之前注册到 renderer 画布（capture 阶段）：raycast 命中「非 world body 且带关节」的 geom 后 `stopImmediatePropagation` 抢占事件、临时禁 OrbitControls；pointermove 只记 NDC，力在 `stepSimulation()` 内经 `applyDragForce()` 写 `data.xfrc_applied[bodyId*6..+6]`（offset × 100 N/m，单轴限幅 300N，力矩槽清零）；松开/失焦/重置时 `cancelDragInteraction()` 清零恢复；`updateDragArrow()` 每帧画 three `ArrowHelper` 力箭头（方向=力向，长度∝力）。 |
| 10 | 速度命令滑条直连策略 | 完成 | 控制面板新增「速度指令」区块（vx/vy/ωz 三滑条 + 归零按钮）；`CONFIG.commandRanges` 解析自 `contract.command_ranges`（兼容 `[[min,max]…]` 与扁平布局，缺省回落 `CONFIG.maxCmd`），默认值取 `contract.default_command`；`updateVelocityCommandControls()` 在 `command_dims ≥ 3` 时显示（g1_mjswan_balance 等无命令观测策略隐藏）；用户触碰滑条后 `manualCmdActive` 接管无按键/摇杆时的 idle 命令流（`updateCommand()` 新增 `applyManualCommand()` 分支），键盘/摇杆仍优先。 |
| 11 | ONNX 推理串行队列 | 完成 | 新增 17 行 `queueOrtRun()`（promise 链，成败两路都推进队列，照搬 mjswan runQueue.ts 思路）；`runPolicy()` 的 `sim.policy.run(feeds)` 全部走队列，杜绝跨 session 的 "Session already started"。 |
| 12 | 根轨迹拖尾 | 完成 | 页脚新增「轨迹」开关（状态入 URL `trail=`）；`ensureTrail/updateTrail/resetTrail`：每 0.2s 采样根 body 世界位置，预分配 200 点 `BufferGeometry`（满后 copyWithin 平移），顶点色从背景色渐变到青蓝实现渐隐，`setDrawRange` 控制绘制；重置/换场景时清空。 |
| 13 | hfield 地形渲染 | 完成 | `makeGeomTypes` 补 `mjGEOM_HFIELD`；`geometryKey` 以 `hfield:<dataid>` 缓存；新增 `buildHFieldGeometry()`（参考 mjswan scene.ts 的 createHFieldGeometry，约 70 行；本查看器直接用 MuJoCo Z-up 坐标，故无坐标重排）：按 `hfield_nrow/ncol/size(sx,sy,sz,base)/adr/data` 生成网格并含 base 高程；`classifyGeom` 原有逻辑已把 world body 的 hfield 归为 terrain。 |
| 14 | .mjz 打包格式脚手架 | 脚手架 | `loadMjzPackage(arrayBuffer)` 函数骨架 + 完整 TODO 注释（.mjz = ZIP(主 MJCF XML + assets 相对路径)；JSZip 放 `vendor/jszip/` 并动态 import 的方案；MEMFS 写入与主 XML 路径返回约定），调用即抛出可读的「未实现」提示。未引入 JSZip 依赖。 |
| 15 | parity 测试脚手架 | 脚手架 | 新增 `scripts/g1_parity_note.md`：固定动作序列对比浏览器（`__sim2simDebug.startFrameLog/stopFrameLog` + 建议的 `playActionClip` 钩子）与桌面（`g1_amp_sim2sim_check.py` 骨架）obs/action 的方案、对比脚本设想、容差阈值与常见不一致排查清单（IMU 符号 / reindex / scale / 历史布局 / settle）。未实现测试本体。 |

## 附注

- **未触碰的区域**：全部 `build*Observation`、`runPolicy` 的动作映射/滤波/PD 逻辑、后端 API。
- **新增 UI**：页脚「轨迹」开关与「取景」按钮；控制面板「速度指令」滑条区块（对应 CSS `.velocity-command-control`、`body.panel-hidden`）。
- **已知边界**：拖拽施力只在物理步生效（暂停时冻结）；manual 滑条命令会被按住的键盘指令临时覆盖，松键后恢复。

## 2026-09-06 修复批次（v=0.8.4）

约束遵守：未改动任何 `build*Observation`、动作映射与 PD 控制逻辑；`node --check` 通过。

| # | 修复项 | 关键改动点 |
|---|--------|-----------|
| 1 | 页脚工具栏宽视口消失 | 根因：基础 `.footer` 为居中收缩条（`left:50% + translateX(-50%)`），mjlab-light 主题改为全宽（`left/right:16px`）却未取消位移，>980px 时整排控件被平移出屏幕左缘只剩白条。主题规则补 `transform:none; flex-wrap:wrap; justify-content:center; row-gap`；窄屏 620px 断点下控制面板 `bottom:64px→92px` 防与换行后的 footer 重叠。 |
| 2 | 页脚新增「视觉模型」开关（默认勾选） | `createRenderable` 记录每个 mesh 的 geom group/contype/conaffinity 与 `baseOpacity`；`updateRenderFlags` 按 `classifyGeom` 归属切 `mesh.visible`（visual=随开关、collision=开关或视觉关闭时强制可见、terrain 恒显）；视觉关闭时碰撞 geom 转为不透明便于辨识。纯渲染层切换，不影响物理；取景包围盒同步跳过被隐藏 geom。 |
| 3 | 速度指令 Max 滑条默认 1.0 | 新增 `velocityCommandMaxDefault()`：三轴 Max 初始一律 1.0（vy 仅当契约范围上下限均为 0 时保持 0.5）；`velocityCommandMax` 缺省回落同步改为该默认值。命令滑条随 Max 联动 ±Max 的逻辑保留。 |
| 4 | 移除「运动指令」区块 | index.html 删除「运动指令」section-title + `#vxSpeedLimit` 滑条（`#speedLabel` 一并移除）；app.js 清理 `elements.vxSpeedLimit/speedLabel`、其 input 绑定与 `updateCommandLabel` 中的文案分支，删除 CSS `#vxSpeedLimit` 规则。键盘 WASD/QE（`input.vxSpeedLimit` 固定 1.0 m/s）、移动摇杆 `bindMobileJoystick`（独立触摸输入，非仅服务该区块）与 cruise 按钮全部保留。 |
| 5 | go2w 策略加载失败（缓存旧字节） | app.js：策略 ONNX 改为手动 `fetch(cache:"no-store")` 取 `Uint8Array` 再 `ort.InferenceSession.create(bytes)`（`fetchPolicyModelBytes`），彻底绕开 URL 缓存；日志输出实际字节数/耗时，并检测字节内残留的外部数据引用（如 `policy.onnx.data`）告警。后端 `browser_simulation_asset` 对 `.onnx/.data` 响应加 `Cache-Control: no-store`。已验证：重启 8877 后 curl 该 URL 返回 `cache-control: no-store`、787633 字节。 |
| 6 | 页脚改左下角紧凑卡片 + 合并「视觉模型/碰撞体」开关（v=0.8.5） | mjlab-light 主题 `.footer` 改为左下角 fixed 竖排小卡片（`left:16px; right:auto; bottom:16px; flex-direction:column; max-width:max-content`），时间/FPS 收进卡片；≤620px 复选框两列网格压低高度、控制面板避让 `bottom:92px→178px`。index.html 删除「视觉模型」复选框，仅保留「碰撞体」（默认不勾选，语义取原「视觉模型」不勾选分支）；`updateRenderFlags` 改由 `collisionToggle` 单开关驱动（visual visible=!checked，collision visible=checked 且勾选时转不透明），清理 `elements.visualModelToggle` 及其 change 监听；资源版本 v0.8.4→v0.8.5。 |

## G1 策略推理修复（v=0.8.6）

- **根因**：base_lin_vel/base_ang_vel 的参考点错误。mjlab/mjswan 用 root body 的 **link 速度**（cvel 绕 subtree COM，需按 `compute_velocity_from_cvel` 修正到 body origin），此前误用 freejoint qvel 线速度——参考点差一个旋转臂，行走时体速度估计带系统性偏差，策略 3 秒内失稳（站立无速度所以看不出）。
- **修复**：`captureImuSample` 改为从 `data.cvel` 计算 root link 速度（lin/ang 都取世界系 cvel，修正后投影机体系），带 qvel 回退。
- **模型**：换回 mjswan 官方 g1.xml（motor 力矩执行器 + 浏览器侧力矩 PD + 官方接触参数 condim=3/friction=0.6）；控制接口 torque。
- **桌面验证**：z 恒 0.759、pitch ±0.02，6 秒稳定行走 2.25m（vx=0.5 指令）。
