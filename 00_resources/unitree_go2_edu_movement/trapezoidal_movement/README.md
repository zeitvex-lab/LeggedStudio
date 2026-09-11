# Unitree Go2 EDU Python SDK — Complete Function Reference

**SDK:** unitree_sdk2py v1.0.1  
**Robot:** Unitree Go2 EDU (quadruped, 12 DOF)  
**Python:** >= 3.8  
**Transport:** CycloneDDS (DDS-based pub/sub + RPC)

---

## Table of Contents

1. [Installation & Setup](#1-installation--setup)
2. [Architecture Overview](#2-architecture-overview)
3. [Core: Channel Communication](#3-core-channel-communication)
4. [High-Level: Sport Client (Motion Control)](#4-high-level-sport-client-motion-control)
5. [High-Level: Obstacles Avoid Client](#5-high-level-obstacles-avoid-client)
6. [High-Level: Video Client (Camera)](#6-high-level-video-client-camera)
7. [High-Level: VUI Client (Display/Audio)](#7-high-level-vui-client-displayaudio)
8. [High-Level: Robot State Client](#8-high-level-robot-state-client)
9. [High-Level: Motion Switcher Client](#9-high-level-motion-switcher-client)
10. [Low-Level: Direct Motor Control](#10-low-level-direct-motor-control)
11. [Low-Level: Sensor Data Structures](#11-low-level-sensor-data-structures)
12. [Utilities](#12-utilities)
13. [Motor & Joint Constants](#13-motor--joint-constants)
14. [Complete Working Examples](#14-complete-working-examples)
15. [Error Codes Reference](#15-error-codes-reference)
16. [DDS Topic Names Reference](#16-dds-topic-names-reference)

---

## 1. Installation & Setup

### Install the SDK

```bash
cd /home/unitree/unitree_sdk2_python
pip3 install -e .
# or
pip3 install cyclonedds==0.10.2 numpy opencv-python
pip3 install .
```

### Network Setup

The robot communicates over ethernet. Find the network interface connected to the robot:

```bash
ip addr  # look for interface connected to 192.168.123.x
```

### Initialize DDS (MANDATORY — first thing in every script)

```python
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

# Auto-discover (works on direct connection)
ChannelFactoryInitialize(0)

# Specify network interface explicitly (recommended)
ChannelFactoryInitialize(0, "eth0")   # replace eth0 with your interface name

# With command-line arg (best practice)
import sys
if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)
```

**Parameters:**
- `id: int` — DDS domain ID (always 0 for Go2)
- `networkInterface: str` — e.g., `"eth0"`, `"enp3s0"` (optional)

> **This must be called exactly once before ANY other SDK call. Calling it twice crashes.**

---

## 2. Architecture Overview

```
Your Script
    │
    ├── High-Level API (RPC over DDS)
    │       SportClient         → Motion commands (walk, jump, flip...)
    │       ObstaclesAvoidClient → Obstacle-aware movement
    │       VideoClient         → Front camera frames
    │       VuiClient           → Display brightness, volume
    │       RobotStateClient    → Service management
    │       MotionSwitcherClient → Switch control modes
    │
    └── Low-Level API (Direct DDS pub/sub)
            ChannelPublisher("rt/lowcmd")   → Send motor commands directly
            ChannelSubscriber("rt/lowstate") → Read motor/IMU/sensor state
            ChannelSubscriber("rt/sportmodestate") → Read high-level state
            ChannelSubscriber("rt/wirelesscontroller") → Read gamepad input
```

**Rule:** Never use both High-Level (SportClient) AND Low-Level (lowcmd publisher) simultaneously — they conflict. Use MotionSwitcherClient to switch between modes.

---

## 3. Core: Channel Communication

### 3.1 ChannelFactoryInitialize

```python
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(id: int = 0, networkInterface: str = None)
```

Initializes the DDS transport layer. Must be called first.

---

### 3.2 ChannelPublisher

Publishes messages to a DDS topic (e.g., send motor commands).

```python
from unitree_sdk2py.core.channel import ChannelPublisher
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_

publisher = ChannelPublisher("rt/lowcmd", LowCmd_)
publisher.Init()

# Write a message
success: bool = publisher.Write(msg)          # no timeout
success: bool = publisher.Write(msg, timeout=0.1)  # with timeout in seconds

publisher.Close()  # cleanup
```

**Methods:**
| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `Init()` | `()` | None | Start publisher |
| `Write()` | `(sample, timeout=None)` | `bool` | Publish message |
| `Close()` | `()` | None | Stop publisher |

---

### 3.3 ChannelSubscriber

Subscribes to a DDS topic (e.g., receive sensor state).

```python
from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

# Callback-based (async, called on each message)
def my_handler(msg: LowState_):
    print("IMU:", msg.imu_state.rpy)

subscriber = ChannelSubscriber("rt/lowstate", LowState_)
subscriber.Init(handler=my_handler, queueLen=10)

# Polling-based (blocking read)
subscriber = ChannelSubscriber("rt/lowstate", LowState_)
subscriber.Init()  # no handler
msg = subscriber.Read(timeout=1.0)  # blocks up to 1s, returns None on timeout

subscriber.Close()  # cleanup
```

**Methods:**
| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `Init()` | `(handler=None, queueLen=0)` | None | Start subscriber |
| `Read()` | `(timeout=None)` | message or None | Blocking read |
| `Close()` | `()` | None | Stop subscriber |

**Common Topic Names:**

| Topic | Message Type | Description |
|-------|-------------|-------------|
| `rt/lowstate` | `LowState_` | Motor states, IMU, battery, foot forces |
| `rt/lowcmd` | `LowCmd_` | Low-level motor commands (write only) |
| `rt/sportmodestate` | `SportModeState_` | High-level motion state, position, velocity |
| `rt/wirelesscontroller` | `WirelessController_` | Gamepad joystick input |
| `rt/lidarstate` | `LidarState_` | LIDAR sensor state |
| `rt/utlidar/cloud` | `PointCloud2` | LIDAR point cloud |
| `rt/lf/lowstate` | `LowState_` | Low-frequency (10Hz) low state |
| `rt/audiodata` | `AudioData_` | Audio data stream |
| `rt/uwbstate` | `UwbState_` | UWB positioning data |
| `rt/heightmap` | `HeightMap_` | Terrain height map |

---

## 4. High-Level: Sport Client (Motion Control)

The `SportClient` is the primary API for controlling Go2's movement and behaviors.

### Setup

```python
from unitree_sdk2py.go2.sport.sport_client import SportClient, PathPoint, SPORT_PATH_POINT_SIZE
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(0, "eth0")

client = SportClient()
client.SetTimeout(10.0)  # seconds to wait for robot response
client.Init()            # connects to robot sport service
```

### All SportClient Methods

Every method returns an integer `code`. `code == 0` means success. Non-zero means error.

---

#### Basic Posture Control

```python
# Damp — all motors go to zero torque (limp). Use to safely power down.
code = client.Damp()

# Stand up from lying/sitting position
code = client.StandUp()

# Stand down — controlled lie-down
code = client.StandDown()

# Balance stand — stands in place, maintains balance but doesn't move
code = client.BalanceStand()

# Sit down (sit on haunches)
code = client.Sit()

# Rise from sit
code = client.RiseSit()

# Recovery stand — recovers from fallen position (flipped over etc.)
code = client.RecoveryStand()

# Stop all movement immediately
code = client.StopMove()
```

---

#### Movement Commands

```python
# Move with velocity commands
# vx: forward/backward (m/s), positive = forward
# vy: lateral (m/s), positive = left
# vyaw: rotation (rad/s), positive = turn left
code = client.Move(vx: float, vy: float, vyaw: float)

# Examples:
client.Move(0.3, 0.0, 0.0)   # walk forward at 0.3 m/s
client.Move(-0.3, 0.0, 0.0)  # walk backward
client.Move(0.0, 0.3, 0.0)   # strafe left
client.Move(0.0, 0.0, 0.5)   # rotate left at 0.5 rad/s
client.Move(0.3, 0.0, 0.3)   # forward + turn (combined)
client.Move(0.0, 0.0, 0.0)   # stop (same as StopMove)

# Set speed level (affects Move command scaling)
# level: 0 = slow, 1 = normal, 2 = fast, 3 = very fast
code = client.SpeedLevel(level: int)
```

---

#### Body Orientation Control

```python
# Set body Euler angles (only works in BalanceStand mode)
# roll: side tilt (rad), pitch: forward tilt (rad), yaw: rotation (rad)
code = client.Euler(roll: float, pitch: float, yaw: float)

# Examples:
client.Euler(0.2, 0.0, 0.0)   # lean right
client.Euler(0.0, 0.3, 0.0)   # look up
client.Euler(0.0, 0.0, 0.5)   # rotate body

# Pose mode (enables free body pose control)
code = client.Pose(flag: bool)
client.Pose(True)   # enter pose mode
client.Pose(False)  # exit pose mode
```

---

#### Tricks & Performances

```python
# Basic tricks
code = client.Hello()        # wave front leg
code = client.Stretch()      # stretch body
code = client.Content()      # happy wiggle
code = client.Scrape()       # scraping paw gesture
code = client.Heart()        # heart shape with body

# Flips and jumps (robot must have enough space — ~2m clearance)
code = client.FrontFlip()    # flip forward
code = client.LeftFlip()     # flip left
code = client.BackFlip()     # flip backward
code = client.FrontJump()    # jump forward
code = client.FrontPounce()  # pounce forward

# Dance
code = client.Dance1()  # dance routine 1
code = client.Dance2()  # dance routine 2
```

---

#### Special Locomotion Modes (Toggle)

All these take a `bool` flag: `True` = enable, `False` = disable. Call with `False` to exit the mode.

```python
# Handstand mode
code = client.HandStand(flag: bool)
client.HandStand(True)
import time; time.sleep(4)
client.HandStand(False)

# Walk upright on two hind legs
code = client.WalkUpright(flag: bool)
client.WalkUpright(True)
time.sleep(4)
client.WalkUpright(False)

# Cross-step gait (legs cross over each other)
code = client.CrossStep(flag: bool)

# Free walk (natural movement style)
code = client.FreeWalk()  # no flag, just triggers

# Free bounding (galloping gait)
code = client.FreeBound(flag: bool)

# Free jump mode
code = client.FreeJump(flag: bool)

# Classic walk gait
code = client.ClassicWalk(flag: bool)
```

---

#### Gait Selection

```python
# Switch between gait types
code = client.StaticWalk()    # slow stable walk
code = client.TrotRun()       # trot gait (default)
code = client.EconomicGait()  # energy-efficient gait
```

---

#### Obstacle Avoidance (Built-in)

```python
# Switch obstacle avoidance mode on/off
code = client.SwitchAvoidMode()  # toggles on/off

# Free avoidance (autonomous avoidance while moving)
code = client.FreeAvoid(flag: bool)
client.FreeAvoid(True)
time.sleep(2)
client.FreeAvoid(False)
```

---

#### Auto Recovery

```python
# Set auto recovery (auto stand up if fallen)
code = client.AutoRecoverySet(enabled: bool)
client.AutoRecoverySet(True)   # enable
client.AutoRecoverySet(False)  # disable

# Get current auto recovery state
code, enabled = client.AutoRecoveryGet()
# enabled: bool
print("Auto recovery:", enabled)
```

---

#### Joystick Control

```python
# Switch joystick control on/off
code = client.SwitchJoystick(on: bool)
client.SwitchJoystick(True)   # enable physical joystick
client.SwitchJoystick(False)  # disable (use API only)
```

---

#### API Version Check

```python
# Get local client API version
version_str: str = client.GetApiVersion()

# Get version from robot (checks compatibility)
code, server_version = client.GetServerApiVersion()
print(f"Robot API version: {server_version}")
```

---

#### Subscribing to Robot State (SportModeState)

```python
from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
from unitree_sdk2py.idl.default import unitree_go_msg_dds__SportModeState_

def sport_state_handler(msg: SportModeState_):
    print("Mode:", msg.mode)
    print("Position (x,y,z):", msg.position)
    print("Velocity (vx,vy,vz):", msg.velocity)
    print("Yaw speed:", msg.yaw_speed)
    print("Body height:", msg.body_height)
    print("Gait type:", msg.gait_type)
    print("Foot forces:", msg.foot_force)
    print("Obstacle distances:", msg.range_obstacle)
    print("IMU RPY:", msg.imu_state.rpy)

sub = ChannelSubscriber("rt/sportmodestate", SportModeState_)
sub.Init(sport_state_handler, 10)
```

**SportModeState_ Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `stamp` | TimeSpec_ | Timestamp |
| `error_code` | uint32 | Error code (0 = ok) |
| `imu_state` | IMUState_ | Full IMU data |
| `mode` | uint8 | Current control mode |
| `progress` | float32 | Movement completion 0.0-1.0 |
| `gait_type` | uint8 | Current gait (0=idle, 1=trot, 2=run...) |
| `foot_raise_height` | float32 | Current foot raise height (m) |
| `position` | float32[3] | Global position [x, y, z] (m) |
| `body_height` | float32 | Body height above ground (m) |
| `velocity` | float32[3] | Body velocity [vx, vy, vz] (m/s) |
| `yaw_speed` | float32 | Yaw angular velocity (rad/s) |
| `range_obstacle` | float32[4] | Obstacle distance [front, back, left, right] (m) |
| `foot_force` | int16[4] | Foot contact forces [FR, FL, RR, RL] |
| `foot_position_body` | float32[12] | Foot positions in body frame (3 × 4 feet) |
| `foot_speed_body` | float32[12] | Foot velocities in body frame |

---

#### Complete SportClient Method Table

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `SetTimeout` | `(timeout: float)` | None | Set RPC timeout in seconds |
| `Init` | `()` | None | Connect to robot sport service |
| `GetApiVersion` | `()` | `str` | Local API version string |
| `GetServerApiVersion` | `()` | `(code, str)` | Robot's API version |
| `Damp` | `()` | `code` | Zero torque all motors |
| `BalanceStand` | `()` | `code` | Stand in place |
| `StopMove` | `()` | `code` | Stop moving |
| `StandUp` | `()` | `code` | Stand from down position |
| `StandDown` | `()` | `code` | Lie down |
| `RecoveryStand` | `()` | `code` | Recover from fallen |
| `Euler` | `(roll, pitch, yaw: float)` | `code` | Set body orientation |
| `Move` | `(vx, vy, vyaw: float)` | `code` | Velocity control |
| `Sit` | `()` | `code` | Sit down |
| `RiseSit` | `()` | `code` | Rise from sit |
| `SpeedLevel` | `(level: int)` | `code` | Speed multiplier 0-3 |
| `Hello` | `()` | `code` | Wave gesture |
| `Stretch` | `()` | `code` | Body stretch |
| `Content` | `()` | `code` | Happy wiggle |
| `Dance1` | `()` | `code` | Dance routine 1 |
| `Dance2` | `()` | `code` | Dance routine 2 |
| `SwitchJoystick` | `(on: bool)` | `code` | Toggle joystick control |
| `Pose` | `(flag: bool)` | `code` | Pose mode toggle |
| `Scrape` | `()` | `code` | Scrape paw gesture |
| `FrontFlip` | `()` | `code` | Forward flip |
| `FrontJump` | `()` | `code` | Forward jump |
| `FrontPounce` | `()` | `code` | Forward pounce |
| `Heart` | `()` | `code` | Heart shape gesture |
| `LeftFlip` | `()` | `code` | Left flip |
| `BackFlip` | `()` | `code` | Backward flip |
| `FreeWalk` | `()` | `code` | Free walk mode |
| `FreeBound` | `(flag: bool)` | `code` | Toggle bounding |
| `FreeJump` | `(flag: bool)` | `code` | Toggle jumping mode |
| `FreeAvoid` | `(flag: bool)` | `code` | Toggle obstacle avoidance |
| `WalkUpright` | `(flag: bool)` | `code` | Toggle bipedal walk |
| `CrossStep` | `(flag: bool)` | `code` | Toggle cross-step gait |
| `StaticWalk` | `()` | `code` | Use static walk gait |
| `TrotRun` | `()` | `code` | Use trot gait |
| `EconomicGait` | `()` | `code` | Use economic gait |
| `HandStand` | `(flag: bool)` | `code` | Toggle handstand mode |
| `ClassicWalk` | `(flag: bool)` | `code` | Toggle classic walk |
| `AutoRecoverySet` | `(enabled: bool)` | `code` | Set auto recovery |
| `AutoRecoveryGet` | `()` | `(code, bool)` | Get auto recovery state |
| `SwitchAvoidMode` | `()` | `code` | Toggle avoid mode |

---

## 5. High-Level: Obstacles Avoid Client

Provides collision-aware movement commands. The robot uses onboard sensors to avoid obstacles while executing velocity commands.

### Setup

```python
from unitree_sdk2py.go2.obstacles_avoid.obstacles_avoid_client import ObstaclesAvoidClient
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(0, "eth0")

client = ObstaclesAvoidClient()
client.SetTimeout(3.0)
client.Init()
```

### All Methods

```python
# Enable or disable obstacle avoidance
code = client.SwitchSet(on: bool)
client.SwitchSet(True)   # enable
client.SwitchSet(False)  # disable

# Get current obstacle avoidance state
code, enabled = client.SwitchGet()
# enabled: bool

# Move with obstacle avoidance active
# Same parameters as SportClient.Move
# vx (m/s), vy (m/s), vyaw (rad/s)
code = client.Move(vx: float, vy: float, vyaw: float)
client.Move(0.5, 0.0, 0.0)  # move forward, avoids obstacles
client.Move(0.0, 0.0, 0.0)  # stop

# Must call this before using Move() from API
# Pass True to take over from joystick, False to release
code = client.UseRemoteCommandFromApi(isRemoteCommandsFromApi: bool)
client.UseRemoteCommandFromApi(True)   # API controls the robot
client.UseRemoteCommandFromApi(False)  # return to joystick

# Move to absolute position (x, y, yaw in world frame)
code = client.MoveToAbsolutePosition(x: float, y: float, yaw: float)
client.MoveToAbsolutePosition(1.0, 0.0, 0.0)  # go to (1,0) position

# Move by incremental offset from current position
code = client.MoveToIncrementPosition(dx: float, dy: float, dyaw: float)
client.MoveToIncrementPosition(1.0, 0.0, 0.0)  # move 1m forward from here

# API version check
version = client.GetApiVersion()
code, server_version = client.GetServerApiVersion()
```

### Full Workflow

```python
# Correct usage sequence:
client.SwitchSet(True)                 # enable avoidance system
client.UseRemoteCommandFromApi(True)   # take control from joystick
client.Move(0.5, 0.0, 0.0)            # move forward with avoidance
time.sleep(2.0)
client.Move(0.0, 0.0, 0.0)            # stop
client.UseRemoteCommandFromApi(False)  # release control
```

### Method Table

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `SetTimeout` | `(timeout: float)` | None | RPC timeout in seconds |
| `Init` | `()` | None | Connect to service |
| `SwitchSet` | `(on: bool)` | `code` | Enable/disable avoidance |
| `SwitchGet` | `()` | `(code, bool)` | Query avoidance state |
| `Move` | `(vx, vy, vyaw: float)` | `code` | Move with avoidance |
| `UseRemoteCommandFromApi` | `(flag: bool)` | `code` | Take/release joystick control |
| `MoveToAbsolutePosition` | `(x, y, yaw: float)` | `code` | Navigate to world position |
| `MoveToIncrementPosition` | `(dx, dy, dyaw: float)` | `code` | Move by offset |
| `GetApiVersion` | `()` | `str` | Local version string |
| `GetServerApiVersion` | `()` | `(code, str)` | Robot version string |

---

## 6. High-Level: Video Client (Camera)

Retrieves compressed video frames from the Go2's front fisheye camera.

### Setup

```python
from unitree_sdk2py.go2.video.video_client import VideoClient
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(0, "eth0")

client = VideoClient()
client.SetTimeout(3.0)
client.Init()
```

### Methods

```python
# Get a single compressed image frame
code, data = client.GetImageSample()
# code: int (0 = success)
# data: list of bytes (JPEG-compressed image)
```

### Complete Camera Loop with OpenCV

```python
import cv2
import numpy as np
from unitree_sdk2py.go2.video.video_client import VideoClient
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(0, "eth0")

client = VideoClient()
client.SetTimeout(3.0)
client.Init()

code, data = client.GetImageSample()
while code == 0:
    code, data = client.GetImageSample()

    # Convert bytes to numpy array, then decode JPEG
    image_data = np.frombuffer(bytes(data), dtype=np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)

    cv2.imshow("Go2 Front Camera", image)
    if cv2.waitKey(20) == 27:  # ESC to quit
        break

cv2.destroyAllWindows()
```

### Save a Single Frame

```python
code, data = client.GetImageSample()
if code == 0:
    image_data = np.frombuffer(bytes(data), dtype=np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
    cv2.imwrite("snapshot.jpg", image)
```

### Method Table

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `SetTimeout` | `(timeout: float)` | None | RPC timeout |
| `Init` | `()` | None | Connect to video service |
| `GetImageSample` | `()` | `(code, list)` | Get one JPEG frame as byte list |
| `GetApiVersion` | `()` | `str` | Local version string |
| `GetServerApiVersion` | `()` | `(code, str)` | Robot version string |

---

## 7. High-Level: VUI Client (Display/Audio)

Controls the Go2's display screen brightness and speaker volume.

### Setup

```python
from unitree_sdk2py.go2.vui.vui_client import VuiClient
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(0, "eth0")

client = VuiClient()
client.SetTimeout(3.0)
client.Init()
```

### Methods

```python
# Enable or disable the VUI (display/audio system)
code = client.SetSwitch(enable: int)
client.SetSwitch(1)  # on
client.SetSwitch(0)  # off

# Get VUI on/off state
code, enable = client.GetSwitch()
# enable: int (0 or 1)

# Set speaker volume
# level: 0-100
code = client.SetVolume(level: int)
client.SetVolume(50)  # 50% volume
client.SetVolume(0)   # mute
client.SetVolume(100) # max volume

# Get current volume
code, volume = client.GetVolume()
# volume: int (0-100)

# Set display brightness
# level: 0-100
code = client.SetBrightness(level: int)
client.SetBrightness(80)  # 80% brightness
client.SetBrightness(0)   # screen off

# Get current brightness
code, brightness = client.GetBrightness()
# brightness: int (0-100)
```

### Method Table

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `SetTimeout` | `(timeout: float)` | None | RPC timeout |
| `Init` | `()` | None | Connect to VUI service |
| `SetSwitch` | `(enable: int)` | `code` | Turn VUI on (1) or off (0) |
| `GetSwitch` | `()` | `(code, int)` | Get VUI on/off state |
| `SetVolume` | `(level: int)` | `code` | Set volume 0-100 |
| `GetVolume` | `()` | `(code, int)` | Get current volume |
| `SetBrightness` | `(level: int)` | `code` | Set brightness 0-100 |
| `GetBrightness` | `()` | `(code, int)` | Get current brightness |
| `GetApiVersion` | `()` | `str` | Local version string |
| `GetServerApiVersion` | `()` | `(code, str)` | Robot version string |

---

## 8. High-Level: Robot State Client

Manages robot system services — start/stop services and query their state.

### Setup

```python
from unitree_sdk2py.go2.robot_state.robot_state_client import RobotStateClient
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(0, "eth0")

client = RobotStateClient()
client.SetTimeout(3.0)
client.Init()
```

### Methods

```python
# Switch a named service on or off
code = client.ServiceSwitch(name: str, switch: bool)
client.ServiceSwitch("sport", True)   # start sport service
client.ServiceSwitch("sport", False)  # stop sport service
client.ServiceSwitch("obstacles_avoid", True)

# Set report frequency for a service
# interval: reporting interval in milliseconds
# duration: how long to report at this rate (ms), 0 = forever
code = client.SetReportFreq(interval: int, duration: int)
client.SetReportFreq(10, 0)   # report every 10ms indefinitely
client.SetReportFreq(100, 0)  # report every 100ms

# List all services and their states
code, services = client.ServiceList()
# services: list of ServiceState objects
for svc in services:
    print(f"Service: {svc.name}, Status: {svc.status}, Protected: {svc.protect}")
```

### ServiceState Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Service name (e.g., "sport", "obstacles_avoid") |
| `status` | int | 0=stopped, 1=running |
| `protect` | bool | True if service is system-protected |

### Method Table

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `SetTimeout` | `(timeout: float)` | None | RPC timeout |
| `Init` | `()` | None | Connect to robot_state service |
| `ServiceSwitch` | `(name: str, switch: bool)` | `code` | Start or stop a service |
| `SetReportFreq` | `(interval: int, duration: int)` | `code` | Set DDS publish rate |
| `ServiceList` | `()` | `(code, [ServiceState])` | List all services |

---

## 9. High-Level: Motion Switcher Client

Switches the robot between control modes (normal, AI, advanced). Essential before using low-level motor control.

### Setup

```python
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(0, "eth0")

msc = MotionSwitcherClient()
msc.SetTimeout(5.0)
msc.Init()
```

### Methods

```python
# Check current active mode
code, result = msc.CheckMode()
# result: dict with keys 'name' (str) and 'alias' (str)
# result['name'] == '' means no mode is active (safe for low-level)
print("Current mode:", result['name'])

# Select a mode by name or alias
code, _ = msc.SelectMode(nameOrAlias: str)
msc.SelectMode("normal")    # standard motion control
msc.SelectMode("ai")        # AI/autonomous mode (Go2 specific)
msc.SelectMode("advanced")  # advanced user mode

# Release current mode (go to no-mode state)
code, _ = msc.ReleaseMode()

# Set silent mode (suppress mode-switch sounds/notifications)
code = msc.SetSilent(silent: bool)
msc.SetSilent(True)   # silent
msc.SetSilent(False)  # verbose

# Get silent mode state
code, silent = msc.GetSilent()
# silent: bool
```

### Available Mode Names (Go2 EDU)

| Name | Alias | Description |
|------|-------|-------------|
| `"normal"` | `"normal"` | Default locomotion mode (SportClient works here) |
| `"ai"` | `"ai"` | AI/autonomous behaviors |
| `"advanced"` | `"advanced"` | Advanced control with more parameters |
| `""` (empty) | N/A | No mode = safe for low-level control |

### Before Using Low-Level Control

```python
# REQUIRED before sending LowCmd messages
sport_client = SportClient()
sport_client.SetTimeout(5.0)
sport_client.Init()

msc = MotionSwitcherClient()
msc.SetTimeout(5.0)
msc.Init()

# Release high-level mode so low-level can take over
status, result = msc.CheckMode()
while result['name']:  # while a mode is active
    sport_client.StandDown()   # lie the robot down first
    msc.ReleaseMode()
    status, result = msc.CheckMode()
    time.sleep(1)

print("Ready for low-level control")
```

### Method Table

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `SetTimeout` | `(timeout: float)` | None | RPC timeout |
| `Init` | `()` | None | Connect to motion_switcher service |
| `CheckMode` | `()` | `(code, dict)` | Get active mode name/alias |
| `SelectMode` | `(nameOrAlias: str)` | `(code, None)` | Activate a mode |
| `ReleaseMode` | `()` | `(code, None)` | Deactivate current mode |
| `SetSilent` | `(silent: bool)` | `code` | Set silent flag |
| `GetSilent` | `()` | `(code, bool)` | Get silent state |

---

## 10. Low-Level: Direct Motor Control

Low-level control bypasses all high-level behaviors and directly commands individual motors. **Use with extreme caution — incorrect commands can damage the robot.**

### Prerequisites

1. Must release motion switcher mode first (see section 9)
2. Must calculate CRC for every LowCmd message
3. Must send commands at ~500Hz (every 2ms)

### Setup

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC
from unitree_sdk2py.utils.thread import RecurrentThread

ChannelFactoryInitialize(0, "eth0")
crc = CRC()
```

### LowCmd_ Message Fields

```python
low_cmd = unitree_go_msg_dds__LowCmd_()   # creates initialized default message

# Required header — always set these
low_cmd.head[0] = 0xFE
low_cmd.head[1] = 0xEF
low_cmd.level_flag = 0xFF    # low-level flag
low_cmd.gpio = 0

# Motor commands — 20 motors total, Go2 uses first 12
for i in range(20):
    low_cmd.motor_cmd[i].mode = 0x01    # PMSM motor mode (always 0x01)
    low_cmd.motor_cmd[i].q   = 0.0     # target position (radians)
    low_cmd.motor_cmd[i].dq  = 0.0     # target velocity (rad/s)
    low_cmd.motor_cmd[i].tau = 0.0     # feedforward torque (Nm)
    low_cmd.motor_cmd[i].kp  = 0.0     # position gain
    low_cmd.motor_cmd[i].kd  = 0.0     # damping gain

# ALWAYS calculate CRC before sending
low_cmd.crc = crc.Crc(low_cmd)
```

### MotorCmd_ Fields (per motor)

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `mode` | uint8 | `0x01` | Motor control mode — always 0x01 (PMSM) |
| `q` | float32 | -3 to 3 rad | Target joint angle. Set to `2.146e9` to disable position control |
| `dq` | float32 | -32 to 32 rad/s | Target joint velocity. Set to `16000.0` to disable velocity control |
| `tau` | float32 | -50 to 50 Nm | Feedforward torque |
| `kp` | float32 | 0 to ~100 | Position gain (stiffness). Set to 0 for torque-only mode |
| `kd` | float32 | 0 to ~10 | Velocity gain (damping). Set to 0 for position-only mode |

**PD Control:** `torque = kp * (q_target - q_actual) + kd * (dq_target - dq_actual) + tau`

### Motor Index Mapping (Go2 — 12 DOF)

```python
LegID = {
    "FR_0": 0,   # Front Right Hip  (abduction/adduction)
    "FR_1": 1,   # Front Right Thigh (hip flexion)
    "FR_2": 2,   # Front Right Calf  (knee)
    "FL_0": 3,   # Front Left Hip
    "FL_1": 4,   # Front Left Thigh
    "FL_2": 5,   # Front Left Calf
    "RR_0": 6,   # Rear Right Hip
    "RR_1": 7,   # Rear Right Thigh
    "RR_2": 8,   # Rear Right Calf
    "RL_0": 9,   # Rear Left Hip
    "RL_1": 10,  # Rear Left Thigh
    "RL_2": 11,  # Rear Left Calf
}
PosStopF = 2.146e9   # magic value to disable position control
VelStopF = 16000.0   # magic value to disable velocity control
HIGHLEVEL = 0xEE
LOWLEVEL  = 0xFF
```

### Safe Stand-Down Position (Target joint angles)

```python
# Damped safe position (folded legs)
_targetPos_1 = [0.0, 1.36, -2.65,   # FR hip, thigh, calf
                0.0, 1.36, -2.65,   # FL
               -0.2, 1.36, -2.65,   # RR
                0.2, 1.36, -2.65]   # RL

# Standing position
_targetPos_2 = [0.0, 0.67, -1.3,
                0.0, 0.67, -1.3,
                0.0, 0.67, -1.3,
                0.0, 0.67, -1.3]
```

### Publisher & Subscriber Setup

```python
# Publisher for motor commands
lowcmd_publisher = ChannelPublisher("rt/lowcmd", LowCmd_)
lowcmd_publisher.Init()

# Subscriber for motor/sensor state
low_state = None
def low_state_handler(msg: LowState_):
    global low_state
    low_state = msg

lowstate_subscriber = ChannelSubscriber("rt/lowstate", LowState_)
lowstate_subscriber.Init(handler=low_state_handler, queueLen=10)

# Wait for first state message
while low_state is None:
    time.sleep(0.1)
```

### Initialize LowCmd Safely

```python
def init_low_cmd(low_cmd):
    low_cmd.head[0] = 0xFE
    low_cmd.head[1] = 0xEF
    low_cmd.level_flag = 0xFF
    low_cmd.gpio = 0
    for i in range(20):
        low_cmd.motor_cmd[i].mode = 0x01
        low_cmd.motor_cmd[i].q   = PosStopF    # disable position control
        low_cmd.motor_cmd[i].kp  = 0
        low_cmd.motor_cmd[i].dq  = VelStopF    # disable velocity control
        low_cmd.motor_cmd[i].kd  = 0
        low_cmd.motor_cmd[i].tau = 0
```

### Send Command Loop at 500Hz

```python
from unitree_sdk2py.utils.thread import RecurrentThread

def send_cmd():
    # Update motor commands here
    low_cmd.motor_cmd[0].q   = target_angle
    low_cmd.motor_cmd[0].dq  = 0.0
    low_cmd.motor_cmd[0].kp  = 60.0
    low_cmd.motor_cmd[0].kd  = 5.0
    low_cmd.motor_cmd[0].tau = 0.0

    low_cmd.crc = crc.Crc(low_cmd)   # MUST recalculate every time
    lowcmd_publisher.Write(low_cmd)

# Start a 500Hz timer thread (interval = 0.002s)
cmd_thread = RecurrentThread(interval=0.002, target=send_cmd, name="lowcmd")
cmd_thread.Start()
```

### CRC Utility

```python
from unitree_sdk2py.utils.crc import CRC

crc = CRC()

# Calculate CRC32 for a LowCmd_ or LowState_ message
checksum: int = crc.Crc(msg)
# Always assign before publishing:
low_cmd.crc = crc.Crc(low_cmd)
```

**CRC is hardware-accelerated using native .so libraries (ARM64 and AMD64 supported).**

---

## 11. Low-Level: Sensor Data Structures

### LowState_ Fields (from `rt/lowstate`)

```python
def handler(msg: LowState_):
    # IMU data
    msg.imu_state.quaternion      # float32[4] — [w, x, y, z]
    msg.imu_state.gyroscope       # float32[3] — angular vel [x, y, z] rad/s
    msg.imu_state.accelerometer   # float32[3] — linear accel [x, y, z] m/s²
    msg.imu_state.rpy             # float32[3] — [roll, pitch, yaw] radians
    msg.imu_state.temperature     # uint8 — IMU temperature °C

    # Individual motor states (12 joints)
    for i in range(12):
        msg.motor_state[i].mode        # uint8 — current mode
        msg.motor_state[i].q           # float32 — position (rad)
        msg.motor_state[i].dq          # float32 — velocity (rad/s)
        msg.motor_state[i].ddq         # float32 — acceleration (rad/s²)
        msg.motor_state[i].tau_est     # float32 — estimated torque (Nm)
        msg.motor_state[i].q_raw       # float32 — raw position
        msg.motor_state[i].dq_raw      # float32 — raw velocity
        msg.motor_state[i].ddq_raw     # float32 — raw acceleration
        msg.motor_state[i].temperature # uint8 — motor temperature °C
        msg.motor_state[i].lost        # uint32 — lost packet count

    # Foot contact forces
    msg.foot_force        # int16[4] — raw forces [FR, FL, RR, RL]
    msg.foot_force_est    # int16[4] — estimated forces

    # Battery / Power
    msg.power_v           # float32 — battery voltage (V)
    msg.power_a           # float32 — current draw (A)

    # Battery management system
    msg.bms_state.soc     # uint8 — state of charge 0-100%
    msg.bms_state.current # int32 — current (mA), negative = discharging
    msg.bms_state.cycle   # uint16 — charge cycles
    msg.bms_state.cell_vol  # uint16[15] — individual cell voltages (mV)
    msg.bms_state.status  # uint8 — BMS status flags

    # Temperatures
    msg.temperature_ntc1  # uint8 — temperature sensor 1 (°C)
    msg.temperature_ntc2  # uint8 — temperature sensor 2 (°C)

    # Raw wireless remote data (40 bytes)
    msg.wireless_remote   # uint8[40]

    # Timing
    msg.tick              # uint32 — timestamp counter

    # CRC
    msg.crc               # uint32 — message CRC
```

### IMUState_ Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `quaternion` | float32[4] | — | Orientation [w, x, y, z] |
| `gyroscope` | float32[3] | rad/s | Angular velocity [x, y, z] |
| `accelerometer` | float32[3] | m/s² | Linear acceleration [x, y, z] |
| `rpy` | float32[3] | radians | Euler angles [roll, pitch, yaw] |
| `temperature` | uint8 | °C | IMU chip temperature |

### MotorState_ Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `mode` | uint8 | — | Current motor mode |
| `q` | float32 | rad | Current joint position |
| `dq` | float32 | rad/s | Current joint velocity |
| `ddq` | float32 | rad/s² | Current joint acceleration |
| `tau_est` | float32 | Nm | Estimated joint torque |
| `q_raw` | float32 | rad | Raw encoder position |
| `dq_raw` | float32 | rad/s | Raw encoder velocity |
| `ddq_raw` | float32 | rad/s² | Raw acceleration |
| `temperature` | uint8 | °C | Motor temperature |
| `lost` | uint32 | — | Lost packets counter |

### BmsState_ Fields (Battery)

| Field | Type | Description |
|-------|------|-------------|
| `version_high/low` | uint8 | BMS firmware version |
| `status` | uint8 | Battery status flags |
| `soc` | uint8 | State of charge (0-100%) |
| `current` | int32 | Current in mA (negative = discharging) |
| `cycle` | uint16 | Total charge cycles |
| `bq_ntc` | uint8[2] | BMS chip temperatures (°C) |
| `mcu_ntc` | uint8[2] | MCU temperatures (°C) |
| `cell_vol` | uint16[15] | Individual cell voltages (mV) |

### WirelessController_ (Joystick Input)

```python
from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_

def joystick_handler(msg: WirelessController_):
    msg.lx    # float32 — left stick X [-1, 1]
    msg.ly    # float32 — left stick Y [-1, 1]
    msg.rx    # float32 — right stick X [-1, 1]
    msg.ry    # float32 — right stick Y [-1, 1]
    msg.keys  # uint16 — button bitmask

sub = ChannelSubscriber("rt/wirelesscontroller", WirelessController_)
sub.Init(joystick_handler)
```

### Joystick Utility Class

```python
from unitree_sdk2py.utils.joystick import Joystick

joystick = Joystick()
joystick.extract(msg.wireless_remote)   # parse raw 40-byte remote data

# Button states
joystick.A.pressed        # bool — button held down
joystick.A.on_pressed     # bool — rising edge (just pressed)
joystick.A.on_released    # bool — falling edge (just released)
joystick.A.click_count    # int — consecutive click counter

# All buttons:
# joystick.A, .B, .X, .Y
# joystick.LB, .RB, .LT, .RT
# joystick.back, .start
# joystick.up, .down, .left, .right (D-pad)
# joystick.F1, .F2

# Analog sticks
joystick.lx.data   # float — left X axis
joystick.ly.data   # float — left Y axis
joystick.rx.data   # float — right X axis
joystick.ry.data   # float — right Y axis

# Axis properties
joystick.lx.smooth    # float — smoothed value
joystick.lx.deadzone  # float — deadzone threshold
joystick.lx.threshold # float — pressed threshold

# Generate raw bytes from joystick state (for simulation)
raw_bytes = joystick.combine()  # uint8[40]

# Reset all click counters
joystick.reset_all_click_counts()
```

---

## 12. Utilities

### 12.1 RecurrentThread (Periodic Timer)

Runs a function on a fixed interval using Linux timerfd for precise timing.

```python
from unitree_sdk2py.utils.thread import RecurrentThread

def my_loop():
    print("running at 500Hz")

# Create thread: interval in seconds
thread = RecurrentThread(
    interval=0.002,     # 0.002s = 500Hz
    target=my_loop,     # function to call
    name="my_thread",   # thread name (optional)
    args=(),            # positional args to target (optional)
    kwargs=None         # keyword args to target (optional)
)

thread.Start()          # start the thread

# ... do other work ...

thread.Wait()           # stop thread and wait for it to finish
```

Common intervals:
- `0.002` = 500 Hz (standard for low-level control)
- `0.01`  = 100 Hz
- `0.02`  = 50 Hz
- `1.0`   = 1 Hz

### 12.2 Future (Async Operations)

```python
from unitree_sdk2py.utils.future import Future, FutureState, FutureResult

f = Future()

# In producer thread:
f.Ready(value=42)     # signal success with value
f.Fail("error msg")   # signal failure

# In consumer thread:
result = f.GetResult(timeout=5.0)   # blocks up to 5s
# result.code: 0=success, 1=timeout, 2=failed, 3=unknown
# result.value: the value set by Ready()
# result.message: error message if failed

ok = f.Wait(timeout=5.0)   # blocks, returns True if ready before timeout
```

**FutureResult codes:**
| Code | Constant | Description |
|------|----------|-------------|
| 0 | `FUTURE_SUCC` | Success |
| 1 | `FUTUTE_ERR_TIMEOUT` | Timed out |
| 2 | `FUTURE_ERR_FAILED` | Failed |
| 3 | `FUTURE_ERR_UNKNOWN` | Unknown |

### 12.3 BQueue (Thread-Safe Bounded Queue)

```python
from unitree_sdk2py.utils.bqueue import BQueue

q = BQueue(maxLen=10)   # max 10 items

# Producer
ok = q.Put(item)               # blocks if full
ok = q.Put(item, replace=True) # drops oldest if full, never blocks

# Consumer
item = q.Get()                 # blocks until item available
item = q.Get(timeout=1.0)      # blocks up to 1s, returns None on timeout

q.Clear()       # empty the queue
size = q.Size() # current item count
q.Interrupt(notifyAll=False)  # wake up blocked Get() calls
```

### 12.4 HZSample (Frequency Monitor)

```python
from unitree_sdk2py.utils.hz_sample import HZSample

hz = HZSample(interval=1.0)  # print rate every 1 second
hz.Start()

# In your loop, call Sample() each iteration:
def my_callback(msg):
    hz.Sample()
    # ... process msg ...
```

### 12.5 CRC (Checksum for LowCmd)

```python
from unitree_sdk2py.utils.crc import CRC

crc = CRC()  # singleton — only one instance exists

# Calculate CRC for LowCmd_ or LowState_ or HGLowCmd_/HGLowState_
checksum = crc.Crc(msg)  # returns uint32

# Usage pattern:
low_cmd.crc = crc.Crc(low_cmd)   # set BEFORE publishing
lowcmd_publisher.Write(low_cmd)
```

---

## 13. Motor & Joint Constants

### Go2 Joint Angle Limits (approximate, may vary per unit)

| Joint | Index | Min (rad) | Max (rad) | Description |
|-------|-------|-----------|-----------|-------------|
| FR_0 | 0 | -0.863 | 0.863 | Front Right Hip (abduction) |
| FR_1 | 1 | -0.686 | 4.501 | Front Right Thigh (hip flex) |
| FR_2 | 2 | -2.818 | -0.888 | Front Right Calf (knee) |
| FL_0 | 3 | -0.863 | 0.863 | Front Left Hip |
| FL_1 | 4 | -0.686 | 4.501 | Front Left Thigh |
| FL_2 | 5 | -2.818 | -0.888 | Front Left Calf |
| RR_0 | 6 | -0.863 | 0.863 | Rear Right Hip |
| RR_1 | 7 | -0.686 | 4.501 | Rear Right Thigh |
| RR_2 | 8 | -2.818 | -0.888 | Rear Right Calf |
| RL_0 | 9 | -0.863 | 0.863 | Rear Left Hip |
| RL_1 | 10 | -0.686 | 4.501 | Rear Left Thigh |
| RL_2 | 11 | -2.818 | -0.888 | Rear Left Calf |

### Useful Low-Level Constants

```python
PosStopF = 2.146e9    # Disable position servo (use pure torque/velocity)
VelStopF = 16000.0    # Disable velocity servo

HIGHLEVEL = 0xEE      # level_flag for high-level mode
LOWLEVEL  = 0xFF      # level_flag for low-level mode
TRIGERLEVEL = 0xF0    # level_flag for trigger mode

# Common Kp/Kd values used in examples
Kp_stand = 60.0   # position gain for standing
Kd_stand = 5.0    # damping gain for standing

Kp_soft  = 20.0   # softer position gain
Kd_soft  = 2.0
```

### Common Standing Target Positions

```python
# Folded/crouched position (safe landing from stand-down)
target_fold = [0.0, 1.36, -2.65,    # FR
               0.0, 1.36, -2.65,    # FL
              -0.2, 1.36, -2.65,    # RR
               0.2, 1.36, -2.65]    # RL

# Normal standing position
target_stand = [0.0, 0.67, -1.3,
                0.0, 0.67, -1.3,
                0.0, 0.67, -1.3,
                0.0, 0.67, -1.3]

# Wide-leg stance
target_wide = [-0.35, 1.36, -2.65,
                0.35, 1.36, -2.65,
               -0.50, 1.36, -2.65,
                0.50, 1.36, -2.65]
```

---

## 14. Complete Working Examples

### Example 1: Walk Forward, Then Stop

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

client = SportClient()
client.SetTimeout(10.0)
client.Init()

# Stand up
client.StandUp()
time.sleep(2)

# Walk forward for 3 seconds
client.Move(0.3, 0.0, 0.0)
time.sleep(3)

# Stop
client.StopMove()
time.sleep(1)

# Stand down safely
client.StandDown()
```

---

### Example 2: Read IMU and Print Orientation

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

def state_handler(msg: LowState_):
    rpy = msg.imu_state.rpy
    print(f"Roll: {rpy[0]:.3f}  Pitch: {rpy[1]:.3f}  Yaw: {rpy[2]:.3f}")
    print(f"Battery: {msg.power_v:.1f}V  {msg.bms_state.soc}%")
    print(f"FR_0 position: {msg.motor_state[0].q:.3f} rad")

sub = ChannelSubscriber("rt/lowstate", LowState_)
sub.Init(state_handler, 10)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    sub.Close()
```

---

### Example 3: Read Robot Position and Velocity (High-Level State)

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

def sport_state_handler(msg: SportModeState_):
    pos = msg.position
    vel = msg.velocity
    print(f"Position: x={pos[0]:.2f}m  y={pos[1]:.2f}m  z={pos[2]:.2f}m")
    print(f"Velocity: vx={vel[0]:.2f}  vy={vel[1]:.2f}  vz={vel[2]:.2f} m/s")
    print(f"Body height: {msg.body_height:.3f}m")
    print(f"Obstacle distances (F/B/L/R): {list(msg.range_obstacle)}")

sub = ChannelSubscriber("rt/sportmodestate", SportModeState_)
sub.Init(sport_state_handler, 10)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    sub.Close()
```

---

### Example 4: Camera Feed with OpenCV

```python
import sys
import numpy as np
import cv2
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.video.video_client import VideoClient

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

client = VideoClient()
client.SetTimeout(3.0)
client.Init()

print("Press ESC to quit")
while True:
    code, data = client.GetImageSample()
    if code != 0:
        print(f"Error: {code}")
        break

    image = cv2.imdecode(np.frombuffer(bytes(data), dtype=np.uint8), cv2.IMREAD_COLOR)
    cv2.imshow("Go2 Camera", image)
    if cv2.waitKey(20) == 27:
        break

cv2.destroyAllWindows()
```

---

### Example 5: Obstacle Avoidance Navigation

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.obstacles_avoid.obstacles_avoid_client import ObstaclesAvoidClient

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

client = ObstaclesAvoidClient()
client.SetTimeout(3.0)
client.Init()

# Enable obstacle avoidance
client.SwitchSet(True)
time.sleep(0.5)

# Take control from joystick
client.UseRemoteCommandFromApi(True)
time.sleep(0.3)

try:
    # Move forward with auto obstacle avoidance
    client.Move(0.5, 0.0, 0.0)
    time.sleep(3.0)

    # Turn left
    client.Move(0.0, 0.0, 0.5)
    time.sleep(2.0)

    # Stop
    client.Move(0.0, 0.0, 0.0)

except KeyboardInterrupt:
    client.Move(0.0, 0.0, 0.0)

finally:
    client.UseRemoteCommandFromApi(False)
    print("Done")
```

---

### Example 6: Low-Level Motor Control (Stand Up Sequence)

**WARNING: Test this in a safe environment. The robot will actively move its legs.**

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC
from unitree_sdk2py.utils.thread import RecurrentThread
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
from unitree_sdk2py.go2.sport.sport_client import SportClient

PosStopF = 2.146e9
VelStopF = 16000.0

LegID = {
    "FR_0": 0, "FR_1": 1, "FR_2": 2,
    "FL_0": 3, "FL_1": 4, "FL_2": 5,
    "RR_0": 6, "RR_1": 7, "RR_2": 8,
    "RL_0": 9, "RL_1": 10, "RL_2": 11,
}

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

# Step 1: Release high-level mode
sc = SportClient()
sc.SetTimeout(5.0)
sc.Init()

msc = MotionSwitcherClient()
msc.SetTimeout(5.0)
msc.Init()

status, result = msc.CheckMode()
while result['name']:
    sc.StandDown()
    msc.ReleaseMode()
    status, result = msc.CheckMode()
    time.sleep(1)

print("Low-level mode active")

# Step 2: Setup pub/sub
crc = CRC()
low_cmd = unitree_go_msg_dds__LowCmd_()
low_state = None

def init_cmd():
    low_cmd.head[0] = 0xFE
    low_cmd.head[1] = 0xEF
    low_cmd.level_flag = 0xFF
    low_cmd.gpio = 0
    for i in range(20):
        low_cmd.motor_cmd[i].mode = 0x01
        low_cmd.motor_cmd[i].q   = PosStopF
        low_cmd.motor_cmd[i].kp  = 0
        low_cmd.motor_cmd[i].dq  = VelStopF
        low_cmd.motor_cmd[i].kd  = 0
        low_cmd.motor_cmd[i].tau = 0

init_cmd()

publisher = ChannelPublisher("rt/lowcmd", LowCmd_)
publisher.Init()

def state_cb(msg: LowState_):
    global low_state
    low_state = msg

sub = ChannelSubscriber("rt/lowstate", LowState_)
sub.Init(state_cb, 10)

# Wait for first message
while low_state is None:
    time.sleep(0.1)

# Step 3: Interpolated motion
Kp = 60.0
Kd = 5.0
target = [0.0, 0.67, -1.3] * 4  # standing position
start  = [low_state.motor_state[i].q for i in range(12)]
steps  = 500   # 500 steps × 2ms = 1 second
step   = [0]

def write_cmd():
    t = min(step[0] / steps, 1.0)
    for i in range(12):
        low_cmd.motor_cmd[i].q   = (1 - t) * start[i] + t * target[i]
        low_cmd.motor_cmd[i].dq  = 0.0
        low_cmd.motor_cmd[i].kp  = Kp
        low_cmd.motor_cmd[i].kd  = Kd
        low_cmd.motor_cmd[i].tau = 0.0
    low_cmd.crc = crc.Crc(low_cmd)
    publisher.Write(low_cmd)
    step[0] += 1

thread = RecurrentThread(interval=0.002, target=write_cmd, name="lowcmd")
thread.Start()

# Run for 2 seconds
time.sleep(2)
thread.Wait()
print("Done")
```

---

### Example 7: Check All Services

```python
import sys
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.robot_state.robot_state_client import RobotStateClient

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

client = RobotStateClient()
client.SetTimeout(5.0)
client.Init()

code, services = client.ServiceList()
if code == 0:
    print(f"{'Service':<30} {'Status':<10} {'Protected'}")
    print("-" * 50)
    for svc in services:
        status = "running" if svc.status == 1 else "stopped"
        print(f"{svc.name:<30} {status:<10} {svc.protect}")
else:
    print(f"Error: {code}")
```

---

### Example 8: Joystick Input Reader

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_
from unitree_sdk2py.utils.joystick import Joystick

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

joystick = Joystick()

def ctrl_handler(msg: WirelessController_):
    joystick.extract(msg.wireless_remote)  # NOTE: uses wireless_remote field from LowState, but WirelessController_ is separate topic
    print(f"LX: {joystick.lx.data:+.2f}  LY: {joystick.ly.data:+.2f}  "
          f"RX: {joystick.rx.data:+.2f}  RY: {joystick.ry.data:+.2f}")
    if joystick.A.on_pressed:
        print("A PRESSED")
    if joystick.B.on_pressed:
        print("B PRESSED")

sub = ChannelSubscriber("rt/wirelesscontroller", WirelessController_)
sub.Init(ctrl_handler, 10)

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    sub.Close()
```

---

### Example 9: Battery Monitor

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

def state_cb(msg: LowState_):
    bms = msg.bms_state
    print(f"SOC: {bms.soc}%  Voltage: {msg.power_v:.2f}V  "
          f"Current: {msg.power_a:.2f}A  Cycles: {bms.cycle}")
    min_cell = min(bms.cell_vol[:15]) / 1000.0
    max_cell = max(bms.cell_vol[:15]) / 1000.0
    print(f"Cell voltages — min: {min_cell:.3f}V  max: {max_cell:.3f}V  "
          f"delta: {(max_cell - min_cell)*1000:.0f}mV")

sub = ChannelSubscriber("rt/lowstate", LowState_)
sub.Init(state_cb, 10)

try:
    while True:
        time.sleep(5)
except KeyboardInterrupt:
    sub.Close()
```

---

### Example 10: Perform a Trick Sequence

```python
import time
import sys
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

if len(sys.argv) > 1:
    ChannelFactoryInitialize(0, sys.argv[1])
else:
    ChannelFactoryInitialize(0)

client = SportClient()
client.SetTimeout(10.0)
client.Init()

print("Starting trick sequence...")
input("Press Enter when robot is standing on flat ground with 2m clearance...")

client.StandUp()
time.sleep(2)

client.Hello()        # wave
time.sleep(3)

client.Stretch()      # stretch
time.sleep(3)

client.Dance1()       # dance
time.sleep(5)

client.BalanceStand()
time.sleep(1)

# Flip — only on Go2 EDU with enough space
print("Front flip in 3 seconds...")
time.sleep(3)
code = client.FrontFlip()
print(f"Front flip result: {code}")
time.sleep(5)

client.RecoveryStand()
time.sleep(3)

client.StandDown()
print("Done")
```

---

## 15. Error Codes Reference

### Return Codes from RPC Methods

| Code | Meaning |
|------|---------|
| `0` | Success |
| `3102` | Client send error |
| `3103` | API not registered |
| `3104` | API call timed out |
| `3105` | API version mismatch |
| `3106` | API data error |
| `3107` | Lease invalid |
| `3201` | Server send error |
| `3202` | Server internal error |
| `3203` | API not implemented on robot |
| `3204` | Invalid parameter |
| `3205` | Lease denied |
| `3206` | Lease does not exist |
| `3207` | Lease already exists |

### Checking Return Codes

```python
code = client.StandUp()
if code == 0:
    print("Success")
elif code == 3104:
    print("Timed out — is robot on and connected?")
elif code == 3203:
    print("Robot firmware does not support this command")
else:
    print(f"Error: {code}")

# For methods returning (code, data):
code, data = client.GetVolume()
if code != 0:
    print(f"Failed with code {code}")
else:
    print(f"Volume: {data}")
```

---

## 16. DDS Topic Names Reference

### Subscribe (Read from Robot)

| Topic | Message Type | Frequency | Content |
|-------|-------------|-----------|---------|
| `rt/lowstate` | `LowState_` | 500 Hz | All motor states, IMU, battery, foot forces |
| `rt/lf/lowstate` | `LowState_` | 10 Hz | Same as above but low frequency |
| `rt/sportmodestate` | `SportModeState_` | ~50 Hz | High-level motion state, position, velocity |
| `rt/wirelesscontroller` | `WirelessController_` | ~50 Hz | Gamepad joystick values and buttons |
| `rt/lidarstate` | `LidarState_` | ~10 Hz | LIDAR system status |
| `rt/utlidar/cloud` | `PointCloud2` | ~10 Hz | 3D point cloud from LIDAR |
| `rt/audiodata` | `AudioData_` | varies | Microphone audio stream |
| `rt/uwbstate` | `UwbState_` | ~10 Hz | UWB positioning data |
| `rt/heightmap` | `HeightMap_` | ~1 Hz | Terrain height map around robot |

### Publish (Write to Robot)

| Topic | Message Type | Description |
|-------|-------------|-------------|
| `rt/lowcmd` | `LowCmd_` | Direct motor commands (low-level control) |

### RPC Services (via SportClient, etc.)

| Service Name | Client Class | Description |
|-------------|-------------|-------------|
| `sport` | `SportClient` | All motion commands |
| `obstacles_avoid` | `ObstaclesAvoidClient` | Obstacle avoidance |
| `robot_state` | `RobotStateClient` | Service management |
| `videohub` | `VideoClient` | Camera feed |
| `vui` | `VuiClient` | Display and volume |
| `motion_switcher` | `MotionSwitcherClient` | Mode switching |

---

## Quick Reference Cheatsheet

```python
# ── BOILERPLATE (every script needs this) ──────────────────────────────
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
ChannelFactoryInitialize(0, "eth0")  # use your actual interface

# ── HIGH-LEVEL MOTION ──────────────────────────────────────────────────
from unitree_sdk2py.go2.sport.sport_client import SportClient
c = SportClient(); c.SetTimeout(10.0); c.Init()
c.StandUp()                          # stand from ground
c.Move(0.3, 0.0, 0.0)               # forward at 0.3 m/s
c.Move(0.0, 0.3, 0.0)               # strafe left
c.Move(0.0, 0.0, 0.5)               # rotate left
c.StopMove()                         # stop
c.BalanceStand()                     # stand still and balance
c.RecoveryStand()                    # recover from fall
c.StandDown()                        # lie down
c.Damp()                             # go limp
c.SpeedLevel(2)                      # set speed: 0=slow, 3=max
c.Euler(0.0, 0.3, 0.0)              # tilt body (in BalanceStand)
c.FrontFlip(); c.BackFlip(); c.LeftFlip()
c.Hello(); c.Stretch(); c.Dance1(); c.Dance2()
c.HandStand(True); c.WalkUpright(True); c.FreeBound(True)
c.AutoRecoverySet(True)

# ── OBSTACLES AVOID ────────────────────────────────────────────────────
from unitree_sdk2py.go2.obstacles_avoid.obstacles_avoid_client import ObstaclesAvoidClient
oa = ObstaclesAvoidClient(); oa.SetTimeout(3.0); oa.Init()
oa.SwitchSet(True)
oa.UseRemoteCommandFromApi(True)
oa.Move(0.5, 0.0, 0.0)
oa.UseRemoteCommandFromApi(False)

# ── CAMERA ─────────────────────────────────────────────────────────────
from unitree_sdk2py.go2.video.video_client import VideoClient
import numpy as np, cv2
vc = VideoClient(); vc.SetTimeout(3.0); vc.Init()
code, data = vc.GetImageSample()
img = cv2.imdecode(np.frombuffer(bytes(data), dtype=np.uint8), cv2.IMREAD_COLOR)

# ── VUI ────────────────────────────────────────────────────────────────
from unitree_sdk2py.go2.vui.vui_client import VuiClient
v = VuiClient(); v.SetTimeout(3.0); v.Init()
v.SetVolume(50); v.SetBrightness(80)

# ── MOTION SWITCHER ────────────────────────────────────────────────────
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
ms = MotionSwitcherClient(); ms.SetTimeout(5.0); ms.Init()
ms.SelectMode("normal")      # normal sport mode
ms.ReleaseMode()             # release for low-level control

# ── READ SENSOR STATE ──────────────────────────────────────────────────
from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_, SportModeState_
sub = ChannelSubscriber("rt/lowstate", LowState_)
sub.Init(lambda msg: print(msg.imu_state.rpy), 10)

# ── LOW-LEVEL MOTOR CONTROL ────────────────────────────────────────────
from unitree_sdk2py.core.channel import ChannelPublisher
from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_
from unitree_sdk2py.utils.crc import CRC
from unitree_sdk2py.utils.thread import RecurrentThread
crc = CRC()
pub = ChannelPublisher("rt/lowcmd", LowCmd_); pub.Init()
cmd = unitree_go_msg_dds__LowCmd_()
cmd.head[0]=0xFE; cmd.head[1]=0xEF; cmd.level_flag=0xFF
# set cmd.motor_cmd[i].q / kp / kd / tau for each joint
cmd.crc = crc.Crc(cmd)
pub.Write(cmd)  # call at 500Hz via RecurrentThread(interval=0.002, ...)
```
