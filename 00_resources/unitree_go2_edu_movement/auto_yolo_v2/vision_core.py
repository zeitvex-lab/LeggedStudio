#!/usr/bin/env python3
"""
vision_core.py
==============
All image processing for the autonomous approach pipeline.

Two clearly separated detection pipelines
------------------------------------------
process_dog_frame(frame)
    Dog camera (fisheye lens).
    Undistort → ground ROI tiling → batch YOLO → pick best ball →
    TargetCoordinates(dist_m, dx_norm), debug_frame.

process_arm_frame(frame)
    Arm camera (standard radial lens).
    Undistort → single full-frame YOLO → pick best ball →
    TargetCoordinates(dist_m, dx_norm), debug_frame, p_ball_in_cam.
    p_ball_in_cam is a homogeneous (4,) array in camera coordinates;
    pass it to ArmController.ball_cam_to_base() for arm-frame position.
"""

import math
import re
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import logging
import numpy as np
from ultralytics import YOLO

_log = logging.getLogger(__name__)

# ── Dog camera intrinsics (fisheye, 1920×1080 calibration) ───────────────────
DOG_K = np.array([
    [1248.95099, 0.0,        957.862066],
    [0.0,        1247.94633, 530.821641],
    [0.0,        0.0,        1.0       ],
], dtype=np.float64)
DOG_D        = np.array([-0.04634571, -0.21551315, 0.45541731, -0.37792435],
                         dtype=np.float64)
DOG_CALIB_WH = (1920, 1080)

# ── Arm camera intrinsics (standard lens, 1280×720 calibration) ──────────────
ARM_K = np.array([
    [1020.78, 0.0,     569.61],
    [0.0,     1027.20, 310.38],
    [0.0,     0.0,     1.0   ],
], dtype=np.float64)
ARM_D        = np.array([-0.216370, 0.076488, 0.000587, -0.000633, -0.024798],
                         dtype=np.float64)
ARM_CALIB_WH = (1280, 720)

# ── Object geometry ────────────────────────────────────────────────────────────
BALL_DIAM_M = 0.043   # golf ball: 43 mm

# ── YOLO settings ─────────────────────────────────────────────────────────────
YOLO_CONF    = 0.03
YOLO_IOU     = 0.45
YOLO_IMGSZ   = 960     # 960 → ~5.9× effective zoom on center crop, reliable to ~4m
YOLO_DEVICE  = "cuda"  # use "cpu" if no CUDA
YOLO_MAX_DET = 8

DOG_ACQUIRE_MIN_CONF = 0.03
DOG_TRACK_MIN_CONF   = 0.03

# ── Arm camera detection thresholds ──────────────────────────────────────────
ARM_MIN_CONF         = 0.03   # same as dog camera — arm camera has different optics
ARM_MIN_FRACTION     = 0.06   # 10% of bbox must be ball color

# ── Ground ROI / tiling (dog camera only) ────────────────────────────────────
# TILE_COUNT=1 → _ground_tile_specs returns only the single full ground ROI.
# One YOLO call ≈ 60ms cycle. More tiles = proportionally more lag.
GROUND_ROI_TOP_FRAC         = 0.40
GROUND_ROI_SIDE_MARGIN_FRAC = 0.02
GROUND_TILE_COUNT           = 1      # single full-ROI tile → 1 YOLO call ≈ 60ms
GROUND_TILE_OVERLAP_FRAC    = 0.35
GROUND_CENTER_ZOOM_FRACS    = (0.20,) # one center crop at 20% ROI width → ~5× zoom

# ── Box geometry filters ──────────────────────────────────────────────────────
MIN_BALL_RADIUS_PX  = 2.0    # raised from 2.0 — sub-3px detections are noise
BALL_BOX_MIN_ASPECT = 0.27    # reject long thin boxes

# ── Ball HSV filters ─────────────────────────────────────────────────────────
# OpenCV HSV scale: H 0-179, S 0-255, V 0-255.
# Tune with hsv_tuner.py under your actual lighting.

# Red wraps around the hue circle — two ranges needed.
_RED_LO1 = np.array([  0,  60,  40], dtype=np.uint8)
_RED_HI1 = np.array([ 20, 255, 255], dtype=np.uint8)
_RED_LO2 = np.array([155,  60,  40], dtype=np.uint8)
_RED_HI2 = np.array([179, 255, 255], dtype=np.uint8)

