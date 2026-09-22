# robot_descriptions_public

## 项目简介
本项目提供了机器人描述文件（URDF）及相关资源，用于在ROS2环境中可视化机器人模型。项目包含两个主要模型：基础模型（model.urdf）和带手指的模型（model_with_finger.urdf）。

## 目录结构
- **urdf/**：存放机器人描述文件，包括基础模型和带手指的模型。
- **mesh/**：存放机器人各部分的网格资源文件（.stl文件）。
- **launch/**：存放启动文件，用于在ROS2中启动机器人模型的可视化。
- **rviz/**：存放RViz配置文件，用于可视化机器人模型。
- **convex/**：存放凸包文件，用于碰撞检测。
- **build.sh**：构建脚本，用于构建本包。
- **display_model.sh**：启动基础模型的脚本。
- **display_model_with_finger.sh**：启动带手指模型的脚本。

## 依赖
- ROS2
- ament_cmake

## 构建方法
使用以下命令构建本包：
```bash
./build.sh
```

## 使用方法
### 启动基础模型
使用以下命令启动基础模型：
```bash
./display_model.sh
```

### 启动带手指模型
使用以下命令启动带手指模型：
```bash
./display_model_with_finger.sh
```

## 维护者
- 作者：Yin Fulong
- 邮箱：yinfulong@zhiyuan-robot.com

## 许可证
本项目采用BSD许可证。 