"""
dog_control.py — 电机控制 + 反馈监控

启动:
  ros2 launch dog_control dog_control.py

启动后:
  - real_motor_controller: 200Hz 电机 PD 控制
  - motor_feedback_dump:   浏览器 http://<IP>:8080 查看扭矩+温度曲线
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    motor_controller = Node(
        package="dog_control",
        executable="real_motor_controller",
        name="real_motor_controller",
        output="screen",
    )

    feedback_dump = Node(
        package="dog_policy_test",
        executable="motor_feedback_dump",
        name="motor_feedback_dump",
        output="screen",
    )

    return LaunchDescription([
        motor_controller,
        feedback_dump,
    ])
