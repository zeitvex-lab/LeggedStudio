# RoboLab WebUI

P7 的第一版本地工作台，刻意与训练后端保持独立。它只通过已有的
`robolab workflow` 启动任务，不导入或修改 Isaac Gym/MJLab 内部实现。

```bash
cd /home/lxy/RoboLab
PYTHONPATH=src python webui/server.py
```

浏览器打开 <http://localhost:8765>。端口可以通过
`ROBO_WEBUI_PORT=9000` 修改。

当前范围：

- 扫描 `resources/robots/` 中的 URDF/XML；
- 真实解析常见 URDF 与 MJCF XML 的 link、joint、axis 和 limit；
- 提取 visual/collision geometry 与 mesh 引用，供中央视图和后续真实渲染使用；
- 显示模型检查、结构树、关节映射、控制参数、训练与运行工作区；
- 检查缺失的 inertial、collision、joint limit 和反向限位；
- 编辑默认站立角、软限位、KP/KD、action scale、峰值扭矩和高效转速；
- 从 Method registry 读取算法插件；
- 自动保存项目 JSON 到 `webui/projects/`；
- 将上传的 URDF/XML 或包含 meshes 的 ZIP 保存到隔离的 `webui/uploads/`（拒绝 Zip Slip 路径）；
- 生成不覆盖源模型的 `derived/<robot>/robot-profile.json` 机器人包；
- 通过现有 train workflow 启动本地训练并保留日志。
- 训练前执行 backend、method、关节映射和资源兼容性检查；
- TensorBoard 可由 WebUI 启动并在 `6006` 查看；Viser 启动会调用现有 play/visualize 链路；

当前中央机器人仍是无外部前端依赖的预览；模型 geometry 数据已经由 API 提供，下一阶段可接入
本地构建的 Three.js + `urdf-loader` 视图已经接入：

```bash
cd webui
npm install
npm run build
```

构建产物写入 `webui/dist/three-viewer.js`，由本地 Python server 提供，不需要 CDN。

坐标约定与 `robot_viewer` 一致：URDF/MJCF 模型挂在唯一的 `world` 根节点下，默认
将机器人 `+Z up` 转换到 Three.js 的 `+Y up`；地面和相机保持在 Three.js 世界坐标，
避免分别旋转机器人和网格产生双重变换。界面可以切换 `±X/±Y/±Z` up 检查特殊模型。
