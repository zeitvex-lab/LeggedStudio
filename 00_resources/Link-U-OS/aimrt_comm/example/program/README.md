# AimRTe Program Example

本目录展示了 **program 模式**下的两种写法：

- **app_mode**：模块直接在业务程序的 `main()` 中注册、随程序一起编译链接；
- **pkg_mode**：模块编译成动态库，由 `aimrte` 主程序按配置动态载入。

## 运行方式（按 install 目录的布局）

本仓库约定示例的运行目录为 `bin/`，配置文件统一放在 `../config/` 下（本示例已从 `cfg/` 调整为 `config`，并放到仓库的 `aimrt_comm/config/` 里统一管理）。

### app_mode

进入 `example/program/app_mode_install/linux/bin/`，执行：

```sh
./run_app_mode.sh
```

它等价于：

```sh
./example-program-app_mode --cfg_file_path=../config/example/program/app_mode_config.yaml --process_name=app_demo
```

### pkg_mode

进入 `example/program/pkg_mode_install/linux/bin/`，执行：

```sh
./run_pkg_mode.sh
```

它等价于：

```sh
./aimrte --cfg_file_path=../config/example/program/pkg_mode_config.yaml --process_name=pkg_demo
```

## 运行方式（按 scripts 的统一入口）

与 `scripts/example/ping` 一样，本示例也提供了统一脚本入口（部署到 build 目录后使用）：

- `scripts/example/program/run_app_mode.sh`
- `scripts/example/program/run_pkg_mode.sh`
