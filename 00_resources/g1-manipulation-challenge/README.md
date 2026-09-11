# g1-manipulation-challenge — 参考资源

> **来源**：`00_open/g1-manipulation-challenge/`　｜　**类型**：参考项目
> **关联机型**：unitree_g1（宇树 G1 人形）
> **定位**：G1 操作挑战赛工程
> **收录**：14 个文件 / 3.6 MB（其中推理策略/模型文件 4 个）
> **已省略**：49 个文件 / 139.7 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（1 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（1 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（4 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（8 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （14 个文件）
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.onnx` | 4 |
| `.data` | 4 |
| `.xml` | 2 |
| `(无扩展名)` | 1 |
| `.json` | 1 |
| `.md` | 1 |
| `.py` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
README.md
croucher.onnx
croucher.onnx.data
g1.xml
model_config.json
right_reacher.onnx
right_reacher.onnx.data
rotator.onnx
rotator.onnx.data
run.py
scene.xml
walker.onnx
walker.onnx.data
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `assets` | 49 | 139.7 MB | [`assets/_OMITTED.md`](./assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
