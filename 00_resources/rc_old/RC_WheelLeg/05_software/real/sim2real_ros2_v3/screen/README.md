# Orin 触控屏控制面板

`fullscreen_quit.py` 是比赛 Orin 外接 `800×600` 屏幕使用的控制面板，通过本机 `http://127.0.0.1:18080/api/*` 调用 ROS 2 Web bridge，不建立第二套控制协议。

```bash
cd <sim2real_ros2_v3工作区>
DISPLAY=:0 python3 screen/fullscreen_quit.py
```

程序默认从脚本父目录自动确定工作区，也可设置 `SIM2REAL_REPO_DIR` 覆盖。显示权限检查：

```bash
python3 screen/check_display.py
```

面板默认定位档位是 `relocal`，但仓库没有比赛使用的 `1hao.bin`。未补回地图时请先使用 odom 档位：

```bash
SIM2REAL_LOCALIZATION_PROFILE=odom DISPLAY=:0 python3 screen/fullscreen_quit.py
```

面板会按所选档位构造 `localization_mode` 和 Odin 配置参数；不要把“界面能启动”理解为重定位资产已经完整。

自启动脚本：

- `install_autostart.sh`：图形桌面登录后启动。
- `install_boot_service.sh <用户名>`：安装 systemd 服务。
- `uninstall_boot_service.sh`：卸载服务。

使用屏幕启动系统前，先完成工作区构建、Odin 配置、CAN 映射检查和急停验证。
