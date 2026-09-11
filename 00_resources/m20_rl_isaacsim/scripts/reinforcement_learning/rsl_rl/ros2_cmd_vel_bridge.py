"""ros2_cmd_vel_bridge.py
A lightweight rclpy subscriber that runs in a daemon thread and exposes the
latest /cmd_vel as a plain Python tuple (vx, vy, wz).

Usage in the play script:
    from ros2_cmd_vel_bridge import CmdVelBridge
    bridge = CmdVelBridge(topic="/cmd_vel")
    bridge.start()
    ...
    vx, vy, wz = bridge.get()   # non-blocking, always returns latest
"""

from __future__ import annotations

import threading
import time
from typing import Tuple


class CmdVelBridge:
    """Thread-safe /cmd_vel subscriber bridge."""

    def __init__(
        self,
        topic: str = "/cmd_vel",
        max_lin_x: float = 3.0,
        max_lin_y: float = 3.0,
        max_ang_z: float = 1.5,
        timeout_s: float = 1.2,
    ) -> None:
        self.topic = topic
        self.max_lin_x = max_lin_x
        self.max_lin_y = max_lin_y
        self.max_ang_z = max_ang_z
        self.timeout_s = timeout_s

        self._vx: float = 0.0
        self._vy: float = 0.0
        self._wz: float = 0.0
        self._last_msg_time: float = 0.0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._node = None

    def start(self) -> None:
        """Spin rclpy in a background daemon thread."""
        self._thread = threading.Thread(
            target=self._spin, daemon=True, name="CmdVelBridge"
        )
        self._thread.start()

    def get(self) -> Tuple[float, float, float]:
        """Return (vx, vy, wz) – thread-safe, non-blocking with timeout."""
        with self._lock:
            # ★ 4. 获取时检查是否超时。如果距离上一次收到消息超过了设定时间，则返回全零
            if time.time() - self._last_msg_time > self.timeout_s:
                return 0.0, 0.0, 0.0
            return self._vx, self._vy, self._wz

    def stop(self) -> None:
        if self._node is not None:
            try:
                self._node.destroy_node()
            except Exception:
                pass

    def _spin(self) -> None:
        try:
            import rclpy
            from geometry_msgs.msg import Twist
        except ImportError as e:
            print(f"[CmdVelBridge] rclpy not available – cmd_vel will be zero: {e}")
            return

        rclpy.init(args=None)
        self._node = rclpy.create_node("m20_cmd_vel_bridge")

        def _cb(msg: Twist) -> None:
            vx = float(msg.linear.x)
            vy = float(msg.linear.y)
            wz = float(msg.angular.z)
            vx = max(-self.max_lin_x, min(self.max_lin_x, vx))
            vy = max(-self.max_lin_y, min(self.max_lin_y, vy))
            wz = max(-self.max_ang_z, min(self.max_ang_z, wz))
            with self._lock:
                self._vx, self._vy, self._wz = vx, vy, wz
                self._last_msg_time = time.time()  # ★ 5. 每次收到新消息，刷新时间戳

        self._node.create_subscription(Twist, self.topic, _cb, 10)
        print(f"[CmdVelBridge] Subscribed to {self.topic} (timeout: {self.timeout_s}s)")
        rclpy.spin(self._node)