# Green — single range (H ~35-85), no wrap needed.
_GREEN_LO1 = np.array([ 35,  40,  60], dtype=np.uint8)
_GREEN_HI1 = np.array([ 85, 255, 255], dtype=np.uint8)
_GREEN_LO2 = np.array([ 35,  40,  60], dtype=np.uint8)  # duplicate — no second range
_GREEN_HI2 = np.array([ 85, 255, 255], dtype=np.uint8)

# Active color — set at startup via set_ball_color().  Default: red.
BALL_HSV_LO1 = _RED_LO1.copy()
BALL_HSV_HI1 = _RED_HI1.copy()
BALL_HSV_LO2 = _RED_LO2.copy()
BALL_HSV_HI2 = _RED_HI2.copy()

# Minimum fraction of bbox pixels that must match the color filter.
BALL_MIN_FRACTION = 0.10


def set_ball_color(color: str) -> None:
    """Switch the active ball color filter.  Call before starting the pipeline.

    Parameters
    ----------
    color : "red" (default) or "green"
    """
    global BALL_HSV_LO1, BALL_HSV_HI1, BALL_HSV_LO2, BALL_HSV_HI2
    if color == "green":
        BALL_HSV_LO1 = _GREEN_LO1.copy()
        BALL_HSV_HI1 = _GREEN_HI1.copy()
        BALL_HSV_LO2 = _GREEN_LO2.copy()
        BALL_HSV_HI2 = _GREEN_HI2.copy()
        _log.info("Ball color set to GREEN")
    else:
        BALL_HSV_LO1 = _RED_LO1.copy()
        BALL_HSV_HI1 = _RED_HI1.copy()
        BALL_HSV_LO2 = _RED_LO2.copy()
        BALL_HSV_HI2 = _RED_HI2.copy()
        _log.info("Ball color set to RED")

# ── Tracking gate (dog camera) ────────────────────────────────────────────────
DOG_TRACK_MAX_AGE_S = 0.8
DOG_TRACK_GATE_PX   = 220.0


# ── Shared data contract ──────────────────────────────────────────────────────

@dataclass
class TargetCoordinates:
    """Passed to BaseController and ArmController."""
    detected: bool
    dist_m:   float = 999.0
    dx_norm:  float = 0.0


# ── Undistorters ──────────────────────────────────────────────────────────────

class _FisheyeUndistorter:
    """Caches fisheye remap maps; rebuilds if resolution changes."""

    def __init__(self, K: np.ndarray, D: np.ndarray, calib_wh: Tuple[int, int]):
        self._k0 = K.copy()
        self._d0 = D.reshape(-1, 1)
        self._cw, self._ch = calib_wh
        self._wh = None
        self._map1 = self._map2 = self._k_new = None

    def undistort(self, img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        h, w = img.shape[:2]
        if self._wh != (w, h):
            sx, sy = w / self._cw, h / self._ch
            K = self._k0.copy()
            K[0, 0] *= sx; K[0, 2] *= sx
            K[1, 1] *= sy; K[1, 2] *= sy
            self._k_new = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
                K, self._d0, (w, h), np.eye(3), balance=0.0
            )
            self._map1, self._map2 = cv2.fisheye.initUndistortRectifyMap(
                K, self._d0, np.eye(3), self._k_new, (w, h), cv2.CV_16SC2
            )
            self._wh = (w, h)
        return cv2.remap(img, self._map1, self._map2, cv2.INTER_LINEAR), self._k_new.copy()


