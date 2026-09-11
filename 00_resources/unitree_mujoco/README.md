# unitree_mujoco — 参考资源

> **来源**：`00_open/unitree_mujoco/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）、unitree_go2（宇树 Go2 四足）、unitree_g1（宇树 G1 人形）
> **定位**：宇树官方 MuJoCo 仿真器与机型 XML（Go1/Go2/G1）
> **收录**：11 个文件 / 148 KB（其中推理策略/模型文件 0 个）
> **已省略**：20 个文件 / 22.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（4 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **评测与测试**（1 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（6 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （3 个文件）
data/  （8 个文件）
    a1/
    aliengo/
    go1/
    laikago/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.urdf` | 4 |
| `.xml` | 4 |
| `(无扩展名)` | 1 |
| `.py` | 1 |
| `.md` | 1 |

## 文件索引（项目内相对路径）

```text
LICENSE
README.md
data/a1/urdf/a1.urdf
data/a1/xml/a1.xml
data/aliengo/urdf/aliengo.urdf
data/aliengo/xml/aliengo.xml
data/go1/urdf/go1.urdf
data/go1/xml/go1.xml
data/laikago/urdf/laikago.urdf
data/laikago/xml/laikago.xml
mujoco_py_test.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `data/a1/meshes` | 5 | 6.8 MB | [`data/a1/meshes/_OMITTED.md`](./data/a1/meshes/_OMITTED.md) |
| `data/aliengo/meshes` | 5 | 3.3 MB | [`data/aliengo/meshes/_OMITTED.md`](./data/aliengo/meshes/_OMITTED.md) |
| `data/go1/meshes` | 5 | 9.8 MB | [`data/go1/meshes/_OMITTED.md`](./data/go1/meshes/_OMITTED.md) |
| `data/laikago/meshes` | 5 | 2.0 MB | [`data/laikago/meshes/_OMITTED.md`](./data/laikago/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
