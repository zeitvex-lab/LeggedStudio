# PCD 地图查看和打点工具

这是离线 Web 工具，用于查看 Odin PCD 地图和保存路线点。它不是 Nano 运行时 Web。

## 归档依赖边界

当前仓库归档了 Python 服务端和前端源码，但原工程使用的 Three.js 静态文件没有随快照保存。因此，全新克隆后不能直接使用三维页面，需先补充同一 Three.js 版本的两个文件：

```text
tools/pcd_map_viewer/vendor/three.module.js
tools/pcd_map_viewer/vendor/jsm/controls/OrbitControls.js
```

也可以通过 `--vendor-dir` 指定外部目录。原始版本号和再分发条款没有留在快照中，所以仓库不擅自补入一个无法证明兼容的版本。

## 启动

在仓库根目录：

```powershell
python .\05_software\real\sim2real_ros2_v2\tools\pcd_map_viewer\server.py --http-port 8090
```

若使用外部依赖目录：

```powershell
python .\05_software\real\sim2real_ros2_v2\tools\pcd_map_viewer\server.py --vendor-dir C:\path\to\three-vendor --http-port 8090
```

打开：

```text
http://127.0.0.1:8090
```

路线点保存：

- `x`
- `y`
- `yaw_deg`
- `speed`
- `policy`
- `tolerance`

不保存 `z` 和 `action`。

当前 `v0.12.0` 运行配置使用 `map/routes/A_min/A_min_route.json`。编辑器也能保存 YAML，但本快照没有旧文档曾描述的 `/route_runner/cmd` 控制接口。

地图抽样边界见 [`../../map/README.md`](../../map/README.md)，版本说明见 [`../../README.md`](../../README.md)。
