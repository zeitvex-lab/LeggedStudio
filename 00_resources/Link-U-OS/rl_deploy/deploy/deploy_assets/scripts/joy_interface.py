#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32
import math
import signal
import sys


class JoyInterface(Node):
    def __init__(self):
        super().__init__("joy_interface")

        # Create joy topic publisher (for debugging and compatibility)
        self.joy_pub = self.create_publisher(Joy, "joy", 10)

        # Create control topic publishers (directly replacing joy_teleop functionality)
        self.cmd_vel_pub = self.create_publisher(Twist, "cmd_vel", 10)
        self.emergency_stop_pub = self.create_publisher(Float32, "emergency_stop", 10)
        self.start_control_pub = self.create_publisher(Float32, "start_control", 10)
        self.switch_mode_pub = self.create_publisher(Float32, "switch_mode", 10)
        self.walk_mode_pub = self.create_publisher(Float32, "walk_mode", 10)
        self.position_control_pub = self.create_publisher(
            Float32, "position_control", 10
        )
        # Initialize joy message
        self.joy_msg = Joy()
        self.joy_msg.header.frame_id = "joy_interface"
        self.joy_msg.axes = [0.0] * 8  # 8 axes
        self.joy_msg.buttons = [0] * 8  # 8 buttons

        # Initialize control messages
        self.cmd_vel_msg = Twist()
        self.emergency_stop_msg = Float32()
        self.start_control_msg = Float32()
        self.switch_mode_msg = Float32()
        self.walk_mode_msg = Float32()
        self.position_control_msg = Float32()

        # Control states
        self.control_active = False
        self.walk_mode_active = False
        self.position_control_active = False
        self.mode_switched = False

        # Joystick auto-centering related
        self.joystick_canvas = None
        self.joystick_handle = None
        self.joystick_center_x = 75  # Joystick center X coordinate
        self.joystick_center_y = 75  # Joystick center Y coordinate
        self.joystick_radius = 60  # Joystick radius
        self.joystick_handle_size = 15  # Joystick handle size

        # Create GUI interface
        self.setup_gui()

        # Timer, publish joy message every 100ms
        self.timer = self.create_timer(0.1, self.publish_joy)

        # Setup signal handler for Ctrl+C
        signal.signal(signal.SIGINT, self.signal_handler)

        self.get_logger().info("Joy interface has started")

    def setup_gui(self):
        """Setup GUI interface"""
        self.root = tk.Tk()
        self.root.title("Joy Control Interface")
        self.root.geometry("900x600")
        self.root.minsize(900, 600)  # Set minimum window size
        self.root.configure(bg="#f0f0f0")

        # Configure root window grid weights for resizing
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Main title
        title_label = tk.Label(
            self.root,
            text="Robot Control Interface",
            font=("Arial", 20, "bold"),
            bg="#f0f0f0",
            fg="#333333",
        )
        title_label.grid(row=0, column=0, pady=20, sticky="ew")

        # Create main frame
        main_frame = tk.Frame(self.root, bg="#f0f0f0")
        main_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)

        # Configure main frame grid weights
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        # Left side: joystick control
        left_frame = tk.Frame(main_frame, bg="#f0f0f0")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        left_frame.grid_rowconfigure(0, weight=1)

        # Left joystick - movement control
        # Parameter description: (parent, title, y_axis, x_axis, color)
        # y_axis=0: left/right turn (angular.z) - joystick Y-axis controls turning
        # x_axis=1: forward/backward (linear.x) - joystick X-axis controls forward/backward
        self.create_joystick(left_frame, "Movement Control Joystick", 0, 1, "#4CAF50")

        # Right side: button control
        right_frame = tk.Frame(main_frame, bg="#f0f0f0")
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=1)

        # Button area
        self.create_buttons(right_frame)

        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Bind keyboard events
        self.root.bind("<KeyPress>", self.on_key_press)
        self.root.bind("<KeyRelease>", self.on_key_release)

        # Set focus to ensure keyboard events can be received
        self.root.focus_set()

    def create_joystick(self, parent, title, x_axis, y_axis, color):
        """Create joystick control"""
        frame = tk.Frame(parent, bg="#f0f0f0")
        frame.grid(row=0, column=0, sticky="nsew", pady=20)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Title
        title_label = tk.Label(
            frame, text=title, font=("Arial", 14, "bold"), bg="#f0f0f0", fg="#333333"
        )
        title_label.pack()

        # Joystick canvas
        canvas_size = 150
        canvas = tk.Canvas(
            frame,
            width=canvas_size,
            height=canvas_size,
            bg="white",
            relief="raised",
            bd=2,
        )
        canvas.pack(pady=10)

        # Joystick center point
        center_x = canvas_size // 2
        center_y = canvas_size // 2
        radius = 60

        # Draw joystick background
        canvas.create_oval(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            fill="#f5f5f5",
            outline="#cccccc",
        )

        # Joystick handle
        handle_size = 15
        self.joystick_handle = canvas.create_oval(
            center_x - handle_size,
            center_y - handle_size,
            center_x + handle_size,
            center_y + handle_size,
            fill=color,
            outline="#333333",
        )

        # Save joystick parameters to instance variables
        self.joystick_canvas = canvas
        self.joystick_center_x = center_x
        self.joystick_center_y = center_y
        self.joystick_radius = radius
        self.joystick_handle_size = handle_size

        # Bind mouse events
        canvas.bind(
            "<Button-1>", lambda e: self.on_joystick_click(e, canvas, x_axis, y_axis)
        )
        canvas.bind(
            "<B1-Motion>", lambda e: self.on_joystick_drag(e, canvas, x_axis, y_axis)
        )
        canvas.bind(
            "<ButtonRelease-1>", lambda e: self.on_joystick_release(x_axis, y_axis)
        )

        # Axis labels
        axis_frame = tk.Frame(frame, bg="#f0f0f0")
        axis_frame.pack(fill="x", padx=10)

        tk.Label(
            axis_frame,
            text=f"Forward/Backward Axis({x_axis}): Forward/Backward Movement",
            bg="#f0f0f0",
            fg="#666666",
            wraplength=200,
            justify="left",
        ).pack(side="left", padx=5, fill="x", expand=True)
        tk.Label(
            axis_frame,
            text=f"Left/Right Turn Axis({y_axis}): Left/Right Turning",
            bg="#f0f0f0",
            fg="#666666",
            wraplength=200,
            justify="left",
        ).pack(side="left", padx=5, fill="x", expand=True)

        # Keyboard control instructions
        keyboard_frame = tk.Frame(frame, bg="#f0f0f0")
        keyboard_frame.pack(pady=5, fill="x", padx=10)
        tk.Label(
            keyboard_frame,
            text="Keyboard Control: ↑↓ Forward/Backward, ←→ Left/Right Turn",
            bg="#f0f0f0",
            fg="#2196F3",
            font=("Arial", 10, "bold"),
            wraplength=300,
        ).pack()

        # Left/Right movement control (axes[3]) - controlled through button combination
        z_control_frame = tk.Frame(frame, bg="#f0f0f0")
        z_control_frame.pack(pady=10)

        tk.Label(
            z_control_frame,
            text="Left/Right Movement Control (axes[3]):",
            bg="#f0f0f0",
            fg="#666666",
        ).pack()

        z_buttons_frame = tk.Frame(z_control_frame, bg="#f0f0f0")
        z_buttons_frame.pack()

        # Left move button
        self.left_move_btn = tk.Button(
            z_buttons_frame,
            text="Left Move",
            command=lambda: self.set_z_axis(-0.5),
            bg="#FF9800",
            fg="white",
            width=8,
        )
        self.left_move_btn.pack(side="left", padx=5)

        # Stop button
        self.stop_move_btn = tk.Button(
            z_buttons_frame,
            text="Stop",
            command=lambda: self.set_z_axis(0.0),
            bg="#9E9E9E",
            fg="white",
            width=8,
        )
        self.stop_move_btn.pack(side="left", padx=5)

        # Right move button
        self.right_move_btn = tk.Button(
            z_buttons_frame,
            text="Right Move",
            command=lambda: self.set_z_axis(0.5),
            bg="#FF9800",
            fg="white",
            width=8,
        )
        self.right_move_btn.pack(side="left", padx=5)

        # Left/Right movement value display
        self.z_axis_label = tk.Label(
            z_control_frame,
            text="0.000",
            bg="#f0f0f0",
            fg="#333333",
            font=("Arial", 10),
        )
        self.z_axis_label.pack()

    def set_z_axis(self, value):
        """Set left/right movement value (axes[3])"""
        self.joy_msg.axes[3] = value
        self.z_axis_label.config(text=f"{value:.3f}")
        self.get_logger().info(f"Left/Right movement set to: {value:.3f}")

        # Update cmd_vel message
        if self.joy_msg.buttons[4] == 1:  # Deadman button
            self.update_cmd_vel()

    def handle_button_function(self, button_id, pressed):
        """Handle button functionality"""
        if button_id == 0:  # Mode switch
            if pressed:
                self.activate_switch_mode()
            else:
                self.deactivate_switch_mode()
        elif button_id == 2:  # Walk mode
            if pressed:
                self.activate_walk_mode()
            else:
                self.deactivate_walk_mode()
        elif button_id == 3:  # Position control mode
            if pressed:
                self.activate_position_control()
            else:
                self.deactivate_position_control()
        elif button_id == 7:  # Start/Stop control
            if pressed:
                self.activate_start_control()
            else:
                self.deactivate_start_control()

    def activate_emergency_stop(self):
        """Activate emergency stop"""
        self.emergency_stop_msg.data = 1.0
        self.emergency_stop_pub.publish(self.emergency_stop_msg)
        self.get_logger().warn("Emergency stop activated!")

    def deactivate_emergency_stop(self):
        """Release emergency stop"""
        self.emergency_stop_msg.data = 0.0
        self.emergency_stop_pub.publish(self.emergency_stop_msg)
        self.get_logger().info("Emergency stop released")

    def activate_switch_mode(self):
        """Activate mode switch"""
        self.switch_mode_msg.data = 1.0
        self.switch_mode_pub.publish(self.switch_mode_msg)
        self.mode_switched = True
        self.get_logger().info("Mode switch activated")

    def deactivate_switch_mode(self):
        """Release mode switch"""
        self.switch_mode_msg.data = 0.0
        self.switch_mode_pub.publish(self.switch_mode_msg)
        self.mode_switched = False
        self.get_logger().info("Mode switch released")

    def activate_walk_mode(self):
        """Activate walk mode"""
        self.walk_mode_msg.data = 1.0
        self.walk_mode_pub.publish(self.walk_mode_msg)
        self.walk_mode_active = True
        self.get_logger().info("Walk mode activated")

    def deactivate_walk_mode(self):
        """Release walk mode"""
        self.walk_mode_msg.data = 0.0
        self.walk_mode_pub.publish(self.walk_mode_msg)
        self.walk_mode_active = False
        self.get_logger().info("Walk mode released")

    def activate_position_control(self):
        """Activate position control mode"""
        self.position_control_msg.data = 1.0
        self.position_control_pub.publish(self.position_control_msg)
        self.position_control_active = True
        self.get_logger().info("Position control mode activated")

    def deactivate_position_control(self):
        """Release position control mode"""
        self.position_control_msg.data = 0.0
        self.position_control_pub.publish(self.position_control_msg)
        self.position_control_active = False
        self.get_logger().info("Position control mode released")

    def activate_start_control(self):
        """Activate start control"""
        self.start_control_msg.data = 1.0
        self.start_control_pub.publish(self.start_control_msg)
        self.control_active = True
        self.get_logger().info("Start control activated")

    def deactivate_start_control(self):
        """Release start control"""
        self.start_control_msg.data = 0.0
        self.start_control_pub.publish(self.start_control_msg)
        self.control_active = False
        self.get_logger().info("Start control released")

    def update_cmd_vel(self):
        """Update and publish cmd_vel message"""
        # According to scaling parameters configured in joy.yaml
        # Axis mapping relationship (Y-axis and Z-axis are swapped):
        # axes[1] -> linear.x (forward/backward) - joystick X-axis movement
        # axes[3] -> linear.y (left/right movement) - button control (original Z-axis function)
        # axes[0] -> angular.z (left/right turn) - joystick Y-axis movement (original Y-axis function)
        self.cmd_vel_msg.linear.x = self.joy_msg.axes[1] * 2.4  # Forward/Backward
        self.cmd_vel_msg.linear.y = (
            self.joy_msg.axes[3] * 1.5
        )  # Left/Right movement (button)
        self.cmd_vel_msg.angular.z = (
            self.joy_msg.axes[0] * 1.0
        )  # Left/Right turn (joystick Y-axis)

        # Publish cmd_vel message
        self.cmd_vel_pub.publish(self.cmd_vel_msg)

    def reset_joystick_position(self):
        """Auto-center joystick to center position"""
        if self.joystick_canvas and self.joystick_handle:
            # Calculate new handle position (center)
            x1 = self.joystick_center_x - self.joystick_handle_size
            y1 = self.joystick_center_y - self.joystick_handle_size
            x2 = self.joystick_center_x + self.joystick_handle_size
            y2 = self.joystick_center_y + self.joystick_handle_size

            # Move handle to center position
            self.joystick_canvas.coords(self.joystick_handle, x1, y1, x2, y2)
            self.get_logger().info("Joystick auto-centered to center position")

    def create_buttons(self, parent):
        """Create button area"""
        button_frame = tk.Frame(parent, bg="#f0f0f0")
        button_frame.grid(row=0, column=0, sticky="nsew", pady=20)
        button_frame.grid_rowconfigure(1, weight=0)  # Don't expand vertically
        button_frame.grid_columnconfigure(0, weight=1)

        # Button title
        button_title = tk.Label(
            button_frame,
            text="Control Buttons",
            font=("Arial", 14, "bold"),
            bg="#f0f0f0",
            fg="#333333",
        )
        button_title.grid(row=0, column=0, pady=(0, 10))

        # Button grid
        buttons_info = [
            ("Mode Switch\n(Lie ↔ Stand)", 0, "#FF9800"),
            ("Emergency Stop\n(Use with another e-stop)", 1, "#D32F2F"),
            ("Enter Walk Mode", 2, "#2196F3"),
            ("Position Control Mode", 3, "#9C27B0"),
            ("Deadman Button\n(Must press to move)", 4, "#F44336"),
            ("Emergency Stop\n(Use with another e-stop)", 5, "#D32F2F"),
            ("Emergency Stop", 6, "#D32F2F"),
            ("Start/Stop Control", 7, "#4CAF50"),
        ]

        button_grid = tk.Frame(button_frame, bg="#f0f0f0")
        button_grid.grid(row=1, column=0, sticky="n", pady=10)  # Align to top, don't expand

        # Configure button grid columns to expand horizontally
        button_grid.grid_columnconfigure(0, weight=1, uniform="button_col")
        button_grid.grid_columnconfigure(1, weight=1, uniform="button_col")
        # Configure row weights for better spacing
        for row_idx in range((len(buttons_info) + 1) // 2):
            button_grid.grid_rowconfigure(row_idx, weight=0, minsize=60)  # Increased minsize for larger buttons

        for i, (text, button_id, color) in enumerate(buttons_info):
            row = i // 2
            col = i % 2

            btn = tk.Button(
                button_grid,
                text=text,
                command=lambda bid=button_id: self.on_button_click(bid),
                bg=color,
                fg="white",
                font=("Arial", 10),  # Increased font size from 9 to 10
                wraplength=160,  # Slightly increased for larger font
                height=3,  # Increased height from 2 to 3
                relief="raised",
                bd=2,
                padx=6,  # Slightly increased internal horizontal padding
                pady=6,  # Slightly increased internal vertical padding
            )
            btn.grid(row=row, column=col, padx=10, pady=6, sticky="ew")  # External padding

            # Special handling for toggle buttons (deadman button and start/stop control)
            if button_id == 4:  # Deadman button
                # Deadman button only responds to click events, not press/release
                btn.bind(
                    "<Button-1>",
                    lambda e, bid=button_id: self.on_deadman_button_click(bid),
                )
            elif button_id in [0, 2, 3, 7]:  # Toggle buttons: mode switch, walk mode, position control, start control
                # Toggle buttons only use click event (handled by command), no press/release
                # Remove default command and use click binding to avoid double triggering
                btn.config(command=None)
                btn.bind(
                    "<Button-1>",
                    lambda e, bid=button_id: self.on_button_click(bid),
                )
            else:
                # Other buttons bind mouse press and release events
                btn.bind(
                    "<ButtonPress-1>",
                    lambda e, bid=button_id: self.on_button_press(bid),
                )
                btn.bind(
                    "<ButtonRelease-1>",
                    lambda e, bid=button_id: self.on_button_release(bid),
                )

    def on_joystick_click(self, event, canvas, x_axis, y_axis):
        """Joystick click event"""
        self.on_joystick_drag(event, canvas, x_axis, y_axis)

    def on_joystick_drag(self, event, canvas, x_axis, y_axis):
        """Joystick drag event"""
        canvas_size = 150
        center_x = canvas_size // 2
        center_y = canvas_size // 2
        radius = 60

        # Calculate mouse position offset relative to center
        dx = event.x - center_x
        dy = event.y - center_y

        # Limit within circular range
        distance = math.sqrt(dx * dx + dy * dy)
        if distance > radius:
            dx = dx * radius / distance
            dy = dy * radius / distance

        # Update joystick handle position
        handle_size = 15
        canvas.coords(
            self.joystick_handle,
            center_x + dx - handle_size,
            center_y + dy - handle_size,
            center_x + dx + handle_size,
            center_y + dy + handle_size,
        )

        # Calculate axis values (-1.0 to 1.0)
        x_value = -dx / radius  # Reverse X-axis, correct forward/backward direction
        y_value = -dy / radius  # Reverse Y-axis, correct left/right turning

        # Update joy message
        self.joy_msg.axes[x_axis] = x_value
        self.joy_msg.axes[y_axis] = y_value

        # Directly publish cmd_vel message (if deadman button is pressed)
        if self.joy_msg.buttons[4] == 1:  # Deadman button
            self.update_cmd_vel()

    def on_joystick_release(self, x_axis, y_axis):
        """Joystick release event"""
        # Reset axis values
        self.joy_msg.axes[x_axis] = 0.0
        self.joy_msg.axes[y_axis] = 0.0

        # Stop movement
        self.update_cmd_vel()

        # Auto-center joystick
        self.reset_joystick_position()

    def on_key_press(self, event):
        """Keyboard press event"""
        key = event.keysym.lower()

        # Check if deadman button is activated
        if self.joy_msg.buttons[4] != 1:
            return

        # Direction key control
        if key == "up":  # ↑ Forward
            self.joy_msg.axes[1] = 1.0
            self.get_logger().info("Keyboard: Forward")
        elif key == "down":  # ↓ Backward
            self.joy_msg.axes[1] = -1.0
            self.get_logger().info("Keyboard: Backward")
        elif key == "left":  # ← Left turn
            self.joy_msg.axes[0] = 1.0
            self.get_logger().info("Keyboard: Left turn")
        elif key == "right":  # → Right turn
            self.joy_msg.axes[0] = -1.0
            self.get_logger().info("Keyboard: Right turn")

        # Update cmd_vel message
        self.update_cmd_vel()

    def on_key_release(self, event):
        """Keyboard release event"""
        key = event.keysym.lower()

        # Stop corresponding direction movement when direction keys are released
        if key in ["up", "down"]:  # Forward/Backward
            self.joy_msg.axes[1] = 0.0
            self.get_logger().info("Keyboard: Stop forward/backward movement")
        elif key in ["left", "right"]:  # Left/Right turn
            self.joy_msg.axes[0] = 0.0
            self.get_logger().info("Keyboard: Stop left/right turning")

        # Update cmd_vel message
        self.update_cmd_vel()

    def on_deadman_button_click(self, button_id):
        """Deadman button click event (toggle mode)"""
        if button_id == 4:  # Deadman button
            current_state = self.joy_msg.buttons[button_id]
            self.joy_msg.buttons[button_id] = 1 if current_state == 0 else 0
            new_state = self.joy_msg.buttons[button_id]

            if new_state == 1:
                self.get_logger().info("Deadman button activated - Robot can now move")
            else:
                self.get_logger().info("Deadman button released - Robot stops moving")
                # Stop movement
                self.stop_robot_movement()

    def stop_robot_movement(self):
        """Stop robot movement"""
        # Reset all movement axes
        self.joy_msg.axes[0] = 0.0  # Y-axis
        self.joy_msg.axes[1] = 0.0  # X-axis
        self.joy_msg.axes[3] = 0.0  # Z-axis

        # Publish stop command
        self.update_cmd_vel()
        self.get_logger().info("Robot movement stopped")

    def on_button_press(self, button_id):
        """Button press event"""
        self.joy_msg.buttons[button_id] = 1
        self.get_logger().info(f"Button {button_id} pressed")

        # Handle special button functionality
        self.handle_button_function(button_id, True)

    def on_button_release(self, button_id):
        """Button release event"""
        self.joy_msg.buttons[button_id] = 0
        self.get_logger().info(f"Button {button_id} released")

        # Handle special button functionality
        self.handle_button_function(button_id, False)

    def on_button_click(self, button_id):
        """Button click event (for toggle buttons)"""
        # Skip deadman button as it has special handling
        if button_id == 4:
            return

        # For certain buttons, maintain state after clicking
        if button_id in [
            0,
            2,
            3,
            7,
        ]:  # Mode switch, walk mode, position control, start control
            current_state = self.joy_msg.buttons[button_id]
            self.joy_msg.buttons[button_id] = 1 if current_state == 0 else 0
            self.get_logger().info(
                f"Button {button_id} state toggled to: {self.joy_msg.buttons[button_id]}"
            )

            # Handle control functionality
            self.handle_button_function(button_id, self.joy_msg.buttons[button_id] == 1)
        # For emergency stop buttons, need to use together
        elif button_id in [1, 5]:  # Emergency stop buttons
            # If both emergency stop buttons are pressed, activate emergency stop
            if button_id == 1:
                self.joy_msg.buttons[1] = 1 if self.joy_msg.buttons[1] == 0 else 0
            elif button_id == 5:
                self.joy_msg.buttons[5] = 1 if self.joy_msg.buttons[5] == 0 else 0

            # Check if both emergency stop buttons are pressed
            if self.joy_msg.buttons[1] == 1 and self.joy_msg.buttons[5] == 1:
                self.get_logger().warn("Emergency stop activated!")
                self.activate_emergency_stop()
            else:
                self.get_logger().info(
                    f"Button {button_id} state toggled to: {self.joy_msg.buttons[button_id]}"
                )
                self.deactivate_emergency_stop()

    def publish_joy(self):
        """Publish joy message"""
        # Verify frame_id is not empty
        if not self.joy_msg.header.frame_id:
            self.joy_msg.header.frame_id = "joy_interface"
            self.get_logger().warn("frame_id is empty, set to default value")

        # Update timestamp
        self.joy_msg.header.stamp = self.get_clock().now().to_msg()

        # Publish message
        self.joy_pub.publish(self.joy_msg)

    def signal_handler(self, signum, frame):
        """Handle SIGINT signal (Ctrl+C)"""
        self.get_logger().info("Received SIGINT signal (Ctrl+C), closing...")
        # Quit mainloop first, then close
        if self.root.winfo_exists():
            self.root.quit()
        self.on_closing()
        sys.exit(0)

    def on_closing(self):
        """Close event handling"""
        self.get_logger().info("Closing Joy interface...")
        if self.root.winfo_exists():
            self.root.quit()
            self.root.destroy()
        rclpy.shutdown()

    def run(self):
        """Run interface"""
        # Use after() to periodically process ROS2 events
        def process_ros2():
            try:
                rclpy.spin_once(self, timeout_sec=0.01)
            except Exception as e:
                self.get_logger().error(f"Error in ROS2 spin: {e}")
            # Schedule next check
            if self.root.winfo_exists():
                self.root.after(10, process_ros2)

        # Start ROS2 processing
        self.root.after(10, process_ros2)

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.get_logger().info("Received KeyboardInterrupt, closing...")
            self.on_closing()
        finally:
            # Ensure cleanup
            if self.root.winfo_exists():
                self.root.quit()
                self.root.destroy()


def main(args=None):
    rclpy.init(args=args)

    joy_interface = JoyInterface()

    try:
        joy_interface.run()
    except Exception as e:
        joy_interface.get_logger().error(f"Error occurred: {e}")
    finally:
        joy_interface.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
