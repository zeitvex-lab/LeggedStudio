# unitree-go2-slam-nav2 — 参考资源

> **来源**：`00_open/unitree-go2-slam-nav2/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：Go2 的 SLAM + Nav2 导航栈（ROS2）
> **收录**：53 个文件 / 144 KB（其中推理策略/模型文件 0 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **RL 训练工程**（7 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **评测与测试**（12 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（34 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （3 个文件）
frontier/  （16 个文件）
    (直接文件)/
    config/
    frontier/
    launch/
    resource/
    test/
go2_cmd_processor/  （9 个文件）
    (直接文件)/
    go2_cmd_processor/
    resource/
    test/
go2_slam_nav/  （16 个文件）
    (直接文件)/
    config/
    go2_slam_nav/
    launch/
    resource/
    test/
image_processing/  （9 个文件）
    (直接文件)/
    image_processing/
    resource/
    test/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 30 |
| `(无扩展名)` | 7 |
| `.xml` | 7 |
| `.cfg` | 4 |
| `.rviz` | 2 |
| `.repo` | 1 |
| `.md` | 1 |
| `.yaml` | 1 |

## 文件索引（项目内相对路径）

```text
.DS_Store
README.md
dependencies.repo
frontier/.DS_Store
frontier/config/frontier_only.rviz
frontier/frontier/__init__.py
frontier/frontier/frontier.py
frontier/frontier/frontier_update1.py
frontier/frontier/frontier_update2.py
frontier/launch/frontier.launch.xml
frontier/launch/frontier_update.launch.xml
frontier/launch/frontier_update2.launch.xml
frontier/package.xml
frontier/resource/frontier
frontier/setup.cfg
frontier/setup.py
frontier/test/test_copyright.py
frontier/test/test_flake8.py
frontier/test/test_pep257.py
go2_cmd_processor/go2_cmd_processor/__init__.py
go2_cmd_processor/go2_cmd_processor/sport_ctrl.py
go2_cmd_processor/package.xml
go2_cmd_processor/resource/go2_cmd_processor
go2_cmd_processor/setup.cfg
go2_cmd_processor/setup.py
go2_cmd_processor/test/test_copyright.py
go2_cmd_processor/test/test_flake8.py
go2_cmd_processor/test/test_pep257.py
go2_slam_nav/.DS_Store
go2_slam_nav/config/nav.rviz
go2_slam_nav/config/nav2_params.yaml
go2_slam_nav/go2_slam_nav/__init__.py
go2_slam_nav/launch/mapping.launch.py
go2_slam_nav/launch/mapping_camera.launch.py
go2_slam_nav/launch/nav.launch.py
go2_slam_nav/launch/rtab_camera_lidar.launch.py
go2_slam_nav/launch/rtab_lidar.launch.py
go2_slam_nav/package.xml
go2_slam_nav/resource/go2_slam_nav
go2_slam_nav/setup.cfg
go2_slam_nav/setup.py
go2_slam_nav/test/test_copyright.py
go2_slam_nav/test/test_flake8.py
go2_slam_nav/test/test_pep257.py
image_processing/image_processing/__init__.py
image_processing/image_processing/image_subscriber.py
image_processing/package.xml
image_processing/resource/image_processing
image_processing/setup.cfg
image_processing/setup.py
image_processing/test/test_copyright.py
image_processing/test/test_flake8.py
image_processing/test/test_pep257.py
```
