# auto_yolo_v2 — Autonomous Ball Approach & Grasp Pipeline

## Platform
- Robot: Unitree Go2 EDU+
- Arm: WidowX-250 (5-DOF, Interbotix, model name `"wx250"`)
- Dog camera: fisheye lens, calibrated at 1920×1080
- Arm camera: standard radial lens, calibrated at 1280×720
- GPU: NVIDIA Jetson Orin (CUDA available)

## How to Run
```bash
source ~/navigation_codes/unitree_go2_edu_movement/mobile_manipulation/.venv/bin/activate
cd ~/navigation_codes/unitree_go2_edu_movement/auto_yolo_v2
python main_state_machine.py                  # red ball (default)
python main_state_machine.py --ball-color green  # green ball
```

## State Machine Flow
```
SEARCH → APPROACH → GRASP → DONE
                 ↘ ARM_SEARCH ↗
```
- **SEARCH**: robot spins in place until dog camera detects ball
- **APPROACH**: dog camera drives robot toward ball at 15 Hz
- **ARM_SEARCH**: fallback when ball lost at 0.4–0.8 m; arm camera re-acquires and re-approaches
- **GRASP**: arm moves to POSITION_2 (observation pose), confirms ball with arm camera, then executes `grasp_flat()`

APPROACH → GRASP directly when:
- `dist_m <= APPROACH_STOP_DIST_M` (distance stop, no centering required), OR
- ball lost at `last_seen_dist <= APPROACH_STOP_DIST_M` (ball dropped out of ROI at close range)

APPROACH → ARM_SEARCH when:
- ball lost for `> ARM_SEARCH_LOSS_TIMEOUT_S` at `0.4 m < dist < 0.8 m`

## Files
| File | Purpose |
|---|---|
| `main_state_machine.py` | Top-level state machine, display thread, all state transitions |
| `vision_core.py` | All image processing: YOLO, undistortion, tiling, HSV filter, distance |
| `base_controller.py` | 15 Hz motor controller, approach P-controller, debounce |
| `arm_controller.py` | WidowX-250 poses, IK, `grasp_flat()`, `scan_wrist()` |
| `dog_detection_worker.py` | Background YOLO thread (`AsyncDogDetector`) |
| `camera_streamer.py` | Dog + arm camera capture threads |

## Key Tuneable Parameters

### vision_core.py
```python
YOLO_IMGSZ   = 960          # inference size; higher = more zoom, slower
YOLO_CONF    = 0.03         # YOLO confidence threshold (dog camera)
GROUND_ROI_TOP_FRAC = 0.40  # ROI starts at 40% from top (bottom 60% searched)
GROUND_CENTER_ZOOM_FRACS = (0.20,)  # center crop at 20% ROI width → ~5× zoom
MIN_BALL_RADIUS_PX = 2.0    # minimum detected ball radius in pixels
BALL_MIN_FRACTION  = 0.10   # fraction of dog-camera bbox that must match color
ARM_MIN_CONF       = 0.03   # YOLO conf for arm camera
ARM_MIN_FRACTION   = 0.06   # color fraction for arm camera

# Red ball HSV (tune with hsv_tuner.py)
_RED_LO1 = [0,  60, 40]   _RED_HI1 = [20, 255, 255]
_RED_LO2 = [155, 60, 40]  _RED_HI2 = [179, 255, 255]

# Green ball HSV
_GREEN_LO1 = [35, 40, 60]  _GREEN_HI1 = [85, 255, 255]
```

### base_controller.py
```python
APPROACH_STOP_DIST_M = 0.45   # stop distance (m)
APPROACH_VX_CONST    = 0.45   # forward speed (m/s)
K_APPROACH_YAW       = 0.8    # yaw P-gain
DX_BIAS              = 0.0    # fix systematic left/right offset; negative = shift left

# Distance-adaptive debounce (coast frames before stopping on detection loss)
# >= 2.0m → 10 frames (667ms)
# 1.0–2.0m → 5 frames (333ms)
# 0.5–1.0m → 2 frames (133ms)
# < 0.5m   → 0 frames (stop immediately)
```

