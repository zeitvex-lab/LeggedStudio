# 占位文件（未下载）

按要求，本机器人的 URDF/网格（mesh）文件未下载，仅保留目录占位。

- 机器人：simplified-quadruped(闭链USD)
- 服务端 URL 模式：`https://sim.stackforce.cc/examples/robots/simplified-quadruped/ (quadruped_in_world.usd, quadruped_simplified_meshes.usd)`
- 下载方式：访问上述 URL 获取 URDF/USD，再解析其中的 `<mesh filename="...">` 引用逐个下载网格。

如需补全，可参考已下载机器人的目录结构（如 go1_description/）。
