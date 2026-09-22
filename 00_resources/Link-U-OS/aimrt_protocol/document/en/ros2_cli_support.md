# Support for Native ROS2 Commands

## Background
1. Improve Development Efficiency
Directly operating custom messages via ROS2 commands allows for quick testing of message formats, subscription, and publication of topics, which facilitates development, debugging, and verification.

2. Enhance System Maintainability
With native command support for custom messages, developers do not need to rely on external or custom toolchains, maintaining consistency with the ROS2 toolchain and reducing operational complexity.

3. Improve Ecosystem Compatibility
Ensuring native ROS2 command compatibility with custom messages helps seamless integration with other components of the ROS2 ecosystem, such as rviz, rosbag, etc., improving overall system collaboration capabilities.

## Solution Design

### Specific Process

![ros2 cli support](images/ros2_cli_support.png)

### Advantages of the Solution
* Toolchain Compatibility: Reuses native ROS2 CMake and colcon build tools, ensuring a standard and complete message generation process.
* Simplified Bazel Tasks: Bazel build is only responsible for integration and linking, while custom message compilation is handed over to a more suitable toolchain, improving build efficiency and reliability.
* ROS2 Command Support: All message interface generation is completed within the package, ensuring that native ROS2 commands recognize custom messages.

## Specific Implementation
### Protocol Repository Defines ROS2 Messages
Taking `record_playback_msgs` as an example
#### Directory Structure
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
Add all sub-packages under the `ros2` directory as subdirectories to uniformly manage their CMake builds.
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
This CMakeLists file is used to generate corresponding message and service interface code for the `record_playback` ROS2 package based on the `.msg` and `.srv` file definitions in its directory.
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
This `package.xml` file is the manifest file for the `record_playback_msgs` ROS2 package, used to declare its name, version, dependencies, and other metadata.
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
This BUILD file is used to package `CMakeLists.txt` and `package.xml` into a logical unit.
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
This BUILD file\'s purpose is to declare and manage ROS2 message definition files for Bazel.
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
This BUILD file is used to build all ROS 2 message and service packages in this project for two different hardware architectures: x86_64 and aarch64.
```Python
load("@integration//rules/utils:ros2_package.bzl", "ros2_colcon_package")
load("@integration//rules/utils:pkg_lib.bzl", "pkg_lib")

package(
    default_visibility = ["//visibility:public"],
)
# Package ROS2 message (msg) and service (srv) definition files for CMake build
pkg_lib(
    name = "ros2_source_files_tar",
    srcs = [
        "CMakeLists.txt",
        "ros2/CMakeLists.txt",
        "aimdk/protocol/CMakeLists.txt",
         ...
         # record_playback related ros2 files target
        "//ros2/record_playback:ros2_files",
        "//ros2/record_playback/msg:ros2_files",
        "//ros2/record_playback/srv:ros2_files",
        ...
    ] + glob([
        "cmake/**",
    ]),
)

# Build ROS2 package for x86_64 architecture
ros2_colcon_package(
    name = "ros2_package_x86",
    aarch_type = "x86_64",
    src_tar = ":ros2_source_files_tar",
)

# Build ROS2 package for aarch64 architecture
ros2_colcon_package(
    name = "ros2_package_aarch64",
    aarch_type = "aarch64",
    src_tar = ":ros2_source_files_tar",
)


```

#### Compilation Artifacts
The ROS 2 message package generated by compiling target `ros2_package_x86` or `ros2_package_aarch64` has the following structure after decompression:
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

### Integration Repository Introduces ROS2 Message Build Artifacts
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

## Test Verification
1. Log in to the x86_64 machine or Orin board.
2. Execute the following commands to load ROS2 environment variables:
```Bash
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY="0"
export ROS_DOMAIN_ID="232"
export FASTRTPS_DEFAULT_PROFILES_FILE="/agibot/software/v0/entry/bin/cfg/privileged_ros_dds_configuration.xml"
export AGIBOT_FEATURE_ROS2_CHANNEL_QOS='history: "keep_last"
        depth: 10
        reliability: "best_effort"'
```
3. List all topics and their corresponding message types:
```Bash
ros2 topic list -t
```
4. List detailed publication and subscription information for a specific topic:
```Bash
ros2 topic info /aima/recordbag_upload -v
```

5. Subscribe and print the content of a currently publishing message in real-time:
```Bash
source /agibot/data/ota/firmware/v0/share/ros2_package/aimrt_protocol_ros2_package/share/record_playback_msgs/local_setup.bash
ros2 topic echo /aima/recordbag_upload
```

## Other
1. For BUILD definition methods for Bazel source compilation of ROS2 msg/srv, refer to: [ros2 msg](./ros2_msg.md); [ros2 srv](./ros2_srv.md); Please ensure that the namespace of the ROS2 messages generated by CMake is consistent with the namespace generated by Bazel compilation. Typically, in `ros_utils`, `interface_name` is defined as "ros2_package_name_msgs", where the package name is usually the parent directory name of the custom message.
