# 支持ROS2原生命令

## 背景
1. 提高开发效率
直接通过ROS2命令操作自定义消息，可以快速测试消息格式、订阅发布主题，更便于开发调试和验证。

2. 增强系统可维护性
原生命令支持自定义消息后，开发者不需依赖外部或自定义工具链，保持与ROS2工具链的一致性，降低运维复杂度。

3. 提升生态兼容性
保持ros2命令原生兼容自定义消息，有助于与ROS2生态的其他组件无缝集成，如rviz、rosbag等，提高系统整体协同能力。

## 方案设计

### 具体流程

![ros2 cli support](images/ros2_cli_support.png)

### 方案优势
* 工具链兼容性：复用ROS2原生cmake和colcon构建工具，保证消息生成流程标准完整。
* 简化bazel任务：bazel构建仅负责集成和链接，自定义消息编译工作交给更适合的工具链，提升构建效率和可靠性。
* 支持ros2命令：包内完成所有消息接口的生成，确保ros2原生命令识别自定义消息。

## 具体实现
### 协议仓定义ROS2消息
以record_playback_msgs为例
#### 目录结构
```bash
ros2
├── CMakeLists.txt
├── record_playback
│   ├── BUILD
│   ├── CMakeLists.txt
│   ├── package.xml
│   ├── msg
│   │   ├── BUILD
│   │   ├── BagInfo.msg
│   │   └── ...
│   └── srv
│       ├── BUILD
│       ├── GetBagList.srv
│       └── ...

```

#### ros2/CMakeLists.txt
将ros2目录下的所有子包添加为子目录，来统一管理它们的CMake构建
```CMake
set_namespace()

set(ROS2_SUBPACKAGES
    record_playback
    ...
)

foreach(SUBPACKAGE ${ROS2_SUBPACKAGES})
    if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/${SUBPACKAGE}/CMakeLists.txt)
        add_subdirectory(${SUBPACKAGE})
    endif()
endforeach()

```

#### ros2/record_playback/CMakeLists.txt
该CMakeLists文件用于为record_playback ROS2包，根据其目录下的.msg和.srv文件定义，生成相应的消息和服务接口代码
```CMake
# Copyright (c) 2025, AgiBot Inc.
# All rights reserved.

cmake_minimum_required(VERSION 3.24)

cmake_policy(SET CMP0148 OLD)

# Get the current folder name
string(REGEX REPLACE ".*/(.*)" "\\1" CUR_DIR ${CMAKE_CURRENT_SOURCE_DIR})

# Get namespace
get_namespace(CUR_SUPERIOR_NAMESPACE)
string(REPLACE "::" "_" CUR_SUPERIOR_NAMESPACE_UNDERLINE ${CUR_SUPERIOR_NAMESPACE})

# Set target name
set(CUR_PACKAGE_NAME ${CUR_DIR}_msgs)
set(CUR_TARGET_NAME ${CUR_SUPERIOR_NAMESPACE_UNDERLINE}_${CUR_DIR})
set(CUR_TARGET_ALIAS_NAME ${CUR_SUPERIOR_NAMESPACE}::${CUR_DIR})

project(${CUR_PACKAGE_NAME})

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# BUG of ros2
set(CUR_BUILD_SHARED_LIBS ${BUILD_SHARED_LIBS})
set(BUILD_SHARED_LIBS ON)
# cmake-format: off
rosidl_generate_interfaces(${CUR_PACKAGE_NAME}
  "msg/BagInfo.msg"
  ...
  "srv/GetBagList.srv"
  ...
)
# cmake-format: on
set(BUILD_SHARED_LIBS ${CUR_BUILD_SHARED_LIBS})

if(NOT TARGET ${CUR_PACKAGE_NAME}::${CUR_PACKAGE_NAME}__rosidl_typesupport_cpp)
  add_library(${CUR_PACKAGE_NAME}::${CUR_PACKAGE_NAME}__rosidl_typesupport_cpp ALIAS ${CUR_PACKAGE_NAME}__rosidl_typesupport_cpp)
endif()

if(NOT TARGET ${CUR_PACKAGE_NAME}::${CUR_PACKAGE_NAME}__rosidl_typesupport_fastrtps_cpp)
  add_library(${CUR_PACKAGE_NAME}::${CUR_PACKAGE_NAME}__rosidl_typesupport_fastrtps_cpp ALIAS ${CUR_PACKAGE_NAME}__rosidl_typesupport_fastrtps_cpp)
endif()

ament_export_dependencies(rosidl_default_runtime)
ament_export_include_directories(include)

ament_package()

```

#### ros2/package.xml
该package.xml文件是record_playback_msgs ROS2包的清单文件，用于声明其名称、版本、依赖项等元数据。
```XML
<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>record_playback_msgs</name>
  <version>0.1.0</version>
  <description>record_playback_msgs package</description>

  <maintainer email="charles@example.com">charles</maintainer>

  <license>Apache License 2.0</license>

  <buildtool_depend>ament_cmake</buildtool_depend>

  <buildtool_depend>rosidl_default_generators</buildtool_depend>

  <exec_depend>rosidl_default_runtime</exec_depend>

  <member_of_group>rosidl_interface_packages</member_of_group>

  <export>
    <build_type>ament_cmake</build_type>
    <!-- <ros1_bridge mapping_rules="mapping_rules.yaml"/> -->
  </export>
</package>

```

#### ros2/record_playback/BUILD
该BUILD文件用于将 CMakeLists.txt 和 package.xml 这两个文件打包成一个逻辑单元
```Python
package(
    default_visibility = ["//visibility:public"],
)

filegroup(
    name = "ros2_files",
    srcs = [
        "CMakeLists.txt",
        'package.xml'
    ],
)

```

