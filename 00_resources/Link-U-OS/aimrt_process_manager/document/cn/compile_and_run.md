## 编译

在本地安装专用的docker环境, 并完成代码的clone. 编译过程使用 bazel 工具链进行编译，具体请参考`integration`.

```sh
cd aimrt_process_manager

# 编译x86版本
bazel build  //:process_manager_tar

# 编译orin版本
bazel build  //:process_manager_tar --config=orin_aarch64

```
编译的产物位于 `bazel-bin` 目录中，名称为：`process_manager_tar.tar`


## 运行

当前模块会分别运行于orin, x86内.

当前模块的配置文件，依赖`integration`仓中的配置，具体路径
- orin: `integration/product/a2_ultra/addons/orin/entry/bin/cfg/run_agibot.yaml`
- x86: `integration/product/a2_ultra/addons/x86/entry/bin/cfg/run_agibot.yaml`

最终部署完成后，配置文件路径位于：
`/agibot/software/v0/entry/bin/cfg/run_agibot.yaml`, 如果需要测试和验证时，请修改和参考该文件.

当前模块的启动脚本，会被`integration`仓中作为守护的python脚本所调用，具体路径：
- orin: `integration/product/a2_ultra/addons/orin/entry/bin/master_em_server.py`
- x86: `integration/product/a2_ultra/addons/x86_64/entry/bin/slave_em_server.py`

两个python 守护脚本以主从的方式进行管理，在时间同步完成后，启动，保证启动时间一致.

如果仅在本地测试:
```sh
cd bazel-bin
tar xvf process_manager_tar.tar
bash ./scripts/process_manager/start_process_manager.sh
```
如果在本地测试，可能需要在本地环境模拟大包运行所需要的目录和必要的文件信息，请自行根据提示构建
