# tdt-nav-kit — 参考资源

> **来源**：`00_open/tdt-nav-kit/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、limx_tron1_pf（逐际动力 TRON1-PF）、limx_tron1_sf（逐际动力 TRON1-SF）、limx_tron1_wf（逐际动力 TRON1-WF）
> **定位**：TDT 二维栅格导航算法组件（A*/Kinodynamic A* 前端 + Minimum-Snap/OSQP 轨迹后端，C++）——H 组导航规划参考
> **收录**：19 个文件 / 258 KB（其中推理策略/模型文件 0 个）
> **已省略**：6 个文件 / 260 KB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **文档与其它**（19 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （6 个文件）
3rd/  （1 个文件）
    (直接文件)/
doc/  （3 个文件）
    (直接文件)/
scripts/  （1 个文件）
    (直接文件)/
src/  （8 个文件）
    MinimumSnapOsqp/
    YAstar/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.cpp` | 5 |
| `(无扩展名)` | 4 |
| `.md` | 4 |
| `.hpp` | 4 |
| `.txt` | 1 |
| `.sh` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
.gitmodules
3rd/.gitkeep
CMakeLists.txt
LICENCE
README.md
doc/Astar.md
doc/MinimumSnap.md
doc/Usage.md
main.cpp
scripts/setup.sh
src/MinimumSnapOsqp/minimumSnap.cpp
src/MinimumSnapOsqp/minimumSnap.hpp
src/MinimumSnapOsqp/sfcSquare.cpp
src/MinimumSnapOsqp/sfcSquare.hpp
src/YAstar/kinodynamicAstar.cpp
src/YAstar/kinodynamicAstar.hpp
src/YAstar/yastar.cpp
src/YAstar/yastar.hpp
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `images` | 6 | 260 KB | [`images/_OMITTED.md`](./images/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
