#!/usr/bin/env python3 
""" 
简化版Nav2启动脚本，只包含最基本的组件 
自动设置初始位姿：从odom坐标系获取当前位置并发布到map坐标系 
""" 

import os 
import time 
from launch import LaunchDescription 
from launch_ros.actions import Node 
from launch.actions import DeclareLaunchArgument, ExecuteProcess 
from launch.substitutions import LaunchConfiguration 
from launch.event_handlers import OnProcessStart 
from launch.actions import RegisterEventHandler 


def generate_launch_description(): 
    # 参数声明 
    map_yaml_arg = DeclareLaunchArgument( 
        'map', 
        default_value=os.path.join( 
            os.path.dirname(__file__), 
            "scripts/reinforcement_learning/rsl_rl/map/full_warehouse.yaml" 
        ), 
        description='地图文件路径' 
    ) 
    
    use_sim_time_arg = DeclareLaunchArgument( 
        'use_sim_time', 
        default_value='true', 
        description='是否使用仿真时间' 
    ) 
    
    rviz_config_arg = DeclareLaunchArgument( 
        'rviz_config', 
        default_value=os.path.join( 
            os.path.dirname(__file__), 
            "scripts/reinforcement_learning/rsl_rl/m20_slam.rviz" 
        ), 
        description='RViz2配置文件路径' 
    ) 
    

    
    # 定义各个节点
    map_server_node = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        parameters=[
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
            {'yaml_filename': LaunchConfiguration('map')}
        ]
    )
    
    amcl_node = Node(
        package='nav2_amcl',
        executable='amcl',
        name='amcl',
        output='screen',
        parameters=[
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
            {'scan_topic': '/m20/scan_2d'},
            {'base_frame_id': 'base_link'},
            {'odom_frame_id': 'odom'},
            {'global_frame_id': 'map'},
            {'tf_broadcast': True}
        ]
    )
    
    # 只添加路径规划器
    planner_server_node = Node(
        package='nav2_planner',
        executable='planner_server',
        name='planner_server',
        output='screen',
        parameters=[
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
            {'planner_plugins': ['GridBased']},
            {'GridBased': {
                'plugin': 'nav2_navfn_planner::NavfnPlanner',
                'tolerance': 0.5,
                'use_astar': False,
                'allow_unknown': True
            }}
        ]
    )
    
    # 更新生命周期管理器，只保留必要的节点
    lifecycle_manager_node = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager',
        output='screen',
        parameters=[
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
            {'autostart': True},
            {'node_names': ['map_server', 'amcl', 'planner_server']}
        ]
    ) 
    
    pointcloud_to_laserscan_node = Node( 
        package='pointcloud_to_laserscan', 
        executable='pointcloud_to_laserscan_node', 
        name='pc2scan_front', 
        parameters=[{ 
            'use_sim_time': LaunchConfiguration('use_sim_time'), 
            'target_frame': 'base_link', 
            'transform_tolerance': 0.1, 
            'min_height': 0.0, 
            'max_height': 1.0, 
            'angle_min': -3.1416, 
            'angle_max': 3.1416, 
            'angle_increment': 0.0087, 
            'scan_time': 0.033, 
            'range_min': 0.1, 
            'range_max': 30.0, 
            'use_inf': True, 
        }], 
        remappings=[ 
            ('cloud_in', '/m20/front_lidar/points'), 
            ('scan',     '/m20/scan_2d'), 
        ], 
    ) 
    
    rviz2_node = Node( 
        package='rviz2', 
        executable='rviz2', 
        name='rviz2', 
        arguments=['-d', LaunchConfiguration('rviz_config')], 
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}], 
        output='screen' 
    ) 
    
    # 自动设置初始位姿的事件处理器
    auto_initial_pose = RegisterEventHandler(
        event_handler=OnProcessStart(
            target_action=amcl_node,  # 在AMCL节点启动后执行
            on_start=[
                ExecuteProcess(
                    cmd=['bash', '-c', 'echo "正在发布初始位姿..."; ros2 topic pub -1 /initialpose geometry_msgs/msg/PoseWithCovarianceStamped "{header: {frame_id: \"map\"}, pose: {pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}}}}"; echo "初始位姿发布完成！"'],
                    shell=True,
                    output='screen'
                )
            ]
        )
    ) 
    
    # 返回所有启动组件
    return LaunchDescription([
        map_yaml_arg,
        use_sim_time_arg,
        rviz_config_arg,
        map_server_node,
        amcl_node,
        planner_server_node,
        lifecycle_manager_node,
        pointcloud_to_laserscan_node,
        rviz2_node,
        auto_initial_pose
    ])