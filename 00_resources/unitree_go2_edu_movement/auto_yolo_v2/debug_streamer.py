#!/usr/bin/env python3
"""
debug_streamer.py
=================
Low-latency RTP/H.264 debug video streamer.

Decoupled from robot control:
  - Main/control threads call publish(frame) — non-blocking, drops old frames.
  - Resize → encode → network send happen in a background thread.

Configuration via environment variables
----------------------------------------
  GO2_DEBUG_STREAM_HOST     Host IP of your PC (required to enable streaming).
  GO2_DEBUG_STREAM_PORT     UDP port (default 5600).
  GO2_DEBUG_STREAM_FPS      Encode FPS (default 8).
  GO2_DEBUG_STREAM_WIDTH    Output width in pixels (default 960).
  GO2_DEBUG_STREAM_BITRATE  H.264 bitrate string (default "1500k").
  GO2_DEBUG_STREAM_SDP_PATH Path where ffmpeg writes the SDP file.

Receive on the host PC with:
  ffplay -protocol_whitelist file,rtp,udp -i /path/to/debug_rtp_5600.sdp
  or:
  ffplay rtp://<robot-ip>:5600
"""

import os
import subprocess
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _make_even(v: int) -> int:
    return max(2, int(v) - (int(v) % 2))


class DebugRtpStreamer:
    """
    Streams the latest debug frame to a remote host via RTP/H.264.

    publish() is safe to call from any thread at any rate.  Frames are
    dropped rather than buffered so the pipeline is never blocked.
    """

    def __init__(
        self,
        host: str,
        port: int = 5600,
        fps: float = 8.0,
        width: int = 960,
        bitrate: str = "1500k",
        sdp_path: Optional[str] = None,
        logger=None,
    ):
        self.host     = str(host).strip()
        self.port     = int(port)
        self.fps      = max(1.0, float(fps))
        self.width    = max(160, int(width))
        self.bitrate  = str(bitrate).strip() or "1500k"
        self.sdp_path = sdp_path
        self.logger   = logger
        self.enabled  = bool(self.host)

        self._lock   = threading.Lock()
        self._cv     = threading.Condition(self._lock)
        self._latest_frame: Optional[np.ndarray] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._out_wh: Optional[Tuple[int, int]] = None
        self._sdp_logged = False

    @classmethod
    def from_env(cls, log_dir: str, logger=None) -> "DebugRtpStreamer":
        """Construct from GO2_DEBUG_STREAM_* environment variables."""
        host     = os.environ.get("GO2_DEBUG_STREAM_HOST", "").strip()
        port     = int(os.environ.get("GO2_DEBUG_STREAM_PORT", "5600"))
        fps      = float(os.environ.get("GO2_DEBUG_STREAM_FPS", "8"))
        width    = int(os.environ.get("GO2_DEBUG_STREAM_WIDTH", "960"))
        bitrate  = os.environ.get("GO2_DEBUG_STREAM_BITRATE", "1500k")
        sdp_path = os.environ.get(
            "GO2_DEBUG_STREAM_SDP_PATH",
            os.path.join(log_dir, f"debug_rtp_{port}.sdp"),
        )
        return cls(host=host, port=port, fps=fps, width=width,
                   bitrate=bitrate, sdp_path=sdp_path, logger=logger)

    def start(self) -> None:
        if not self.enabled or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="rtp-stream")
        self._thread.start()
        self._log(
            f"RTP streamer → {self.host}:{self.port}  "
            f"fps={self.fps:.1f}  width={self.width}  bitrate={self.bitrate}"
        )

    def stop(self) -> None:
        if not self._running:
            self._close_proc()
            return
        self._running = False
        with self._cv:
            self._cv.notify_all()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._close_proc()

    def publish(self, frame_bgr: Optional[np.ndarray]) -> None:
        """Non-blocking: store the latest frame for the background thread."""
        if not self.enabled or not self._running or frame_bgr is None:
            return
        with self._cv:
            self._latest_frame = frame_bgr
            self._cv.notify()

    # ── Background encode/send loop ───────────────────────────────────────────

    def _loop(self) -> None:
        send_dt    = 1.0 / self.fps
        next_send  = 0.0

        while self._running:
            with self._cv:
                while self._running and self._latest_frame is None:
                    self._cv.wait(timeout=0.5)
                if not self._running:
                    break

                now    = time.time()
                wait_s = max(0.0, next_send - now)
                if wait_s > 0.0:
                    self._cv.wait(timeout=wait_s)
                    if not self._running:
                        break
                    now = time.time()

                frame = self._latest_frame
                self._latest_frame = None

            if frame is None:
                continue

            try:
                self._ensure_proc(frame)
                if self._proc is None or self._proc.stdin is None:
                    continue
                out = self._prepare_frame(frame)
                self._proc.stdin.write(out.tobytes())
                self._proc.stdin.flush()
                next_send = time.time() + send_dt
            except (BrokenPipeError, OSError):
                self._log("RTP pipe broke — restarting ffmpeg.", warn=True)
                self._close_proc()
                next_send = time.time() + send_dt

        self._close_proc()

    def _prepare_frame(self, frame: np.ndarray) -> np.ndarray:
        if self._out_wh is None:
            return frame
        out_w, out_h = self._out_wh
        h, w = frame.shape[:2]
        if (w, h) == (out_w, out_h):
            return frame
        return cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)

    def _ensure_proc(self, frame: np.ndarray) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return

        h, w   = frame.shape[:2]
        out_w  = _make_even(min(self.width, w))
        out_h  = _make_even(int(round(out_w * h / max(1, w))))
        self._out_wh = (out_w, out_h)

        if self.sdp_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.sdp_path)), exist_ok=True)
            try:
                os.remove(self.sdp_path)
            except FileNotFoundError:
                pass

        gop = max(1, int(round(self.fps)))
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats",
            "-fflags", "nobuffer",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s:v", f"{out_w}x{out_h}",
            "-r", f"{self.fps:.3f}",
            "-i", "-",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-x264-params", "repeat-headers=1",
            "-pix_fmt", "yuv420p",
            "-profile:v", "baseline",
            "-bf", "0",
            "-g", str(gop), "-keyint_min", str(gop),
            "-b:v", self.bitrate, "-maxrate", self.bitrate, "-bufsize", self.bitrate,
            "-flush_packets", "1",
            "-payload_type", "96",
        ]
        if self.sdp_path:
            cmd.extend(["-sdp_file", self.sdp_path])
        cmd.extend(["-f", "rtp", f"rtp://{self.host}:{self.port}?pkt_size=1200&reuse=1"])

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._log(f"ffmpeg started: {out_w}x{out_h} → rtp://{self.host}:{self.port}")

        if self.sdp_path and not self._sdp_logged:
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if os.path.exists(self.sdp_path) and os.path.getsize(self.sdp_path) > 0:
                    break
                time.sleep(0.05)
            if os.path.exists(self.sdp_path):
                self._log(f"SDP file: {self.sdp_path}")
                self._sdp_logged = True

    def _close_proc(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _log(self, msg: str, warn: bool = False) -> None:
        if self.logger is None:
            return
        if warn:
            self.logger.warning(msg)
        else:
            self.logger.info(msg)


def debug_window_enabled(default: bool = True) -> bool:
    return _env_bool("GO2_DEBUG_SHOW_WINDOW", default)
