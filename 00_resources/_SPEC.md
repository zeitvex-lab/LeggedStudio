# 00_resources/ — 提取规范（v3：以「项目」为单位）

> 版本：v3.1 ｜ 日期：2026-09-11 ｜ 脚本：[`../tools/sync_resources.py`](../tools/sync_resources.py)
> 执行：`python legged_studio/tools/sync_resources.py [--clean] [--only <project>] [--dry-run]`

## 1. 组织原则

1. **以项目为单位**：一个来源项目 = 一个目录 `00_resources/<project>/`，**原样保留该项目的目录结构与组织思想**，
   路径与 `00_open/<project>/` 逐级对应。不再按机型拆成十几份重复拷贝。
2. **机型归属写在索引里**：项目与 14 机型的对应关系记录在各项目 `README.md` 与根 `README.md` 的
   「项目清单 / 机型反查」中，不通过目录重复体现。
3. **只读参考底座**：本目录不参与运行时加载；归一化可执行资产在 [`../assets/robots/`](../assets/robots/)。
4. **不做适配、不改写**：拷贝即原样拷贝，保留来源项目的文件名与组织方式。

## 2. 保留（拷贝）

| 类别 | 扩展名（示例） |
|---|---|
| 源码 / 脚本 | `.py .pyx .cpp .cc .c .h .hpp .cu .cuh .java .js .ts .jsx .tsx .vue .sh .ps1 .bat .cmd .ipynb .proto .srv .msg .action .cmake .mk .sql .rs .go .lua` |
| 配置 / 机型描述 | `.yaml .yml .json .toml .ini .cfg .conf .xml .urdf .xacro .sdf .launch .world .txt .csv .tsv .env` |
| 文档 | `.md .rst .tex .bib` |
| 数据 | `.npz .npy .pkl .mat .msgpack`（受 20MB 限制） |
| **推理策略 / 模型** | `.onnx .pt .pth .engine .plan .trt .ckpt .safetensors .tflite .jit .mlpackage .rknn .mnn .dlc`（**不限大小**，仅 4GB 兜底） |
| 无扩展名文本 | `Makefile / Dockerfile / LICENSE / CMakeLists.txt` 等，且 < 20MB |

其余未知扩展名一律**保留**（< 20MB），宁可多留。

## 3. 省略（不拷贝，但在原目录留 `_OMITTED.md` 占位登记）

| 类别 | 扩展名 |
|---|---|
| 3D 网格 | `.stl .obj .dae .glb .gltf .fbx .ply .3mf .mesh .wrl .3ds .max .skp` |
| CAD 几何 | `.step .stp .igs .iges .sldprt .sldasm` |
| 3D 工程 / 二进制场景 | `.blend .abc .x3d .usd .usda .usdc .usdz .c4d .mb .ma .mjz` |
| 点云 | `.pcd .las .laz .e57` |
| ROS 录包 | `.bag .bag2 .db3 .mcap .pcap .bt` |
| 归档 / 安装包 | `.zip .tar .tgz .gz .bz2 .xz .7z .rar .whl .deb .rpm .apk .conda .jar .egg` |
| 可执行 / 二进制 | `.so .dll .dylib .a .lib .exe .bin .class .pyc .pyo .o .elf .hex .msi .dmg .appimage .wasm .node` |
| 版本化二进制库 | 扩展名为纯数字者（如 `libonnxruntime.so.1`、`libfoo.so.1.22.0` 的 `.1` / `.0`） |
| 视频 / 动图 / 音频 | `.mp4 .avi .mov .mkv .webm .flv .wmv .m4v .mpg .gif` / `.mp3 .wav .ogg .flac .aac .m4a .opus .mid` |
| 图像 / 纹理 | `.png .jpg .jpeg .bmp .webp .tif .tiff .exr .hdr .ppm .pgm .tga .dds .ktx .psd .ai .ico .icon .svg .xcf .spr` |
| 字体 | `.ttf .otf .woff .woff2 .eot` |
| 大数据表 | `.h5 .hdf5 .sqlite .db .mdb` |
| 日志 / 缓存 | `.log .lock .cache .pack .idx` |
| 体积超限 | 任意文件 > **20MB**（策略文件除外） |

**占位形式**：受影响目录生成一个 `_OMITTED.md`，逐条登记
`文件 | 体积 | 类型 | 源路径`，源路径形如 `00_open/<project>/<dir>/<file>`，可直接取用。
目录（含仅有省略文件的目录）**保留**，因此项目结构不丢。

## 4. 整目录跳过（不登记、不建空目录）

`.git`、`__pycache__`、`.venv` / `venv` / `.conda`、`node_modules`、`.pytest_cache` / `.mypy_cache` /
`.ruff_cache`、`.idea` / `.vscode`、`.ipynb_checkpoints`、`.eggs`、`CMakeFiles`、`.mimic`、`.cache`、`.next`、
`build/`、`dist/`、`outputs/`、`logs/`。

## 5. 目录结构

```
00_resources/
  README.md              # 总索引：总览 / 项目清单 / 项目定位 / 机型反查 / 知识库 / 未纳入项目
  _SPEC.md               # 本文件
  _index.json            # 机器可读索引（项目 × 机型 × 计数 × 策略规则）
  knowledge_base/        # 非机型知识库（14 机型共用参考）
    <name>/README.md     #   知识库说明 + 文件索引
  <project>/             # 一个来源项目一个目录
    README.md            #   来源 / 关联机型 / 定位 / 能帮什么 / 目录构成 / 类型分布 / 文件索引 / 省略索引
    <原项目目录结构>/     #   有用文件原样拷贝
      _OMITTED.md        #   该目录被省略文件的占位登记
```