#### ros2/record_playback/msg/BUILD
该BUILD 文件的作用是为 Bazel 声明和管理 ROS2 的消息定义文件
```Python
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "BagInfo.msg",
    ...
])

filegroup(
    name = "ros2_files",
    srcs = glob(
        [
            "**",
        ],
        exclude = ["BUILD"],
    ),
)


```

#### ros2/record_playback/srv/BUILD
```Python
package(
    default_visibility = ["//visibility:public"],
)

exports_files([
    "GetBagList.srv",
    ...
])

filegroup(
    name = "ros2_files",
    srcs = glob(
        [
            "**",
        ],
        exclude = ["BUILD"],
    ),
)


```

#### BUILD
该BUILD 文件的作用为 x86_64 和 aarch64 两种不同的硬件架构，构建出本项目中所有的 ROS 2 消息（message）和服务（service）包
```Python
load("@integration//rules/utils:ros2_package.bzl", "ros2_colcon_package")
load("@integration//rules/utils:pkg_lib.bzl", "pkg_lib")

package(
    default_visibility = ["//visibility:public"],
)
# 打包用于 CMake 构建的 ROS2 消息(msg)和服务(srv)定义文件
pkg_lib(
    name = "ros2_source_files_tar",
    srcs = [
        "CMakeLists.txt",
        "ros2/CMakeLists.txt",
        "aimdk/protocol/CMakeLists.txt",
         ...
         # record_playback相关ros2文件的target
        "//ros2/record_playback:ros2_files",
        "//ros2/record_playback/msg:ros2_files",
        "//ros2/record_playback/srv:ros2_files",
        ...
    ] + glob([
        "cmake/**",
    ]),
)

# 构建x86_64架构的ROS2消息包
ros2_colcon_package(
    name = "ros2_package_x86",
    aarch_type = "x86_64",
    src_tar = ":ros2_source_files_tar",
)

# 构建aarch64架构的ROS2消息包
ros2_colcon_package(
    name = "ros2_package_aarch64",
    aarch_type = "aarch64",
    src_tar = ":ros2_source_files_tar",
)


```

#### 编译产物
通过编译target：ros2_package_x86或ros2_package_aarch64生成的ROS 2 消息包解压后结构如下：
```Bash
├── include
│   └──record_playback_msgs
├── lib
│   ├── librecord_playback_msgs__rosidl_generator_c.so
│   ├── librecord_playback_msgs__rosidl_generator_py.so
│   ├── librecord_playback_msgs__rosidl_typesupport_cpp.so
│   ├── librecord_playback_msgs__rosidl_typesupport_c.so
│   ├── librecord_playback_msgs__rosidl_typesupport_fastrtps_cpp.so
│   ├── librecord_playback_msgs__rosidl_typesupport_fastrtps_c.so
│   ├── librecord_playback_msgs__rosidl_typesupport_introspection_cpp.so
│   └── librecord_playback_msgs__rosidl_typesupport_introspection_c.so
├── ...
└── share
    ├── aimrt_protocol
    ├── ament_index
    ├── colcon-core
    └── record_playback_msgs

```

### 集成仓引入ROS2消息构建产物
#### BUILD
```Python
repackage_tar(
    name = "aimrt_protocol_ros2_package_tar",
    srcs = select({
        "@integration//toolchains/platforms:is_orin_aarch64": ["@aimrt_protocol//:ros2_package_aarch64"],
        "//conditions:default": ["@aimrt_protocol//:ros2_package_x86"],
    }),
    prefix = "share/ros2_package/aimrt_protocol_ros2_package",
)

filegroup(
    name = "ros2_package_tar_list",
    srcs = [
        ":aimrt_protocol_ros2_package_tar",
    ],
)

filegroup(
    name = "x86_64_a2_ultra_tar_list",
    srcs = [
        ":ros2_package_tar_list",
        ...
    ],
)

filegroup(
    name = "orin_a2_ultra_tar_list",
    srcs = [
        ":ros2_package_tar_list",
        ...
    ],
)

```

## 测试验证
1. 登陆机器x86_64或者orin板子
2. 执行下面命令加载ros2的环境变量
```Bash
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY="0"
export ROS_DOMAIN_ID="232"
export FASTRTPS_DEFAULT_PROFILES_FILE="/agibot/software/v0/entry/bin/cfg/privileged_ros_dds_configuration.xml"
export AGIBOT_FEATURE_ROS2_CHANNEL_QOS='history: "keep_last"
        depth: 10
        reliability: "best_effort"'
```
3. 列出所有话题及其对应的消息类型
```Bash
ros2 topic list -t
```
4. 列出某个具体话题的发布和订阅详细信息
```Bash
ros2 topic info /aima/recordbag_upload -v
```

5. 订阅并实时打印某个正在发布的消息内容
```Bash
source /agibot/data/ota/firmware/v0/share/ros2_package/aimrt_protocol_ros2_package/share/record_playback_msgs/local_setup.bash
ros2 topic echo /aima/recordbag_upload
```

## 其他
1. 关于bazel源码编译ros2的msg/srv的BUILD定义方法可参考：[ros2 msg](./ros2_msg.md); [ros2 srv](./ros2_srv.md); 请确保通过cmake生成的ROS2消息的命名空间与bazel编译生成的命名空间保持一致，通常在ros_utils中，interface_name定义为“ros2消息包名_msgs”，其中包名通常为自定义消息所在的父目录名称。