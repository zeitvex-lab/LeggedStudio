# URDF Studio 测试脚本

## 数据准备

```bash
npm run test:setup                # 一键克隆所有
npm run test:setup:mujoco         # MJCF (mujoco_menagerie)
npm run test:setup:unitree-usd    # USD (HuggingFace unitree_model)
npm run test:setup:unitree-urdf   # URDF (unitree_ros)
```

## 功能覆盖矩阵

| 功能                  | 测试脚本                                   | 覆盖点                                                                                                                                               |
| --------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **模型导入**          | `test:browser:mujoco-import`               | 6 个 MJCF 模型加载，link/joint 数量，robot name                                                                                                      |
| **结构树 CRUD**       | `test:browser:urdf-tree-crud` / `test:browser:mujoco-tree-crud` | addChild, deleteSubtree, deleteLink, renameLink, renameRobot, setLinkVisibility, setAllLinksVisibility, undo/redo (多轮)                             |
| **属性编辑**          | `test:browser:urdf-property-editor` / `test:browser:mujoco-property-editor` | joint origin/axis/limit/dynamics/friction/type, link visualCount/collisionCount/inertial, joint angle (单个+批量), property panel                    |
| **碰撞/显示**         | `test:browser:mujoco-viewer` / `test:browser:collision-opt` | showCollision, showJointAxes, showOrigins, showCenterOfMass, showInertia, tool mode 切换, runtime transforms 联动, canvas                            |
| **物理/显示位姿真值** | `test:fixtures:physics-display-transforms` | MuJoCo(MJCF) / URDF / Xacro / SDF / USD / USDA 的惯量/质心、坐标轴、关节轴、visual/collision 位置                                                    |
| **源码编辑器**        | `test:browser:urdf-source-editor` / `test:browser:mujoco-source-editor` / `test:browser:source-apply-mujoco` | Monaco 编辑, auto-apply, XML 修改, re-import 恢复                                                                                                    |
| **组装拼接**          | `test:browser:urdf-assembly` / `test:browser:mujoco-assembly` / `test:browser:cross-format-assembly` | initAssembly, addComponent×2, updateComponentTransform, toggleComponentVisibility, addBridge, updateBridge, removeBridge, removeComponent, undo/redo |
| **导出验证**          | `test:browser:urdf-export` / `test:browser:mujoco-export` / `test:browser:mjcf-export` / `test:browser:assembly-export` | URDF/MJCF/XML 生成验证、重名检测、UI 导出选项、导出后状态完整性                                                            |
| **多格式导入**        | `test:browser:multi-format`                | URDF / MJCF / SDF / USD / Xacro / ZIP 等入口 smoke                                                                                                   |
| **Editor 深度回归**   | `test:browser:editor-deep-all`             | assembly / collision / source / materials / joints 深度路径                                                                                          |

## 运行

```bash
npm run test:browser:all                 # 全部浏览器测试
npm run test:browser:multi-format        # 多格式导入
npm run test:browser:mujoco-tree-crud    # MuJoCo 结构树
npm run test:browser:mujoco-property-editor  # MuJoCo 属性+碰撞
npm run test:browser:mujoco-viewer       # MuJoCo 显示+工具模式
npm run test:fixtures:physics-display-transforms # 多格式物理/显示位姿真值
npm run test:browser:mujoco-assembly     # MuJoCo 组装
npm run test:browser:mujoco-export       # MuJoCo 导出
npm run test:browser:editor-deep-all     # Editor 深度回归集合
```

测试后清理：`node test/usd-viewer/scripts/cleanup-headless.cjs`

## AI Agent 使用

```bash
npm run test:unit:list
npm run test:unit -- src/path/to/file.test.ts
npm run test:browser:all
```

浏览器测试复用 `browser/helpers/*-helpers.mjs` 和 `helpers/browser-helpers.mjs`，通过 `createSession()` 管理 dev server 和浏览器生命周期。
Store 操作通过 `store.*` 一行调用（addChild, updateJoint, undo 等）。
断言用 `assert`/`assertEqual`/`assertGreaterThan`，彩色输出 + 汇总。

## 目录

```
scripts/test/
├── setup/                          # 数据克隆
├── helpers/                        # 浏览器 / E2E 共用 helper
├── e2e/                            # 端到端场景测试
├── browser/
│   ├── helpers/mjcf-helpers.mjs    # 公共 helper (session, store, queries)
│   ├── test_mujoco_model_import.mjs
│   ├── test_mujoco_tree_crud.mjs
│   ├── test_mujoco_property_editor.mjs
│   ├── test_mujoco_viewer.mjs
│   ├── test_mujoco_source_editor.mjs
│   ├── test_mujoco_assembly.mjs
│   ├── test_mujoco_export.mjs
│   └── ... (现有回归脚本)
├── fixtures/                        # fixture 生成与导出辅助
├── runner/                          # Node/browser 聚合 runner
├── setup/                           # 数据克隆
├── truth/                           # 真值验证
├── benchmark/                       # 性能基准
└── README.md
```
