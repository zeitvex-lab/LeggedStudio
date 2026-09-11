#!/usr/bin/env python3
"""
vision_pose.py
==============
Stage 1:
  - Undistort fisheye image using intrinsics
  - Detect AprilTag
  - Produce raw tag pose T_cam_tag (camera -> tag)

NO filtering/fusion/control here.
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Any

import numpy as np
import cv2
import math

# --- AprilTag backend selection ---
# Try to import pyapriltags first (recommended). If unavailable, fall back
# to pupil_apriltags. If neither is installed, exit with a clear error message.
APRILTAG_BACKEND = None
try:
    from pyapriltags import Detector
    APRILTAG_BACKEND = "pyapriltags"
except ImportError:
    try:
        from pupil_apriltags import Detector
        APRILTAG_BACKEND = "pupil_apriltags"
    except ImportError as e:
        raise SystemExit(
            "Missing dependency: pyapriltags (recommended) or pupil-apriltags\n"
            "Install with: pip3 install pyapriltags\n"
            "Fallback: pip3 install pupil-apriltags\n"
            f"Original error: {e}"
        )


@dataclass
class TagObservation:
    """
    Holds the result of one AprilTag detection attempt on a single frame.

    Fields:
      t         - timestamp (seconds) of the frame
      visible   - True if the target tag was found in this frame
      tag_id    - ID of the tag we are tracking
      T_cam_tag - 4x4 homogeneous transform: camera-frame to tag-frame (None if not visible)
      corners_px- pixel coordinates of the tag's 4 corners in the undistorted image, shape (4,2)
      center_px - pixel coordinates of the tag's center, shape (2,)
      debug_img - undistorted frame with tag overlay drawn on it (only set when want_debug=True)
    """
    t: float
    visible: bool
    tag_id: int
    T_cam_tag: Optional[np.ndarray] = None  # 4x4
    corners_px: Optional[np.ndarray] = None # (4,2)
    center_px: Optional[np.ndarray] = None  # (2,)
    debug_img: Optional[np.ndarray] = None  # undistorted image with overlay (if requested)


class FisheyeUndistorter:
    """
    Removes fisheye lens distortion from images using OpenCV's fisheye model.

    The undistortion maps are computed once per image resolution and cached.
    If a different resolution is seen (e.g. the camera was reconfigured), the
    maps are recomputed automatically.

    Args:
      K     - 3x3 camera intrinsic matrix from calibration (at calib_wh resolution)
      D     - fisheye distortion coefficients (4 values: k1, k2, k3, k4)
      calib_wh - (width, height) at which K and D were calibrated
    """
    def __init__(self, K: np.ndarray, D: np.ndarray, calib_wh: Tuple[int, int]):
        self.K0 = K.astype(np.float64)
        self.D0 = D.astype(np.float64).reshape(-1, 1)
        self.calib_w, self.calib_h = calib_wh

        # Cached state — populated on first call to undistort()
        self._wh = None    # last image size for which maps were built
        self._map1 = None  # x-remap table (CV_16SC2)
        self._map2 = None  # y-remap table
        self._Knew = None  # new pinhole camera matrix for the undistorted image

    def _scale_K(self, w: int, h: int) -> np.ndarray:
        """
        Scale the calibration intrinsic matrix K to a different image resolution.

        OpenCV calibration is tied to the resolution at which it was performed.
        If the incoming frame is a different size, we must scale focal lengths
        (fx, fy) and principal point (cx, cy) proportionally.
        """
        sx = w / float(self.calib_w)
        sy = h / float(self.calib_h)
        K = self.K0.copy()
        K[0, 0] *= sx  # fx
        K[0, 2] *= sx  # cx
        K[1, 1] *= sy  # fy
        K[1, 2] *= sy  # cy
        return K

    def undistort(self, img_bgr: np.ndarray, balance: float = 0.0) -> Tuple[np.ndarray, np.ndarray]:
        """
        Undistort a fisheye image and return (undistorted_image, K_new).

        K_new is the new pinhole intrinsic matrix valid for the undistorted image.
        It is used downstream for PnP pose estimation.

        balance=0.0 crops to the valid pixel region (no black borders).
        balance=1.0 retains all original pixels (may have black borders).

        The remap tables are rebuilt only when the input resolution changes.
        """
        h, w = img_bgr.shape[:2]
        if self._wh != (w, h):
            # Resolution changed — rebuild undistortion maps
            K = self._scale_K(w, h)
            R = np.eye(3, dtype=np.float64)  # no rotation between camera axes
            # Compute the optimal new camera matrix for the undistorted view
            self._Knew = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
                K, self.D0, (w, h), R, balance=balance
            )
            # Build pixel-to-pixel remap tables (CV_16SC2 = fast fixed-point format)
            self._map1, self._map2 = cv2.fisheye.initUndistortRectifyMap(
                K, self.D0, R, self._Knew, (w, h), cv2.CV_16SC2
            )
            self._wh = (w, h)

        # Apply the precomputed remap to remove fisheye distortion
        und = cv2.remap(
            img_bgr, self._map1, self._map2,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT
        )
        return und, self._Knew


def tag_pose_from_corners(
    corners_px: np.ndarray,
    K: np.ndarray,
    tag_size_m: float
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Estimate the 6-DoF pose of an AprilTag from its four detected corner pixels.

    Uses OpenCV's solvePnP to solve the Perspective-n-Point problem:
      X_cam = R * X_tag + t

    The tag is modelled as a flat square centred at the origin in its own frame:
      top-left    (-s/2, -s/2, 0)
      top-right   ( s/2, -s/2, 0)
      bottom-right( s/2,  s/2, 0)
      bottom-left (-s/2,  s/2, 0)

    Args:
      corners_px  - detected corner pixel positions in the undistorted image, shape (4,2)
      K           - 3x3 pinhole camera intrinsic matrix (for the undistorted image)
      tag_size_m  - physical side length of the tag in metres

    Returns:
      (rvec, tvec) on success, or None if solvePnP fails.
      rvec - Rodrigues rotation vector (3,1) encoding camera-to-tag rotation
      tvec - translation vector (3,1), tag origin in camera coordinates (metres)
    """
    s = float(tag_size_m)
    # 3-D coordinates of the tag's four corners in the tag's own coordinate frame
    obj = np.array([
        [-s/2, -s/2, 0.0],
        [ s/2, -s/2, 0.0],
        [ s/2,  s/2, 0.0],
        [-s/2,  s/2, 0.0],
    ], dtype=np.float32)

    img = corners_px.astype(np.float32)
    dist = np.zeros((4, 1), dtype=np.float32)  # undistorted => ~0 distortion

    # IPPE_SQUARE is a closed-form solver optimised for planar square targets;
    # it is more accurate than iterative methods for flat markers like AprilTags.
    ok, rvec, tvec = cv2.solvePnP(
        obj, img, K.astype(np.float64), dist,
        flags=cv2.SOLVEPNP_IPPE_SQUARE
    )
    if not ok:
        return None
    return rvec, tvec


