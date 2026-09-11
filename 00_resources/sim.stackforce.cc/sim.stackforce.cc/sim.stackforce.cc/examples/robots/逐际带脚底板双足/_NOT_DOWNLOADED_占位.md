# 占位文件（未下载）

按要求，本机器人的 URDF/网格（mesh）文件未下载，仅保留目录占位。

- 机器人：逐际带脚底板双足
- 服务端 URL 模式：`https://sim.stackforce.cc/examples/robots/%E9%80%90%E9%99%85%E5%B8%A6%E8%84%9A%E5%BA%95%E6%9D%BF%E5%8F%8C%E8%B6%B3/ (urdf/robot.urdf)`
- 下载方式：访问上述 URL 获取 URDF/USD，再解析其中的 `<mesh filename="...">` 引用逐个下载网格。

如需补全，可参考已下载机器人的目录结构（如 go1_description/）。
