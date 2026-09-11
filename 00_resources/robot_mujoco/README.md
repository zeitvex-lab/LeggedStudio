# robot_mujoco — 参考资源

> **来源**：`00_open/robot_mujoco/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）、unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_b2（宇树 B2 四足）、unitree_b2w（宇树 B2W 轮足）、unitree_g1（宇树 G1 人形）、deeprobotics_lite3（云深处 Lite3 四足）
> **定位**：多机型 MuJoCo 资产与场景
> **收录**：80 个文件 / 1.9 MB（其中推理策略/模型文件 0 个）
> **已省略**：368 个文件 / 509.3 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（28 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（1 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（49 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **文档与其它**（2 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （2 个文件）
jszr_robots/  （77 个文件）
    D1/
    b2/
    b2w/
    go2/
    go2w/
    h1/
    lite3/
    xg/
    xgb/
    xgw/
    zg/
    zgw/
    zgws/
simulate/  （1 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.xml` | 70 |
| `.urdf` | 7 |
| `(无扩展名)` | 2 |
| `.yaml` | 1 |

## 文件索引（项目内相对路径）

```text
.git
.gitignore
jszr_robots/D1/D1.urdf
jszr_robots/D1/D1.xml
jszr_robots/D1/scene_terrain.xml
jszr_robots/b2/b2.xml
jszr_robots/b2/scene.xml
jszr_robots/b2/scene_terrain.xml
jszr_robots/b2w/b2w.xml
jszr_robots/b2w/scene.xml
jszr_robots/b2w/scene_terrain.xml
jszr_robots/go2/go2.xml
jszr_robots/go2/scene.xml
jszr_robots/go2/scene_terrain.xml
jszr_robots/go2w/go2w.xml
jszr_robots/go2w/scene.xml
jszr_robots/go2w/scene_terrain.xml
jszr_robots/h1/h1.xml
jszr_robots/h1/scene.xml
jszr_robots/h1/scene_terrain.xml
jszr_robots/lite3/lite3.urdf
jszr_robots/lite3/lite3.xml
jszr_robots/lite3/scene_terrain.xml
jszr_robots/xg/XG.xml
jszr_robots/xg/scene_terrain.xml
jszr_robots/xgb/scene.xml
jszr_robots/xgb/scene_terrain.xml
jszr_robots/xgb/scene_terrain_apart.xml
jszr_robots/xgb/scene_terrain_cozy.xml
jszr_robots/xgb/scene_terrain_crowd.xml
jszr_robots/xgb/scene_terrain_flat.xml
jszr_robots/xgb/scene_terrain_house.xml
jszr_robots/xgb/scene_terrain_maze.xml
jszr_robots/xgb/scene_terrain_rw.xml
jszr_robots/xgb/scene_terrain_sloped.xml
jszr_robots/xgb/scene_terrain_t10.xml
jszr_robots/xgb/scene_terrain_venice.xml
jszr_robots/xgb/scene_terrain_wh.xml
jszr_robots/xgb/scene_terrain_yard.xml
jszr_robots/xgb/xg_b.urdf
jszr_robots/xgb/xgb.xml
jszr_robots/xgb/xgb_game.xml
jszr_robots/xgw/scene_terrain.xml
jszr_robots/xgw/scene_terrain_apart.xml
jszr_robots/xgw/scene_terrain_cozy.xml
jszr_robots/xgw/scene_terrain_crowd.xml
jszr_robots/xgw/scene_terrain_flat.xml
jszr_robots/xgw/scene_terrain_house.xml
jszr_robots/xgw/scene_terrain_maze.xml
jszr_robots/xgw/scene_terrain_rw.xml
jszr_robots/xgw/scene_terrain_sloped.xml
jszr_robots/xgw/scene_terrain_t10.xml
jszr_robots/xgw/scene_terrain_venice.xml
jszr_robots/xgw/scene_terrain_wh.xml
jszr_robots/xgw/scene_terrain_yard.xml
jszr_robots/xgw/xg_wheel.urdf
jszr_robots/xgw/xg_wheel.xml
jszr_robots/zg/scene_terrain.xml
jszr_robots/zg/zg.urdf
jszr_robots/zg/zg.xml
jszr_robots/zgw/assets/zg_wheel.urdf
jszr_robots/zgw/scene_terrain.xml
jszr_robots/zgw/zg_wheel.urdf
jszr_robots/zgw/zgw.xml
jszr_robots/zgws/Venice.xml
jszr_robots/zgws/scene_terrain.xml
jszr_robots/zgws/scene_terrain_apart.xml
jszr_robots/zgws/scene_terrain_cozy.xml
jszr_robots/zgws/scene_terrain_crowd.xml
jszr_robots/zgws/scene_terrain_flat.xml
jszr_robots/zgws/scene_terrain_house.xml
jszr_robots/zgws/scene_terrain_maze.xml
jszr_robots/zgws/scene_terrain_rw.xml
jszr_robots/zgws/scene_terrain_sloped.xml
jszr_robots/zgws/scene_terrain_t10.xml
jszr_robots/zgws/scene_terrain_venice.xml
jszr_robots/zgws/scene_terrain_wh.xml
jszr_robots/zgws/scene_terrain_yard.xml
jszr_robots/zgws/zgws.xml
simulate/config.yaml
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `jszr_robots/D1` | 2 | 19 KB | [`jszr_robots/D1/_OMITTED.md`](./jszr_robots/D1/_OMITTED.md) |
| `jszr_robots/D1/assets` | 17 | 6.1 MB | [`jszr_robots/D1/assets/_OMITTED.md`](./jszr_robots/D1/assets/_OMITTED.md) |
| `jszr_robots/b2` | 3 | 669 KB | [`jszr_robots/b2/_OMITTED.md`](./jszr_robots/b2/_OMITTED.md) |
| `jszr_robots/b2/assets` | 31 | 30.1 MB | [`jszr_robots/b2/assets/_OMITTED.md`](./jszr_robots/b2/assets/_OMITTED.md) |
| `jszr_robots/b2w` | 3 | 689 KB | [`jszr_robots/b2w/_OMITTED.md`](./jszr_robots/b2w/_OMITTED.md) |
| `jszr_robots/b2w/assets` | 35 | 36.2 MB | [`jszr_robots/b2w/assets/_OMITTED.md`](./jszr_robots/b2w/assets/_OMITTED.md) |
| `jszr_robots/go2` | 3 | 629 KB | [`jszr_robots/go2/_OMITTED.md`](./jszr_robots/go2/_OMITTED.md) |
| `jszr_robots/go2/assets` | 16 | 27.1 MB | [`jszr_robots/go2/assets/_OMITTED.md`](./jszr_robots/go2/assets/_OMITTED.md) |
| `jszr_robots/go2w` | 2 | 19 KB | [`jszr_robots/go2w/_OMITTED.md`](./jszr_robots/go2w/_OMITTED.md) |
| `jszr_robots/go2w/assets` | 22 | 32.0 MB | [`jszr_robots/go2w/assets/_OMITTED.md`](./jszr_robots/go2w/assets/_OMITTED.md) |
| `jszr_robots/h1` | 3 | 789 KB | [`jszr_robots/h1/_OMITTED.md`](./jszr_robots/h1/_OMITTED.md) |
| `jszr_robots/h1/assets` | 51 | 29.3 MB | [`jszr_robots/h1/assets/_OMITTED.md`](./jszr_robots/h1/assets/_OMITTED.md) |
| `jszr_robots/lite3/assets` | 28 | 85.4 MB | [`jszr_robots/lite3/assets/_OMITTED.md`](./jszr_robots/lite3/assets/_OMITTED.md) |
| `jszr_robots/lite3/assets/tex` | 2 | 175 KB | [`jszr_robots/lite3/assets/tex/_OMITTED.md`](./jszr_robots/lite3/assets/tex/_OMITTED.md) |
| `jszr_robots/xg` | 1 | 5 KB | [`jszr_robots/xg/_OMITTED.md`](./jszr_robots/xg/_OMITTED.md) |
| `jszr_robots/xg/assets` | 17 | 50.7 MB | [`jszr_robots/xg/assets/_OMITTED.md`](./jszr_robots/xg/assets/_OMITTED.md) |
| `jszr_robots/xgb` | 3 | 47 KB | [`jszr_robots/xgb/_OMITTED.md`](./jszr_robots/xgb/_OMITTED.md) |
| `jszr_robots/xgb/assets` | 26 | 12.0 MB | [`jszr_robots/xgb/assets/_OMITTED.md`](./jszr_robots/xgb/assets/_OMITTED.md) |
| `jszr_robots/xgw` | 2 | 19 KB | [`jszr_robots/xgw/_OMITTED.md`](./jszr_robots/xgw/_OMITTED.md) |
| `jszr_robots/xgw/assets` | 27 | 15.9 MB | [`jszr_robots/xgw/assets/_OMITTED.md`](./jszr_robots/xgw/assets/_OMITTED.md) |
| `jszr_robots/zg` | 2 | 19 KB | [`jszr_robots/zg/_OMITTED.md`](./jszr_robots/zg/_OMITTED.md) |
| `jszr_robots/zg/assets` | 17 | 83.7 MB | [`jszr_robots/zg/assets/_OMITTED.md`](./jszr_robots/zg/assets/_OMITTED.md) |
| `jszr_robots/zgw` | 2 | 19 KB | [`jszr_robots/zgw/_OMITTED.md`](./jszr_robots/zgw/_OMITTED.md) |
| `jszr_robots/zgw/assets` | 25 | 44.4 MB | [`jszr_robots/zgw/assets/_OMITTED.md`](./jszr_robots/zgw/assets/_OMITTED.md) |
| `jszr_robots/zgws` | 2 | 19 KB | [`jszr_robots/zgws/_OMITTED.md`](./jszr_robots/zgws/_OMITTED.md) |
| `jszr_robots/zgws/assets` | 26 | 53.4 MB | [`jszr_robots/zgws/assets/_OMITTED.md`](./jszr_robots/zgws/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
