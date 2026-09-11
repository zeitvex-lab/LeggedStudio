#!/usr/bin/env python3
"""
pink_detector.py
================
Classical CV detector for the upright pink rectangular object.

Detection pipeline
------------------
1. Convert BGR → HSV.
2. Threshold for pink/magenta hue.
   Two ranges are OR-ed together to handle hue wrap-around near red.
3. Morphological opening  (remove isolated noise pixels).
   Morphological closing  (fill small holes inside the blob).
4. Find external contours.
5. Filter by minimum area and minimum aspect ratio (tall/thin shape).
6. Return the largest qualifying contour as the detection.

Distance / pose estimate
------------------------
Two methods are available:

  detect()      — fast, height-based:  Z ≈ fy × H_real / h_pixels
                  Good for visual-servo approach (robust even if the object
                  partially overflows the frame).

  detect_pnp()  — PnP-based:  fit a rotated rectangle to the segmented contour,
                  then solvePnP with those 4 image corners and the known
                  physical size. Returns a full 3D position of the
                  object face centre in camera frame (pos_cam).  Accuracy is
                  < 2 cm at 0.3–0.8 m because the 302 mm height dominates the
                  PnP solution.  Use this once the robot has stopped to compute
                  the exact grasp coordinates.

Object dimensions
-----------------
  width  = 20.5  mm = 0.0205  m   (very thin — horizontal PnP component noisy)
  height = 302.39 mm = 0.30239 m  (tall    — Z and Y components well-constrained)

Tuning notes
------------
The default HSV ranges are a starting point.  Pink colour appearance varies
with lighting.  Run the debug overlay (want_debug=True) and adjust
PINK_H_LO / PINK_H_HI accordingly.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


# ---------------------------------------------------------------------------
#  Physical object dimensions
# ---------------------------------------------------------------------------
OBJ_W_M = 0.0205    # width  (metres)
OBJ_H_M = 0.30239   # height (metres)

# 3D corners in object frame, origin at face centre:
#   X right, Y up, Z toward camera (out of the face)
_OBJ_PTS = np.array([
    [-OBJ_W_M / 2,  OBJ_H_M / 2, 0.0],   # top-left
    [ OBJ_W_M / 2,  OBJ_H_M / 2, 0.0],   # top-right
    [ OBJ_W_M / 2, -OBJ_H_M / 2, 0.0],   # bottom-right
    [-OBJ_W_M / 2, -OBJ_H_M / 2, 0.0],   # bottom-left
], dtype=np.float64)


# ---------------------------------------------------------------------------
#  Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PinkDetection:
    """
    Result of one pink-object detection attempt on a single arm-camera frame.

    Fields
    ------
    detected         True if a qualifying blob was found.
    cx, cy           Centroid of the detection in pixel coordinates.
    bbox             Bounding rectangle: (x, y, w, h) in pixels.
    pixel_height     Fitted long-edge height in pixels.
    estimated_dist_m Forward distance from the height-based pinhole formula (m).
    dx_norm          Horizontal angular offset:  (cx - W/2) / fx
                       > 0  object is to the right  (command vyaw < 0)
                       < 0  object is to the left   (command vyaw > 0)
    pos_cam          3D position of the object face centre in camera frame
                     [Xc, Yc, Zc] (metres).  Set only by detect_pnp().
    pnp_ok           True if the PnP solve in detect_pnp() succeeded.
    debug_img        Annotated copy of the input frame (set only when
                     want_debug=True is passed to detect / detect_pnp).
    """
    detected:         bool
    cx:               float = 0.0
    cy:               float = 0.0
    bbox:             Tuple[int, int, int, int] = (0, 0, 0, 0)
    quad_px:          Optional[np.ndarray] = None   # (4,2): tl, tr, br, bl
    pixel_height:     float = 0.0
    estimated_dist_m: float = 9999.0
    dx_norm:          float = 0.0
    pos_cam:          Optional[np.ndarray] = None   # [Xc, Yc, Zc]
    pnp_ok:           bool = False
    rvec:             Optional[np.ndarray] = None   # PnP rotation vec (3,)
    tvec:             Optional[np.ndarray] = None   # PnP translation vec (3,)
    debug_img:        Optional[np.ndarray] = None


# ---------------------------------------------------------------------------
#  Detector class
# ---------------------------------------------------------------------------

class PinkObjectDetector:
    """
    Detects the upright pink object in arm-camera BGR frames.

    Args
    ----
    K               Arm-camera 3×3 intrinsic matrix (np.float64).
    D               Arm-camera distortion coefficients (np.float64, length 5).
    img_w, img_h    Arm camera image dimensions in pixels.
    hsv_lo, hsv_hi  Primary HSV lower / upper bounds (np.uint8 arrays of length 3).
    hsv_lo2, hsv_hi2 Secondary HSV range OR-ed with the primary.
                    Needed because pink/magenta can wrap around the hue axis
                    (hue ≈ 140–180 and hue ≈ 0–20 for red-pink shades).
    use_second_range Whether to enable the secondary HSV range.
    min_area        Minimum contour area in pixels² to consider as a candidate.
    min_aspect      Minimum height/width ratio.  The object is tall and thin
                    (height ≈ 302 mm, width ≈ 20 mm → ratio ≈ 15 real-world),
                    so values around 2.5–4 safely reject wide/flat blobs while
                    being forgiving at large distances where the object is small.
    """

    # ── Default HSV ranges ──────────────────────────────────────────────────
    # Pink / magenta: hue 140–180 in OpenCV (0–180 scale), moderate-to-high
    # saturation and value.
    _DEFAULT_HSV_LO  = np.array([140,  50,  80], dtype=np.uint8)
    _DEFAULT_HSV_HI  = np.array([180, 255, 255], dtype=np.uint8)
    # Red-pink wrap-around: hue 0–20
    _DEFAULT_HSV_LO2 = np.array([  0,  50,  80], dtype=np.uint8)
    _DEFAULT_HSV_HI2 = np.array([ 20, 255, 255], dtype=np.uint8)

    def __init__(
        self,
        K:                np.ndarray,
        D:                np.ndarray,
        img_w:            int   = 1280,
        img_h:            int   = 720,
        hsv_lo:           Optional[np.ndarray] = None,
        hsv_hi:           Optional[np.ndarray] = None,
        hsv_lo2:          Optional[np.ndarray] = None,
        hsv_hi2:          Optional[np.ndarray] = None,
        use_second_range: bool  = True,
        min_area:         int   = 800,
        min_aspect:       float = 2.5,
    ):
        self.K    = np.array(K, dtype=np.float64)
        self.D    = np.array(D, dtype=np.float64)
        self.fx   = float(K[0, 0])
        self.fy   = float(K[1, 1])
        # Calibrated principal point — NOT necessarily at image centre.
        # ARM_K has cx=569.61, cy=310.38 vs frame centre 640, 360.
        # Using img_w/2 as centre would introduce a ~70 px systematic offset.
        self.cx_p = float(K[0, 2])
        self.cy_p = float(K[1, 2])
        self.img_w = int(img_w)
        self.img_h = int(img_h)

        self.hsv_lo  = (hsv_lo  if hsv_lo  is not None else self._DEFAULT_HSV_LO.copy())
        self.hsv_hi  = (hsv_hi  if hsv_hi  is not None else self._DEFAULT_HSV_HI.copy())
        self.hsv_lo2 = (hsv_lo2 if hsv_lo2 is not None else self._DEFAULT_HSV_LO2.copy())
        self.hsv_hi2 = (hsv_hi2 if hsv_hi2 is not None else self._DEFAULT_HSV_HI2.copy())

        self.use_second_range = bool(use_second_range)
        self.min_area         = int(min_area)
        self.min_aspect       = float(min_aspect)

        # Pre-build morphology kernels (reused every frame for speed)
        self._k_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,  5))
        self._k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    # -------------------------------------------------------------------------

    def _undistort_pixel(self, x_px: float, y_px: float) -> Tuple[float, float]:
        """
        Undistort one pixel location back into the calibrated image plane.

        Returns pixel coordinates in the same pinhole model as self.K.
        """
        pts = np.array([[[float(x_px), float(y_px)]]], dtype=np.float64)
        pts_u = cv2.undistortPoints(pts, self.K, self.D, P=self.K)
        return float(pts_u[0, 0, 0]), float(pts_u[0, 0, 1])

    def _order_quad_upright(self, pts: np.ndarray) -> np.ndarray:
        """
        Order 4 image points as top-left, top-right, bottom-right, bottom-left.

        The pink target is expected to stay roughly upright in the image, so
        splitting the points into top and bottom pairs by y-coordinate is a
        stable way to get a consistent ordering for solvePnP.
        """
        pts = np.asarray(pts, dtype=np.float64).reshape(4, 2)
        idx = np.argsort(pts[:, 1])
        top = pts[idx[:2]]
        bot = pts[idx[2:]]
        top = top[np.argsort(top[:, 0])]
        bot = bot[np.argsort(bot[:, 0])]
        return np.array([top[0], top[1], bot[1], bot[0]], dtype=np.float64)

    def _fit_quad(self, cnt: np.ndarray) -> np.ndarray:
        """
        Fit a rotated rectangle to the contour and return ordered image corners.
        """
        rect = cv2.minAreaRect(cnt)
        quad = cv2.boxPoints(rect)
        return self._order_quad_upright(quad)

    def _quad_height_px(self, quad_px: np.ndarray) -> float:
        """
        Return the average length of the two long rectangle edges in pixels.
        """
        q = np.asarray(quad_px, dtype=np.float64).reshape(4, 2)
        edge01 = float(np.linalg.norm(q[1] - q[0]))
        edge12 = float(np.linalg.norm(q[2] - q[1]))
        edge23 = float(np.linalg.norm(q[3] - q[2]))
        edge30 = float(np.linalg.norm(q[0] - q[3]))
        return max(0.5 * (edge01 + edge23), 0.5 * (edge12 + edge30))

    def estimate_pos_cam(self, det: PinkDetection) -> Optional[np.ndarray]:
        """
        Estimate the object centre in camera coordinates from centroid + height.

        This is intentionally simpler than full PnP: for a very thin object,
        the apparent width is noisy while the height is much more stable.  We
        therefore use the known object height to estimate depth, then back-
        project the undistorted centroid ray to get X/Y.
        """
        if (not det.detected) or det.pixel_height <= 1.0:
            return None
        if det.estimated_dist_m <= 0.0 or not np.isfinite(det.estimated_dist_m):
            return None

        cx_u, cy_u = self._undistort_pixel(det.cx, det.cy)
        z = float(det.estimated_dist_m)
        x = (cx_u - self.cx_p) * z / self.fx
        y = (cy_u - self.cy_p) * z / self.fy
        return np.array([x, y, z], dtype=np.float64)

    # -------------------------------------------------------------------------

    def detect(self, frame_bgr: np.ndarray, want_debug: bool = False) -> PinkDetection:
        """
        Run detection on one arm-camera frame.

        Args
        ----
        frame_bgr   BGR image from the arm camera.
        want_debug  If True, fill det.debug_img with an annotated overlay.

        Returns
        -------
        PinkDetection with detected=True if a qualifying blob was found.
        """
        # 1. Colour segmentation in HSV
        hsv  = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.hsv_lo, self.hsv_hi)

        if self.use_second_range:
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, self.hsv_lo2, self.hsv_hi2))

        # 2. Morphology: remove noise then fill holes
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  self._k_open)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._k_close)

        # 3. Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 4. Filter: area + aspect ratio → keep largest passing contour
        best_cnt  = None
        best_area = 0.0
        best_bbox = (0, 0, 0, 0)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            if w == 0:
                continue
            if (h / float(w)) < self.min_aspect:
                continue  # too wide / not tall enough

            if area > best_area:
                best_area = area
                best_cnt  = cnt
                best_bbox = (x, y, w, h)

        if best_cnt is None:
            det = PinkDetection(detected=False)
            if want_debug:
                det.debug_img = self._draw_debug(frame_bgr, mask, None)
            return det

        # 5. Compute centroid from moments
        bx, by, bw, bh = best_bbox
        quad_px = self._fit_quad(best_cnt)
        M = cv2.moments(best_cnt)
        if M["m00"] > 1e-6:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
        else:
            cx = bx + bw / 2.0
            cy = by + bh / 2.0

        # 6. Distance estimate and horizontal offset
        pixel_height = float(self._quad_height_px(quad_px))
        est_dist = (
            (self.fy * OBJ_H_M / pixel_height) if pixel_height > 1.0
            else 9999.0
        )

        # Undistort the centroid before computing the angular offset.
        # Raw centroid in a distorted frame is shifted by lens distortion.
        # cv2.undistortPoints with P=K returns corrected pixel coordinates.
        # Then use the calibrated principal point (K[0,2], K[1,2]), NOT the
        # frame centre (img_w/2), as the reference — they differ by ~70 px.
        cx_u, _ = self._undistort_pixel(cx, cy)
        dx_norm = (cx_u - self.cx_p) / self.fx

        det = PinkDetection(
            detected=True,
            cx=float(cx),
            cy=float(cy),
            bbox=best_bbox,
            quad_px=quad_px.copy(),
            pixel_height=pixel_height,
            estimated_dist_m=float(est_dist),
            dx_norm=float(dx_norm),
        )
        if want_debug:
            det.debug_img = self._draw_debug(frame_bgr, mask, det)
        return det

    # -------------------------------------------------------------------------

    def detect_pnp(
        self, frame_bgr: np.ndarray, want_debug: bool = False
    ) -> PinkDetection:
        """
        Run detection then solve PnP to get the full 3D position.

        Calls detect() first, then maps the 4 contour-fitted rectangle corners
        to the known physical corners of the object and runs solvePnP.

        The result is returned in det.pos_cam = [Xc, Yc, Zc] (metres) —
        the 3D position of the object face centre in camera frame.
        Zc is the depth (distance); Xc and Yc are the lateral offsets.

        det.pnp_ok is False if the solve failed or the blob was not found.
        det.estimated_dist_m is always populated from the height formula as a
        fallback (useful when the object partially overflows the frame).
        """
        det = self.detect(frame_bgr, want_debug=False)

        if not det.detected:
            if want_debug:
                h, w = frame_bgr.shape[:2]
                empty_mask = np.zeros((h, w), dtype=np.uint8)
                det.debug_img = self._draw_debug(frame_bgr, empty_mask, None)
            return det

        # 2D image corners matching the 3D _OBJ_PTS order:
        #   top-left, top-right, bottom-right, bottom-left
        if det.quad_px is not None and np.asarray(det.quad_px).shape == (4, 2):
            img_pts = np.asarray(det.quad_px, dtype=np.float64)
        else:
            bx, by, bw, bh = det.bbox
            img_pts = np.array([
                [bx,        by      ],
                [bx + bw,   by      ],
                [bx + bw,   by + bh ],
                [bx,        by + bh ],
            ], dtype=np.float64)

        # IPPE_SQUARE not valid here (not a square), use IPPE for planar targets.
        ok, rvec, tvec = cv2.solvePnP(
            _OBJ_PTS, img_pts, self.K, self.D,
            flags=cv2.SOLVEPNP_IPPE,
        )

        if ok:
            pos = tvec.reshape(3)
            # If Z is negative the wrong solution was chosen; try the other one.
            if pos[2] < 0:
                _, rvec2, tvec2 = cv2.solvePnP(
                    _OBJ_PTS, img_pts, self.K, self.D,
                    rvec=rvec, tvec=tvec,
                    useExtrinsicGuess=True,
                    flags=cv2.SOLVEPNP_ITERATIVE,
                )
                pos2 = tvec2.reshape(3)
                if pos2[2] > 0:
                    pos  = pos2
                    rvec = rvec2
                    tvec = tvec2
            det.pos_cam = pos.copy()
            det.rvec    = rvec.reshape(3).copy()
            det.tvec    = tvec.reshape(3).copy()
            det.pnp_ok  = True
            # Override distance with the more accurate PnP Z
            det.estimated_dist_m = float(pos[2])

        if want_debug:
            hsv  = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, self.hsv_lo, self.hsv_hi)
            if self.use_second_range:
                mask = cv2.bitwise_or(mask, cv2.inRange(hsv, self.hsv_lo2, self.hsv_hi2))
            det.debug_img = self._draw_debug(frame_bgr, mask, det)

        return det

    # -------------------------------------------------------------------------

    def _draw_debug(
        self,
        frame: np.ndarray,
        mask:  np.ndarray,
        det:   Optional[PinkDetection],
    ) -> np.ndarray:
        """Return an annotated copy of the frame for visualisation."""
        dbg = frame.copy()

        # Tint segmented pixels green
        tint = np.zeros_like(frame)
        tint[mask > 0] = (0, 180, 0)
        dbg = cv2.addWeighted(dbg, 0.75, tint, 0.25, 0)

        # Draw vertical centre reference line
        cx_img = self.img_w // 2
        cv2.line(dbg, (cx_img, 0), (cx_img, self.img_h), (200, 200, 0), 1)

        if det is not None and det.detected:
            bx, by, bw, bh = det.bbox
            cv2.rectangle(dbg, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
            if det.quad_px is not None and np.asarray(det.quad_px).shape == (4, 2):
                quad = np.round(det.quad_px).astype(np.int32).reshape(-1, 1, 2)
                cv2.polylines(dbg, [quad], isClosed=True, color=(255, 180, 0), thickness=2)
            cv2.circle(dbg, (int(det.cx), int(det.cy)), 6, (0, 0, 255), -1)
            if det.pnp_ok and det.pos_cam is not None:
                label = (f"PnP Z={det.pos_cam[2]:.3f}m "
                         f"X={det.pos_cam[0]:+.3f}m Y={det.pos_cam[1]:+.3f}m")
            else:
                label = f"d={det.estimated_dist_m:.2f}m  dx={det.dx_norm:+.3f}"
            cv2.putText(
                dbg, label,
                (bx, max(by - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2,
            )

        return dbg