class _StandardUndistorter:
    """Caches standard radial/tangential remap maps."""

    def __init__(self, K: np.ndarray, D: np.ndarray, calib_wh: Tuple[int, int]):
        self._k0 = K.copy()
        self._d0 = D.copy()
        self._cw, self._ch = calib_wh
        self._wh = None
        self._map1 = self._map2 = self._k_new = None

    def undistort(self, img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        h, w = img.shape[:2]
        if self._wh != (w, h):
            sx, sy = w / self._cw, h / self._ch
            K = self._k0.copy()
            K[0, 0] *= sx; K[0, 2] *= sx
            K[1, 1] *= sy; K[1, 2] *= sy
            self._k_new, _ = cv2.getOptimalNewCameraMatrix(K, self._d0, (w, h), alpha=0)
            self._map1, self._map2 = cv2.initUndistortRectifyMap(
                K, self._d0, None, self._k_new, (w, h), cv2.CV_16SC2
            )
            self._wh = (w, h)
        return cv2.remap(img, self._map1, self._map2, cv2.INTER_LINEAR), self._k_new.copy()


# ── Tile spec helpers (dog camera only) ───────────────────────────────────────

def _ground_roi_spec(frame: np.ndarray) -> Tuple[int, int, int, int]:
    h, w     = frame.shape[:2]
    x_margin = int(round(GROUND_ROI_SIDE_MARGIN_FRAC * w))
    y0       = int(round(GROUND_ROI_TOP_FRAC * h))
    x0       = x_margin
    x1       = max(x0 + 2, w - x_margin)
    return x0, y0, x1, h


def _ground_tile_specs(frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
    x0, y0, x1, y1 = _ground_roi_spec(frame)
    roi_w  = max(2, x1 - x0)
    tiles: List[Tuple[int, int, int, int]] = [(x0, y0, x1, y1)]
    seen: set = {(int(x0), int(y0), int(x1), int(y1))}

    tile_count = max(1, GROUND_TILE_COUNT)
    if tile_count > 1:
        overlap = max(0.0, min(0.9, GROUND_TILE_OVERLAP_FRAC))
        tile_w  = int(math.ceil(roi_w / (1.0 + (tile_count - 1) * (1.0 - overlap))))
        tile_w  = max(64, min(roi_w, tile_w))
        step    = max(1, int(round(tile_w * (1.0 - overlap))))

        xs: List[int] = []
        cur = x0
        while cur + tile_w < x1:
            xs.append(cur)
            cur += step
            if len(xs) > 12:
                break
        xs.append(max(x0, x1 - tile_w))

        for sx in xs:
            ex  = min(x1, sx + tile_w)
            sx  = max(x0, ex - tile_w)
            key = (int(sx), int(y0), int(ex), int(y1))
            if key not in seen:
                seen.add(key)
                tiles.append(key)

    # Center zoom crops — applied regardless of GROUND_TILE_COUNT.
    # A narrow center crop sent to YOLO at imgsz=640 gives effective zoom
    # proportional to (ROI_width / crop_width), e.g. frac=0.35 → ~3× zoom.
    cx = 0.5 * (x0 + x1)
    for frac in GROUND_CENTER_ZOOM_FRACS:
        zoom_w = int(round(max(64.0, min(float(roi_w), frac * roi_w))))
        sx = int(round(cx - 0.5 * zoom_w))
        ex = sx + zoom_w
        sx = max(x0, sx); ex = min(x1, ex); sx = max(x0, ex - zoom_w)
        key = (int(sx), int(y0), int(ex), int(y1))
        if key not in seen:
            seen.add(key)
            tiles.append(key)

    return tiles


# ── Per-box helpers ───────────────────────────────────────────────────────────

def _bbox_center_radius(
    bbox: Tuple[int, int, int, int]
) -> Tuple[Optional[np.ndarray], float]:
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return None, 0.0
    center = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float64)
    radius = 0.25 * float((x2 - x1) + (y2 - y1))
    return center, radius


def _ball_color_fraction(img_bgr: np.ndarray, bbox: Tuple[int, int, int, int]) -> float:
    """Return the fraction of pixels inside bbox that match the ball color filter."""
    x1, y1, x2, y2 = bbox
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(img_bgr.shape[1], x2); y2 = min(img_bgr.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    crop = img_bgr[y1:y2, x1:x2]
    hsv  = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_or(
        cv2.inRange(hsv, BALL_HSV_LO1, BALL_HSV_HI1),
        cv2.inRange(hsv, BALL_HSV_LO2, BALL_HSV_HI2),
    )
    return float(np.count_nonzero(mask)) / float(mask.size)


def _refine_radius_from_mask(
    img_bgr: np.ndarray, bbox: Tuple[int, int, int, int]
) -> Tuple[Optional[np.ndarray], float]:
    """
    Fit a circle to the red color mask inside bbox.

    Returns (center_full_px, radius_px) in full-frame coordinates,
    or (None, 0.0) when the mask is too sparse to fit reliably.
    The radius is used for distance estimation — this is far more
    accurate than the YOLO bbox dimensions for tiny/close balls.
    """
    x1, y1, x2, y2 = bbox
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(img_bgr.shape[1], x2); y2 = min(img_bgr.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return None, 0.0

    crop = img_bgr[y1:y2, x1:x2]
    hsv  = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_or(
        cv2.inRange(hsv, BALL_HSV_LO1, BALL_HSV_HI1),
        cv2.inRange(hsv, BALL_HSV_LO2, BALL_HSV_HI2),
    )
    # Use a 2×2 kernel and skip MORPH_OPEN: OPEN with a 3×3 kernel erases blobs
    # smaller than ~6px — exactly the tiny balls we need to detect at range.
    # CLOSE alone fills small holes without destroying sub-6px detections.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, 0.0

    cnt = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(cnt) < 4.0:   # need at least 4 px² of colored area
        return None, 0.0

    (cx, cy), radius = cv2.minEnclosingCircle(cnt)
    # Convert crop-local coordinates back to full-frame coordinates
    center_full = np.array([float(cx) + x1, float(cy) + y1], dtype=np.float64)
    return center_full, float(radius)


def _is_ball_class(class_name: str) -> bool:
    label  = str(class_name).strip().lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", label) if t]
    if not tokens:
        return False
    if tokens == ["sports", "ball"]:
        return True
    return tokens[-1] == "ball"


# ── Main VisionCore ───────────────────────────────────────────────────────────

class VisionCore:
    """
    Wraps one shared YOLO model used by both camera pipelines.

    Dog-camera path:  process_dog_frame()
    Arm-camera path:  process_arm_frame()
    """

    def __init__(self, yolo_model_path: str = "yolo11n.pt", conf: float = YOLO_CONF):
        import torch
        if torch.cuda.is_available():
            _log.info(f"YOLO GPU: CUDA available — device 0 ({torch.cuda.get_device_name(0)})")
        else:
            _log.warning("YOLO GPU: CUDA NOT available — running on CPU (will be very slow!)")

        self.model = YOLO(yolo_model_path)
        self.model.to(YOLO_DEVICE)   # move to GPU — default load is CPU
        self.conf        = float(conf)
        self._infer_lock = threading.Lock()

        # Warmup: first CUDA inference compiles kernels (~3s), do it at init
        # so the first real frame isn't delayed.
        _log.info("YOLO warmup inference (compiles CUDA kernels, ~3s)...")
        import numpy as _np
        _dummy = _np.zeros((320, 320, 3), dtype=_np.uint8)
        self.model.predict(source=_dummy, imgsz=320, verbose=False, device=YOLO_DEVICE)
        _log.info("YOLO warmup done — GPU inference ready")

        self._dog_und    = _FisheyeUndistorter(DOG_K, DOG_D, DOG_CALIB_WH)
        self._arm_und    = _StandardUndistorter(ARM_K, ARM_D, ARM_CALIB_WH)

        # Dog tracking state
        self._dog_last_center: Optional[np.ndarray] = None
        self._dog_last_seen_t = 0.0

        # Ball class id filter
        self._ball_ids: Optional[List[int]] = self._resolve_ball_ids()

    def _resolve_ball_ids(self) -> Optional[List[int]]:
        names = getattr(self.model, "names", {})
        if not names:
            return None
        ids = [int(k) for k, v in names.items() if _is_ball_class(str(v))]
        return ids or None

    # ── Dog camera ────────────────────────────────────────────────────────────

    def process_dog_frame(
        self, frame_bgr: np.ndarray
    ) -> Tuple[TargetCoordinates, np.ndarray]:
        """
        Process one raw fisheye dog-camera frame.

        Returns
        -------
        (TargetCoordinates, debug_frame_bgr)
        """
        und, K = self._dog_und.undistort(frame_bgr)
        h, w   = und.shape[:2]
        names  = getattr(self.model, "names", {})

        tile_specs  = _ground_tile_specs(und)
        valid_specs = []
        tiles       = []
        for spec in tile_specs:
            tx0, ty0, tx1, ty1 = spec
            tile = und[ty0:ty1, tx0:tx1]
            if tile.size > 0:
                valid_specs.append(spec)
                tiles.append(tile)

        results = []
        if tiles:
            with self._infer_lock:
                results = self.model.predict(
                    source=tiles,
                    conf=self.conf,
                    iou=YOLO_IOU,
                    imgsz=YOLO_IMGSZ,
                    max_det=YOLO_MAX_DET,
                    verbose=False,
                    device=YOLO_DEVICE,
                    classes=self._ball_ids,
                )

        # Tracking gate
        track_center = None
        if (self._dog_last_center is not None
                and time.time() - self._dog_last_seen_t <= DOG_TRACK_MAX_AGE_S):
            track_center = self._dog_last_center

        best_score = -1.0
        best_center = best_bbox_full = None
        best_radius = best_dist = best_dx = best_conf = 0.0
        best_dist = 999.0
        detected  = False

        for (tx0, ty0, tx1, ty1), result in zip(valid_specs, results):
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            xyxy    = boxes.xyxy.cpu().numpy()
            confs   = boxes.conf.cpu().numpy()
            classes = boxes.cls.cpu().numpy().astype(int)

            for box_xyxy, conf, cls_id in zip(xyxy, confs, classes):
                cls_name = str(names.get(int(cls_id), ""))
                if names and not _is_ball_class(cls_name):
                    continue

                x1t, y1t, x2t, y2t = map(int, box_xyxy)
                bw = max(1, x2t - x1t); bh = max(1, y2t - y1t)
                aspect  = float(min(bw, bh)) / float(max(bw, bh))
                min_conf = DOG_TRACK_MIN_CONF if track_center is not None else DOG_ACQUIRE_MIN_CONF
                if float(conf) < min_conf or aspect < BALL_BOX_MIN_ASPECT:
                    continue

                bbox_full = (x1t + tx0, y1t + ty0, x2t + tx0, y2t + ty0)

                # Reject if not enough red pixels in the box
                if _ball_color_fraction(und, bbox_full) < BALL_MIN_FRACTION:
                    continue

                # Fit a circle to the color mask — gives continuous, accurate radius
                # as the ball grows in the frame. Falls back to bbox geometry if mask
                # is too sparse (very far away ball with few colored pixels).
                center_full, radius = _refine_radius_from_mask(und, bbox_full)
                if center_full is None or radius < MIN_BALL_RADIUS_PX:
                    center_tile, radius = _bbox_center_radius((x1t, y1t, x2t, y2t))
                    if center_tile is None or radius < MIN_BALL_RADIUS_PX:
                        continue
                    center_full = np.array([center_tile[0] + tx0, center_tile[1] + ty0])

                dist_m  = self._dist(radius, K)
                dx_norm = self._dx(center_full[0], K)

                score = radius * (0.5 + float(conf))
                if track_center is not None:
                    delta = float(np.linalg.norm(center_full - track_center))
                    gate  = max(0.35, math.exp(-0.5 * (delta / DOG_TRACK_GATE_PX) ** 2))
                    score *= gate

                if score > best_score:
                    best_score    = score
                    best_radius   = radius
                    best_center   = center_full
                    best_dist     = dist_m
                    best_dx       = dx_norm
                    best_conf     = float(conf)
                    best_bbox_full = bbox_full
                    detected      = True

        # ── Debug annotation ──────────────────────────────────────────────────
        debug = und.copy()
        for idx, (tx0, ty0, tx1, ty1) in enumerate(tile_specs):
            cv2.rectangle(debug, (tx0, ty0), (tx1, ty1),
                          (0, 255, 255), 2 if idx == 0 else 1)

        if detected and best_center is not None:
            self._dog_last_center = best_center.copy()
            self._dog_last_seen_t = time.time()
            cx, cy = int(round(float(best_center[0]))), int(round(float(best_center[1])))
            rr = max(4, int(best_radius))
            _log.info(
                f"[DET] dist={best_dist:.2f}m  r={best_radius:.1f}px  conf={best_conf:.2f}  "
                f"bbox={best_bbox_full}  dx={best_dx:+.3f}"
            )
            cv2.circle(debug, (cx, cy), rr, (0, 140, 255), 2)
            cv2.circle(debug, (cx, cy), 3, (255, 255, 255), -1)
            if best_bbox_full:
                cv2.rectangle(debug, best_bbox_full[:2], best_bbox_full[2:], (0, 140, 255), 1)
            cv2.putText(debug,
                        f"dist={best_dist:.2f}m  dx={best_dx:+.3f}  r={best_radius:.1f}px  conf={best_conf:.2f}",
                        (cx + rr + 4, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 255), 2, cv2.LINE_AA)
        else:
            if time.time() - self._dog_last_seen_t > DOG_TRACK_MAX_AGE_S:
                self._dog_last_center = None
            cv2.putText(debug, "SEARCHING...", (20, h - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)

        return TargetCoordinates(detected=detected, dist_m=best_dist, dx_norm=best_dx), debug

    # ── Arm camera ────────────────────────────────────────────────────────────

    def process_arm_frame(
        self, frame_bgr: np.ndarray
    ) -> Tuple[TargetCoordinates, np.ndarray, Optional[np.ndarray]]:
        """
        Process one standard-lens arm-camera frame.

        Single full-frame YOLO pass; no ground tiling needed.

        Returns
        -------
        (TargetCoordinates, debug_frame_bgr, p_ball_in_cam)

        p_ball_in_cam
            Homogeneous (4,) array [X, Y, Z, 1] in camera coordinates, or
            None if not detected.  Pass to ArmController.ball_cam_to_base().
        """
        und, K = self._arm_und.undistort(frame_bgr)
        h, w   = und.shape[:2]
        names  = getattr(self.model, "names", {})

        with self._infer_lock:
            results = self.model.predict(
                source=und,
                conf=self.conf,
                iou=YOLO_IOU,
                imgsz=YOLO_IMGSZ,
                max_det=YOLO_MAX_DET,
                verbose=False,
                device=YOLO_DEVICE,
                classes=self._ball_ids,
            )

        best_center = best_bbox = None
        best_radius = 0.0
        best_dist   = 999.0
        best_dx     = 0.0
        detected    = False

        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            xyxy    = boxes.xyxy.cpu().numpy()
            confs   = boxes.conf.cpu().numpy()
            classes = boxes.cls.cpu().numpy().astype(int)

            for box_xyxy, conf, cls_id in zip(xyxy, confs, classes):
                cls_name = str(names.get(int(cls_id), ""))
                if names and not _is_ball_class(cls_name):
                    continue

                x1, y1, x2, y2 = map(int, box_xyxy)
                bw = max(1, x2 - x1); bh = max(1, y2 - y1)
                aspect = float(min(bw, bh)) / float(max(bw, bh))
                if float(conf) < ARM_MIN_CONF or aspect < BALL_BOX_MIN_ASPECT:
                    continue

                center, radius = _bbox_center_radius((x1, y1, x2, y2))
                if center is None or radius < MIN_BALL_RADIUS_PX:
                    continue

                # Reject if YOLO bbox touches the frame boundary — means the ball
                # is genuinely clipped → bbox dimensions are wrong → bad pose.
                if x1 <= 0 or y1 <= 0 or x2 >= w or y2 >= h:
                    continue

                # Strict color filter for arm camera
                if _ball_color_fraction(und, (x1, y1, x2, y2)) < ARM_MIN_FRACTION:
                    continue

                dist_m  = self._dist(radius, K)
                dx_norm = self._dx(center[0], K)

                if radius > best_radius:
                    best_radius = radius
                    best_center = center
                    best_dist   = dist_m
                    best_dx     = dx_norm
                    best_bbox   = (x1, y1, x2, y2)
                    detected    = True

        # ── Debug annotation ──────────────────────────────────────────────────
        debug = und.copy()
        if detected and best_center is not None:
            cx, cy = int(round(float(best_center[0]))), int(round(float(best_center[1])))
            rr = max(4, int(best_radius))
            cv2.circle(debug, (cx, cy), rr, (255, 100, 0), 2)
            cv2.circle(debug, (cx, cy), 3, (255, 255, 255), -1)
            if best_bbox:
                cv2.rectangle(debug, best_bbox[:2], best_bbox[2:], (255, 100, 0), 1)
            cv2.putText(debug,
                        f"ARM dist={best_dist:.2f}m  dx={best_dx:+.3f}  r={best_radius:.1f}px",
                        (cx + rr + 4, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 100, 0), 2, cv2.LINE_AA)
        else:
            cv2.putText(debug, "ARM SEARCHING...", (20, h - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)

        # ── 3-D position in camera frame ──────────────────────────────────────
        p_ball_in_cam: Optional[np.ndarray] = None
        if detected and best_center is not None and best_dist < 990.0:
            Z   = best_dist
            X_c = (float(best_center[0]) - float(K[0, 2])) / float(K[0, 0]) * Z
            Y_c = (float(best_center[1]) - float(K[1, 2])) / float(K[1, 1]) * Z
            p_ball_in_cam = np.array([X_c, Y_c, Z, 1.0], dtype=np.float64)

        return (
            TargetCoordinates(detected=detected, dist_m=best_dist, dx_norm=best_dx),
            debug,
            p_ball_in_cam,
        )

    # ── Shared geometry helpers ───────────────────────────────────────────────

    def _dist(self, radius_px: float, K: np.ndarray) -> float:
        if radius_px <= 1e-6:
            return 999.0
        return (float(K[0, 0]) * BALL_DIAM_M) / (2.0 * float(radius_px))

    def _dx(self, cx: float, K: np.ndarray) -> float:
        return float((cx - float(K[0, 2])) / float(K[0, 0]))