def T_from_rvec_tvec(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    """
    Build a 4x4 homogeneous transform from a Rodrigues rotation vector and a translation vector.

    Converts the compact Rodrigues representation (used by solvePnP) into a
    full rotation matrix via cv2.Rodrigues, then assembles the SE(3) matrix:
      | R  t |
      | 0  1 |
    """
    R, _ = cv2.Rodrigues(rvec)  # convert Rodrigues vector -> 3x3 rotation matrix
    t = tvec.reshape(3)
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def T_from_R_t(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    """
    Build a 4x4 homogeneous transform from a rotation matrix R and translation t.

    Accepts any array-like for R (e.g. the pose_R attribute returned directly by
    some AprilTag detector backends) and reshapes / casts as needed.
      | R  t |
      | 0  1 |
    """
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = np.asarray(R, dtype=np.float64).reshape(3, 3)
    T[:3, 3] = np.asarray(t, dtype=np.float64).reshape(3)
    return T


class VisionPoseEstimator:
    """
    High-level pipeline: fisheye undistortion → AprilTag detection → 6-DoF pose.

    Wraps FisheyeUndistorter and an AprilTag Detector into a single `process()`
    call that consumes a raw BGR frame and returns a TagObservation.

    Args:
      K0               - 3x3 calibration intrinsic matrix (at calib_wh resolution)
      D0               - fisheye distortion coefficients
      calib_wh         - (width, height) at which K0/D0 were calibrated
      tag_family       - AprilTag family string, e.g. "tag36h11"
      tag_id           - numeric ID of the tag we want to track
      tag_size         - physical side length of the tag in metres
      undistort_balance- 0.0 = no black borders (crop); 1.0 = keep all pixels
    """
    def __init__(
        self,
        K0: np.ndarray,
        D0: np.ndarray,
        calib_wh=(1920, 1080),
        tag_family: str = "tag36h11",
        tag_id: int = 0,
        tag_size: float = 0.18,
        undistort_balance: float = 0.0,
    ):
        self.tag_family = str(tag_family)
        self.tag_id = int(tag_id)
        self.tag_size = float(tag_size)
        self.undistort_balance = float(undistort_balance)

        # Build the fisheye undistorter and the AprilTag detector
        self.und = FisheyeUndistorter(K0, D0, calib_wh=calib_wh)
        self.det = Detector(families=self.tag_family)

    def backend_name(self) -> str:
        """Return which AprilTag library was loaded at import time."""
        return APRILTAG_BACKEND or "unknown"

    def process(self, img_bgr: np.ndarray, t_now: float, want_debug: bool = False) -> Tuple[TagObservation, Optional[np.ndarray]]:
        """
        Process one BGR frame and attempt to detect the target AprilTag.

        Pipeline:
          1. Undistort the fisheye image → img_und, K_new
          2. Convert to greyscale for the detector
          3. Run AprilTag detection (with in-detector pose if the backend supports it)
          4. If the target tag is found, compute its 4x4 camera→tag transform
          5. Optionally annotate a debug image with corners / centre / label

        Args:
          img_bgr    - raw fisheye frame in BGR format (None is handled gracefully)
          t_now      - timestamp of the frame in seconds
          want_debug - if True, store an annotated copy of the undistorted frame
                       in obs.debug_img

        Returns:
          obs   - TagObservation (visible=False if the tag was not found)
          K_new - pinhole intrinsic matrix of the undistorted image (or None)
        """
        if img_bgr is None:
            return TagObservation(t=t_now, visible=False, tag_id=self.tag_id), None

        # Step 1 & 2: undistort and convert to grey
        img_und, K_new = self.und.undistort(img_bgr, balance=self.undistort_balance)
        gray = cv2.cvtColor(img_und, cv2.COLOR_BGR2GRAY)

        # Extract scalar intrinsics needed by the detector's pose solver
        fx, fy = float(K_new[0, 0]), float(K_new[1, 1])
        cx, cy = float(K_new[0, 2]), float(K_new[1, 2])

        # Step 3: run the detector
        # Some backends accept camera_params for in-detector pose estimation;
        # fall back to detection-only if those kwargs are not supported.
        dets = []
        pose_from_detector = False
        try:
            dets = self.det.detect(
                gray,
                estimate_tag_pose=True,
                camera_params=(fx, fy, cx, cy),
                tag_size=float(self.tag_size),
            )
            pose_from_detector = True  # detector returned pose_R / pose_t
        except TypeError:
            # Backend does not accept pose estimation kwargs
            dets = self.det.detect(gray, estimate_tag_pose=False)
        except Exception:
            dets = []

        obs = TagObservation(t=t_now, visible=False, tag_id=self.tag_id)

        # Step 4: search detections for our target tag ID
        for d in dets:
            if int(d.tag_id) != int(self.tag_id):
                continue  # skip tags we are not interested in

            corners = np.asarray(d.corners, dtype=np.float64).reshape(4, 2)
            center = np.asarray(d.center, dtype=np.float64).reshape(2)

            # Prefer the pose provided directly by the detector (lower latency);
            # fall back to our own solvePnP call if it is unavailable or invalid.
            T_cam_tag = None
            if (pose_from_detector and
                hasattr(d, "pose_R") and d.pose_R is not None and
                hasattr(d, "pose_t") and d.pose_t is not None):
                try:
                    T_cam_tag = T_from_R_t(np.asarray(d.pose_R), np.asarray(d.pose_t))
                except Exception:
                    T_cam_tag = None  # malformed detector output — try solvePnP below

            if T_cam_tag is None:
                # Compute pose ourselves using the four detected corner pixels
                pose = tag_pose_from_corners(corners, K_new, float(self.tag_size))
                if pose is None:
                    continue  # solvePnP failed — skip this detection
                rvec, tvec = pose
                T_cam_tag = T_from_rvec_tvec(rvec, tvec)

            # Populate the observation with the successful detection
            obs.visible = True
            obs.T_cam_tag = T_cam_tag
            obs.corners_px = corners
            obs.center_px = center

            # Step 5 (optional): draw tag overlay on a copy of the undistorted image
            if want_debug:
                dbg = img_und.copy()
                c = center.astype(int)
                # Draw a filled circle at the tag centre
                cv2.circle(dbg, (c[0], c[1]), 6, (0, 255, 0), -1)
                # Draw the four edges of the tag outline
                for k in range(4):
                    p0 = tuple(corners[k % 4].astype(int))
                    p1 = tuple(corners[(k + 1) % 4].astype(int))
                    cv2.line(dbg, p0, p1, (0, 255, 0), 2)
                # Label with the tag ID
                cv2.putText(
                    dbg, f"tag {d.tag_id}",
                    (c[0] + 10, c[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
                )
                obs.debug_img = dbg
            break  # stop after finding the first matching tag

        return obs, K_new