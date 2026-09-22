import os

from launch_ros.substitutions import FindPackageShare
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution, TextSubstitution

from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    urdf_arg = DeclareLaunchArgument(name='urdf', default_value='model.urdf', choices=['model.urdf', 'model_with_finger.urdf'], description='Name of the urdf file')
    rviz_file = PathJoinSubstitution([FindPackageShare('robot_descriptions_public'), 'rviz', 'display.rviz'])
    urdf_file = PathJoinSubstitution([FindPackageShare('robot_descriptions_public'), 'urdf', LaunchConfiguration('urdf')])

    # xacro
    robot_description = ParameterValue(Command(['xacro ', urdf_file]), value_type=str)

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': robot_description}]    
    )

    joint_state_publisher_gui_node = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui'
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_file],
    )

    return LaunchDescription([
        urdf_arg,
        joint_state_publisher_gui_node,
        robot_state_publisher_node,
        rviz_node
    ])
