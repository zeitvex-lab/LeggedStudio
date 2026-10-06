<!-- 由 tools/gen_capability_seams.py 生成——真值是 registry/plugin-registry.json，手改会被覆盖。再生成：python tools/gen_capability_seams.py -->

# Capability Seams：能力面地图（机器生成）

一切即插件（`00_know/08` v3.0）：能力挂在 13 个冻结 seam 上，新增行为 = 加声明，不改框架。
真值：`registry/plugin-registry.json`（schema `plugin-registry-1.0`，
31 条注册表条目 + `registry/plugins/` 插件清单目录）。

## seam × 承载

| seam | 数据注册表 | 插件清单 | 状态 |
|---|---:|---:|---|
| algorithm | 1 | 0 | ✓ 有承载 |
| controller | 1 | 0 | ✓ 有承载 |
| evaluator | 2 | 0 | ✓ 有承载 |
| family | 3 | 0 | ✓ 有承载 |
| pack | 9 | 0 | ✓ 有承载 |
| panel | 0 | 9 | ✓ 有承载 |
| profile | 2 | 0 | ✓ 有承载 |
| reward | 3 | 0 | ✓ 有承载 |
| robot | 0 | 0 | —（该 seam 尚无声明，属待扩展位） |
| sensor | 2 | 0 | ✓ 有承载 |
| skill | 5 | 0 | ✓ 有承载 |
| task | 1 | 0 | ✓ 有承载 |
| terrain | 2 | 0 | ✓ 有承载 |

## 新增一个 X 该挂哪（新增能力不改框架代码）

| 要加什么 | seam | 声明落点 | 门禁 |
|---|---|---|---|
| 机器人 | robot | `assets/robots/<id>/`（契约 v3 + MJCF + 包声明，经 onboard 导入） | 包过校验进索引；族通用技能即插即训 |
| 形态族 | family | `registry/families/<id>.json` | `tools/audit_families.py` 全绿 |
| 技能 / 任务配方 | skill | `registry/skills/<recipe>.json`（K4：先登记 index 再放文件） | `backend/skill_registry` 校验 + 冒烟 |
| 地形档 | terrain | `registry/terrains/profiles.json` | `tools/audit_terrain_profiles.py` |
| 奖励项 / 预设 | reward | `registry/rewards/*.json` | 技能配方 reward_terms 引用可解析 |
| 算法插件 | algorithm | `adapters/mjlab/algorithms/<algo>/` + `registry.json` 登记 | `verify_plugin` fail-closed + `test_algorithm_plugins` |
| 任务插件（感知×判据） | task | `registry/task_plugins/index.json` | `contracts/task_plugin_contract` 同一道闸 |
| 传感器 / 感知 provider | sensor | `registry/perception_providers/`、`cameras.json` | `sensor_plugin_contract` 词表核对 |
| 验收判据 / 效果口径 | evaluator | `arrival_criteria.json`、`effect_criterion.json` | 判据声明可被验收器执行 |
| 页面 / 面板（四投影） | panel | `registry/plugins/panel/<id>.json`（legged-plugin-1.0） | manifest 校验 + provider 真 module:attr |
| 控制器（MPC 轴） | controller | `registry/controllers/index.json` | `backend/controller_plugins` fail-loud |
| 资源包 / 许可与出处 | pack | `registry/packs/`、`licenses.json`、`porting_*.json` | `tools/validate_packs.py` + `audit_licenses` |
| 训练 / 命令档位 | profile | `registry/tasks/profiles.json`、`motion_commands.json` | `runtime_registry` 总表派生 + schema 门 |

## 内核与投影

* 内核：`plugins/runtime.py`（服务上下文 + 事件五模式 + patch 整行替换；纯度由
  `backend/test_plugin_kernel_purity.py` AST 守卫：≤400 行 / 零本仓 import / 零业务词）。
* provider 解析：**真 `module:attr`**（importlib，可指向任何模块）——
  `backend/cli_panels.py::resolve_provider`。
* 统一度计数器：`tools/audit_plugin_unification.py --check`（旧机制只许减少不许回涨）。
