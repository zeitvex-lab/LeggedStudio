import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.substitutions import (
    LaunchConfiguration,
    PathJoinSubstitution,
    PythonExpression,
)
from ament_index_python.packages import get_package_share_directory

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():

    # Initialize Arguments
    parameters_file = PathJoinSubstitution(
        [
            FindPackageShare("rl_controllers"),
            "config",
            "joy.yaml",
        ]
    )

    # Read URDF from package
    robot_descriptions_pkg_dir = get_package_share_directory('robot_descriptions_public')
    urdf_file_path = os.path.join(robot_descriptions_pkg_dir, 'urdf', 'model_with_finger.urdf')
    with open(urdf_file_path, 'r') as infile:
        robot_description_content = infile.read()
    robot_description = {"robot_description": robot_description_content}

    controllers_config = PathJoinSubstitution(
        [
            FindPackageShare("rl_controllers"),
            "config",
            PythonExpression([
                '"', LaunchConfiguration("controllers_config"), '".endswith(".yaml") and "',
                LaunchConfiguration("controllers_config"), '" or "',
                LaunchConfiguration("controllers_config"), '" + ".yaml"',
            ]),
        ]
    )

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[robot_description, controllers_config, {"aimrt_cfg_path": LaunchConfiguration('aimrt_cfg_path')}],
        output="both",
    )

    robot_state_pub_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="both",
        parameters=[robot_description]
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster", "--controller-manager", "controller_manager"],
    )

    robot_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["rl_controllers", "--controller-manager", "controller_manager"],
    )

    # Delay start of robot_controller after `joint_state_broadcaster`
    delay_robot_controller_spawner_after_joint_state_broadcaster_spawner = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[robot_controller_spawner],
        )
    )

    joy_node = Node(
        package='joy',
        executable='joy_node',
        name='joy_node',
        parameters=[{'autorepeat_rate': 20.0}],
    )

    teleop_node = Node(
        package='joy_teleop',
        executable='joy_teleop',
        parameters=[parameters_file]
    )

    nodes = [
        DeclareLaunchArgument('teleop_config', default_value=parameters_file),
        DeclareLaunchArgument('controllers_config', default_value='baseline'),
        DeclareLaunchArgument('aimrt_cfg_path', default_value=os.environ.get('AIMRT_CFG_PATH')),
        control_node,
        robot_state_pub_node,
        joint_state_broadcaster_spawner,
        delay_robot_controller_spawner_after_joint_state_broadcaster_spawner,
        joy_node,
        teleop_node,
    ]

    return LaunchDescription(nodes)
