# 占位文件（未下载）

按要求，本机器人的 URDF/网格（mesh）文件未下载，仅保留目录占位。

- 机器人：菠萝狗
- 服务端 URL 模式：`https://sim.stackforce.cc/examples/robots/%E8%8F%A0%E8%90%9D%E7%8B%97/ (urdf/Pyapple_urdf.urdf)`
- 下载方式：访问上述 URL 获取 URDF/USD，再解析其中的 `<mesh filename="...">` 引用逐个下载网格。

如需补全，可参考已下载机器人的目录结构（如 go1_description/）。