## 6. 项目清单（收集范围）

- **纳入**（脚本 `PROJECTS`，共 **89** 个条目 = 机型相关 **76** + 跨机型参考 **12** + 知识库 1〔`robo_know` → `knowledge_base/`〕，另加 `knowledge_base/Robotics_Tutorial`）：
  1. **机型相关**（76 个）：与 14 个目标机型相关的参考项目，参与「机型 → 项目反查」；
  2. **跨机型参考**（10 个，`robots: []`，不进入机型反查）：
     - `urdf_tool` —— 机器人资产查看与验证工具参考（`robot_viewer` / `URDF-Studio`）；
     - `jie_3d_nav` —— 导航与感知参考（`jie_octomap` + `octo_planner`）；
     - `mjlab-skillkit` —— Isaac Lab → mjlab 移植参考（`adapters` / `agents` / `shared`）；
     - `wandb`（源目录 `auto_web/wandb`）—— 训练任务跟踪与可视化平台参考（Go core + Python SDK）；
     - `genesis-world` / `newton` —— 物理引擎（多物理 / GPU 可微）参考；
     - `PaddleX` —— 视觉模型产线（只借配置组织与导出 ONNX）；
     - `mujoco_ros2_control` —— ros2_control × MuJoCo 控制器接口参考；
     - `engineai_rl_workspace`（2026-09-23）—— 人形/四足 RL 训练·评测一体框架参考（PM01/SA01）；
     - `legged_gym` / `humanoid-gym`（2026-09-23）—— 前者的两个上游（legged_gym 原始范式 / 人形 reward·terrain 组织）；
     - `Link-U-OS`（2026-09-23）—— 具身智能 OS 参考（AimRT 中间件 / Bazel 交叉编译 / ros2_control 部署 / AimStudio，含 13 个外链子仓）。
- **不纳入**：通用工具与素材（`auto_web` 的其余部分、`ComfyUI`、`InvokeAI`、`langflow`、`n8n`、
  `tools`、`archive`）、非目标机型（`dm_dog`、`min_dog`）、仅网格的描述汇总
  （`awesome-robot-descriptions`）、通用知识文档（`robo_know`，其教程已单独纳入知识库）。
  以上仅记入根 README 的「未纳入项目」说明。

## 7. 回溯与恢复

1. `00_resources/<project>/<rel>` ↔ `00_open/<project>/<rel>` 一一对应。
2. 目录内 `_OMITTED.md` 的「源路径」列即被省略文件的原位置。
3. 需恢复某类文件：调整脚本 `OMIT_EXTS` / 阈值后执行
   `python legged_studio/tools/sync_resources.py --only <project>`。

## 8. 变更记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v3.3 | 2026-09-23 | **新增 4 个跨机型参考项目**（用户指定外链：`MeredithRowe/engineai_rl_workspace`、`Link-U-OS/Link-U-OS` 及其 `.gitmodules` 点名的 **13 个子仓**，外加前者 README 致谢点名的上游 **`legged_gym` / `humanoid-gym`**）：均**不含 14 机型**（人形 / 四足 / OS 栈），`robots: []`；§6 计数同步为 **89** 条目（机型相关 76 + 跨机型参考 12 + 知识库 1）并把跨机型子列表补全（此前只列 4 条，`genesis-world`/`newton`/`PaddleX`/`mujoco_ros2_control` 未列）。源快照放在**工作区外** `<外部工作区>/00_open/`（用户口径：克隆不进当前工作区），`_SOURCE.md` 登记 4 仓 + 13 子仓的仓库地址与提交号；作用分析见 [`../00_know/03_参考项目与资源.md`](../00_know/03_参考项目与资源.md) §5.3 |
| v3.2 | 2026-09-11 | **新增 4 个跨机型参考项目**（`urdf_tool` / `jie_3d_nav` / `mjlab-skillkit` / `wandb`）：资产查看与验证、导航与感知、Isaac→mjlab 移植、训练任务跟踪四类参考。`PROJECTS` 新增 `"src"`（源目录可指向嵌套路径）与 `"kind"`（参考类型）字段；这 4 项 `robots` 为空，不参与机型反查 |
| v3.1 | 2026-09-11 | **目录由 `resources/` 改名为 `00_resources/`**（与 `00_know/` 同为「资料类目录」，`00_` 前缀表示不参与运行时加载）；脚本 `RES_ROOT`、根 README、`docs/`、`00_know/` 交叉引用与全部生成文档（项目 README / `_OMITTED.md`）同步更新。**提取规则本身未变** |
| v3 | 2026-09-11 | **改为以项目为单位**（不再按机型复制多份）；省略项在原目录留 `_OMITTED.md` 占位；新增 `_index.json` 与项目级「能帮什么 / 关联机型」索引；普通文件 20MB 上限、策略文件不限 |
| v2 | 2026-09-10 | 按「机型 × 功能类别」抽取 14 份；文本/框架源码全收；二进制只登记不拷贝 |
| v1 | 2026-09-09 | 按机型抽取核心资产 |