### main_state_machine.py
```python
RESULT_MAX_AGE_S = 0.200       # staleness gate for dog camera results
ARM_STOP_DIST_M  = 0.66        # ARM_SEARCH stop distance (arm-base-frame)
GRASP_CONFIRM_FRAMES = 3       # consecutive arm-camera confirmations needed
GRASP_HOVER_Z_M      = 0.07   # hover height above grasp point
GRASP_Z_CORRECTION_M = 0.0    # tune: positive shifts grasp up, negative down
ARM_SEARCH_TRIGGER_DIST_M = 0.80  # only trigger ARM_SEARCH if lost closer than this
```

### arm_controller.py
```python
POSITION_2_DEG = [-0.0, -20.0, 60.0, -15.0, 0.0]  # arm-camera observation pose
CARRY_PRESET_DEG = [0.0, -90.0, 70.0, 5.0, 0.0]   # travel-safe pose
HOVER_Z_OFFSET_M = 0.06   # 6 cm hover above ball before descending
```

## Architecture Notes

### Dog Camera Detection
- Fisheye undistortion via `cv2.fisheye` remap (cached, adapts to runtime resolution)
- Ground ROI: bottom 60% of frame, 2% side margins
- Two YOLO tiles batched in one call: full ROI + center crop (20% width → ~5× effective zoom)
- Effective zoom is height-limited: `scale = min(imgsz/crop_w, imgsz/crop_h)`
- Radius from HSV mask (`_refine_radius_from_mask`) for accurate distance; falls back to bbox
- Distance formula: `dist_m = (fx * BALL_DIAM_M) / (2 * radius_px)`
- BALL_DIAM_M = 0.043 m (43 mm golf ball)

### Arm Camera Detection
- Standard undistortion (`cv2.getOptimalNewCameraMatrix`)
- Single full-frame YOLO pass (no tiling)
- Stricter than dog camera: ARM_MIN_CONF, ARM_MIN_FRACTION
- Rejects detections where YOLO bbox touches frame edge (clipped ball = bad radius)
- 3D position: `p_cam = [X, Y, Z, 1]` → `arm.ball_cam_to_base(p_cam)` → `[fwd, lat, z]`

### Lag / Latency
- YOLO runs in background thread (`AsyncDogDetector`); main loop calls `get_latest()`
- Staleness gate: results older than 200ms treated as `detected=False`
- X11 display runs in background thread (`_display_thread`) — never blocks main loop
- Two tiles at imgsz=960: ~120ms per batch on Orin GPU

### Detection Debounce
- `ever_detected` flag: robot stays still until ball seen at least once
- `miss_streak`: counts consecutive missed frames
- `_coast_frames(smooth_dist)`: returns coast window based on last known distance
- During coast: robot continues at last known `vx + vyaw`; stops after window expires

### grasp_flat()
- Gripper pitch = π/2 (straight down, body level — no pitch compensation)
- Sequence: home → hover → descend → close gripper → lift → POSITION_2
- IK tries 4 pre-built seed guesses; logs "IK FAILED" if all fail
- If arm workspace issue: reduce `APPROACH_STOP_DIST_M` to get robot closer

## Common Issues & Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Robot moves before seeing ball | Debounce coasting at startup | `ever_detected` flag prevents coast until first detection |
| Distance stuck at same value | False positive (not tracking real ball) | Check BALL_MIN_FRACTION; look for red objects in environment |
| Robot stops/starts intermittently | Detection flickering | Adjust debounce frames in `_coast_frames()` |
| Ball not detected far away | Too small in YOLO input | Increase YOLO_IMGSZ or tighten center crop frac |
| Arm camera shows nothing | POSITION_2_DEG wrong or camera stream None | Check arm pose; verify arm camera device |
| IK FAILED at grasp | Target too far from arm | Reduce APPROACH_STOP_DIST_M (get closer) |
| Grasp offset wrong | GRASP_Z_CORRECTION_M needs tuning | Adjust in main_state_machine.py; check arm-base-frame z from logs |
| Ball always right at stop | Camera mount offset | Tune DX_BIAS (negative = shift reference left) |

## HSV Tuning
Run `hsv_tuner.py` with ball in frame:
```bash
python hsv_tuner.py
```
Adjust sliders until only the ball is white in the mask. Copy H/S/V bounds to `vision_core.py`.
