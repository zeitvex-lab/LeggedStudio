# assets/maps/ — 公共地图库

**机器人无关的环境地图**：基础仿真的地形下拉框对所有机型共用这一套地图。
地图 = 纯环境（灯光 / 材质 / 地形几何），**不含机器人** —— 服务端下发时按机型注入
`<include file="../model/robot.xml"/>`（见 `backend/simulation_browser.py::map_scene_xml`），
同一张图可跑四足 / 轮足 / 人形 / 灵巧手。

## 约定

- 新增地图 = 往本目录加一份**环境专用** XML（不得 include 任何机型模型）+ 在 `_index.json` 登记；
  各机型自动出现在地形下拉框，无需改机器人包。
- 机型专属任务场景（如 wuji 的掌心朝上 + 立方体、go2 的 PIE 跑酷楼梯）**不进这里**，
  仍留在各包 `simulation/`，由包 config 的 `terrains` 声明；id 冲突时**包声明优先**。
- `web/sim2sim/assets/go2/*.xml` 保留为 go2/fsdog 内置旧链路（bundled flow）的静态资源，
  新链路一律走本库 + `/api/simulation/browser-package/<robot>/maps/<id>.xml`。

## 地图清单

| id | 说明 | 来源 |
|---|---|---|
| flat | 平地 | 1000framesai go2 参考 |
| stairs / cross_stairs | 楼梯 / 交叉楼梯 | 1000framesai go2 参考 |
| high_platforms | 高台（30-100 cm） | 1000framesai go2 参考 |
| cross_slope / race_track | 横坡 / 赛道 | 1000framesai go2 参考 |
| rough / slope | 粗糙地形 / 斜坡 | zex-w（rc_old 比赛场地） |
| relief | 起伏围场 | microduck-simulator |
| apartment | 公寓室内 | microduck 上游场景 |
| robocon_dual_track | RC2026障碍赛（比赛地图，15×12 m 整场，1623 geom） | lain_job/ArenaX terrain_library |

索引机器可读版：`_index.json`（`map-library-1.0`）。

> 本库 XML 一律**不声明 `compiler.angle`**：地图跨机型共用，而各机型 `model/robot.xml` 都是
> `angle="radian"`（且 tron1/g1/go1/zex-w 的模型里有 `euler/axisangle/xyaxes` 这类角度型属性），
> 地图一旦声明 `degree` 就会**覆盖被包含机型的单位**，那些机型全歪。所以导入外部地形时，
> 把它的 `euler="…"`（度）换算成等价的 `quat="…"` 再入库
> （`robocon_dual_track.xml` 就是这么做的，106 处，已用 MuJoCo 编译对拍 geom 位姿）。
