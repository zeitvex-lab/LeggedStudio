# sim.stackforce.cc — 参考资源

> **来源**：`00_open/sim.stackforce.cc/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：stackforce 仿真站点参考资源
> **收录**：64 个文件 / 4.0 MB（其中推理策略/模型文件 0 个）
> **已省略**：168 个文件 / 174.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（10 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **文档与其它**（54 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （8 个文件）
_analysis/  （7 个文件）
    (直接文件)/
sim.stackforce.cc/  （49 个文件）
    (直接文件)/
    _next/
    api_snapshots/
    sim.stackforce.cc/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.md` | 20 |
| `.js` | 17 |
| `.txt` | 12 |
| `.urdf` | 8 |
| `.py` | 3 |
| `.jsonl` | 2 |
| `.html` | 1 |
| `.css` | 1 |

## 文件索引（项目内相对路径）

```text
SUMMARY.md
_analysis/ui_strings_chunk117.txt
_analysis/ui_strings_chunk520.txt
_analysis/ui_strings_chunk595.txt
_analysis/ui_strings_chunk813.txt
_analysis/ui_strings_chunk862.txt
_analysis/ui_strings_layout.txt
_analysis/ui_strings_page.txt
_crawl2.py
_dl_log.jsonl
_dl_log2.jsonl
_extract_strings.py
_fetch.py
_urls.txt
index.html
sim.stackforce.cc/_next/static/chunks/117-2ee3bdcd70c3e40c.js
sim.stackforce.cc/_next/static/chunks/520-eb9aebf56d2f93f7.js
sim.stackforce.cc/_next/static/chunks/595.37abfba7757430ff.js
sim.stackforce.cc/_next/static/chunks/726.4e3ad189194e715e.js
sim.stackforce.cc/_next/static/chunks/806-3e067aea5513f35e.js
sim.stackforce.cc/_next/static/chunks/813.a483af6207812705.js
sim.stackforce.cc/_next/static/chunks/862-cd6ccb43afd19fbd.js
sim.stackforce.cc/_next/static/chunks/app/layout-998e3b0ec6d3e0a1.js
sim.stackforce.cc/_next/static/chunks/app/page-436aa2d611eaef8a.js
sim.stackforce.cc/_next/static/chunks/b536a0f1-e095b8572862d2c1.js
sim.stackforce.cc/_next/static/chunks/fd9d1056-5bc63bfeed71c730.js
sim.stackforce.cc/_next/static/chunks/main-app-f6f96cbb11f9d1b2.js
sim.stackforce.cc/_next/static/chunks/pages/_error-7ba65e1336b92748.js
sim.stackforce.cc/_next/static/chunks/polyfills-42372ed130431b0a.js
sim.stackforce.cc/_next/static/chunks/webpack-05254f693c87e932.js
sim.stackforce.cc/_next/static/css/4d6465c0376a66b5.css
sim.stackforce.cc/_next/static/ozYDHUU0OClC7t3lgx_KH/_buildManifest.js
sim.stackforce.cc/_next/static/ozYDHUU0OClC7t3lgx_KH/_ssgManifest.js
sim.stackforce.cc/api_snapshots/env-script-isaac_gym.txt
sim.stackforce.cc/api_snapshots/env-script-isaac_lab.txt
sim.stackforce.cc/api_snapshots/env-script-mjlab.txt
sim.stackforce.cc/robots.txt
sim.stackforce.cc/sim.stackforce.cc/examples/robots/12自由度菠萝狗/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/SF双足带脚底板/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/SF双足点足/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/SF大轮足/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/SF小轮足/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/SF舵机四轮足/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/aliengo_description/urdf/aliengo.urdf
sim.stackforce.cc/sim.stackforce.cc/examples/robots/anymal-softfoot-q/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/anymal_b/urdf/anymal_b.urdf
sim.stackforce.cc/sim.stackforce.cc/examples/robots/anymal_c/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/b2_description/urdf/b2_description.urdf
sim.stackforce.cc/sim.stackforce.cc/examples/robots/g1_description/urdf/g1_29dof.urdf
sim.stackforce.cc/sim.stackforce.cc/examples/robots/g1_description/urdf/meshes/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/go1_description/urdf/go1.urdf
sim.stackforce.cc/sim.stackforce.cc/examples/robots/go2_description/dae/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/gr1/urdf/gr1t1.urdf
sim.stackforce.cc/sim.stackforce.cc/examples/robots/lite3/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/robotamer_qmini/urdf/q1.urdf
sim.stackforce.cc/sim.stackforce.cc/examples/robots/simplified-quadruped/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/solo12/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/x30/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/xbot_l/urdf/XBot-L.urdf
sim.stackforce.cc/sim.stackforce.cc/examples/robots/宇树A1/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/菠萝狗/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/逐际带脚底板双足/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/逐际点足/_NOT_DOWNLOADED_占位.md
sim.stackforce.cc/sim.stackforce.cc/examples/robots/逐际轮足/_NOT_DOWNLOADED_占位.md
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 24 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `sim.stackforce.cc` | 1 | 912 B | [`sim.stackforce.cc/_OMITTED.md`](./sim.stackforce.cc/_OMITTED.md) |
| `sim.stackforce.cc/sim.stackforce.cc/examples/robots/aliengo_description/meshes` | 6 | 6.0 MB | [`sim.stackforce.cc/sim.stackforce.cc/examples/robots/aliengo_description/meshes/_OMITTED.md`](./sim.stackforce.cc/sim.stackforce.cc/examples/robots/aliengo_description/meshes/_OMITTED.md) |
| `sim.stackforce.cc/sim.stackforce.cc/examples/robots/anymal_b/meshes` | 3 | 11.8 MB | [`sim.stackforce.cc/sim.stackforce.cc/examples/robots/anymal_b/meshes/_OMITTED.md`](./sim.stackforce.cc/sim.stackforce.cc/examples/robots/anymal_b/meshes/_OMITTED.md) |
| `sim.stackforce.cc/sim.stackforce.cc/examples/robots/b2_description/meshes` | 13 | 19.6 MB | [`sim.stackforce.cc/sim.stackforce.cc/examples/robots/b2_description/meshes/_OMITTED.md`](./sim.stackforce.cc/sim.stackforce.cc/examples/robots/b2_description/meshes/_OMITTED.md) |
| `sim.stackforce.cc/sim.stackforce.cc/examples/robots/go1_description/meshes` | 7 | 68.9 MB | [`sim.stackforce.cc/sim.stackforce.cc/examples/robots/go1_description/meshes/_OMITTED.md`](./sim.stackforce.cc/sim.stackforce.cc/examples/robots/go1_description/meshes/_OMITTED.md) |
| `sim.stackforce.cc/sim.stackforce.cc/examples/robots/go2_description/dae` | 6 | 14.5 MB | [`sim.stackforce.cc/sim.stackforce.cc/examples/robots/go2_description/dae/_OMITTED.md`](./sim.stackforce.cc/sim.stackforce.cc/examples/robots/go2_description/dae/_OMITTED.md) |
| `sim.stackforce.cc/sim.stackforce.cc/examples/robots/gr1/meshes/gr1t1` | 35 | 17.6 MB | [`sim.stackforce.cc/sim.stackforce.cc/examples/robots/gr1/meshes/gr1t1/_OMITTED.md`](./sim.stackforce.cc/sim.stackforce.cc/examples/robots/gr1/meshes/gr1t1/_OMITTED.md) |
| `sim.stackforce.cc/sim.stackforce.cc/examples/robots/robotamer_qmini/meshes` | 11 | 22.4 MB | [`sim.stackforce.cc/sim.stackforce.cc/examples/robots/robotamer_qmini/meshes/_OMITTED.md`](./sim.stackforce.cc/sim.stackforce.cc/examples/robots/robotamer_qmini/meshes/_OMITTED.md) |
| `sim.stackforce.cc/sim.stackforce.cc/examples/robots/xbot_l/meshes` | 85 | 13.2 MB | [`sim.stackforce.cc/sim.stackforce.cc/examples/robots/xbot_l/meshes/_OMITTED.md`](./sim.stackforce.cc/sim.stackforce.cc/examples/robots/xbot_l/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
