"""H18：Episode 记录 schema + 轨迹回放（"预测 vs 实际"叠加）。

## 依据

字段清单取自 `00_resources/LightNav-0/docs/VISUALIZATION.md`（Recording layout and record schema）：

```
<record_dir>/run_<YYYYmmdd_HHMMSS>/<conn>/episode_NNN/
    manifest.json     # 本次运行的参数（每集一份）
    actions.jsonl     # 每一步一条，**边跑边 append+flush**
    actions.json      # 同一批记录，收尾时写成 JSON 数组
```

**为什么是 jsonl 边写边 flush**（而不是收尾一次性写）：Episode 是"跑到一半崩了也算数"的数据 ——
机器人一次导航可能中途断电/断连，jsonl 让**崩前的每一步都还在**。所以本模块的 `record()`
必须 flush，`read_episode()` 必须**容忍最后一行被截断**（宁可丢半步，不能整集读不出）。

## "forward-offset ≈0.6 m"这个坑

模型输出的航点是在**机体**坐标系（前/侧/偏航），而叠加到画面上时，"预测轨迹"的起点不是机体原点，
而是**相机/ego 原点** —— 两者差一个 `overlay_forward_offset`（真机上约 0.6 m）。
不做这个偏移，预测与实际的轨迹会**整体错开约 0.6 m**，看起来像"控制器有稳态误差"，
实际是画错了。这里把它做成必须显式传入的参数（默认 `None` = 未标定，如实告诉调用方"没标定就别假装准"）。
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

#: schema 版本（进 manifest.schema；将来字段变更必须升它，读侧据此决定兼容策略）
EPISODE_SCHEMA_VERSION = 1

#: manifest.json 必备键（顺序与 LightNav 文档一致）
MANIFEST_FIELDS: tuple[str, ...] = (
    "schema", "created_at", "conn", "episode", "task", "model_path",
    "video_fps", "video_timeline", "waypoint_dt_s",
    "overlay_hfov_deg", "overlay_cam_height", "overlay_forward_offset",
    "frame_size", "instruction", "extra",
)

#: 每步 record 必备键
RECORD_FIELDS: tuple[str, ...] = (
    "step", "seq", "received_at", "step_dt_ms", "step_fps", "instruction",
    "waypoints", "stop", "visible", "raw_text", "latency_ms", "pointing", "frame_size",
)


def _utc_now_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _coerce_point(value: Any) -> tuple[float, float] | None:
    """把任意输入收敛成有限二元点；不是有限数就返回 None（**不猜、不填零**）。"""

    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return x, y


class EpisodeRecorder:
    """一次 episode 的记录器（上下文管理器；异常退出也会尽力收尾）。"""

    def __init__(
        self,
        record_root: str | os.PathLike[str],
        *,
        conn: str,
        episode: int,
        task: str = "navigation",
        model_path: str | None = None,
        instruction: str | None = None,
        frame_size: Iterable[int] | None = (480, 270),
        video_fps: float = 10,
        video_timeline: str = "realtime",
        waypoint_dt_s: float = 0.1,
        overlay_hfov_deg: float = 90.0,
        overlay_cam_height: float = 0.5,
        overlay_forward_offset: float | None = None,
        extra: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> None:
        self.run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.root = Path(record_root) / self.run_id / str(conn) / f"episode_{int(episode):03d}"
        size = tuple(int(v) for v in (frame_size or ())) if frame_size else None
        self.manifest: dict[str, Any] = {
            "schema": EPISODE_SCHEMA_VERSION,
            "created_at": _utc_now_iso_ms(),
            "conn": str(conn),
            "episode": int(episode),
            "task": task,
            "model_path": model_path,
            "video_fps": video_fps,
            "video_timeline": video_timeline,
            "waypoint_dt_s": waypoint_dt_s,
            "overlay_hfov_deg": overlay_hfov_deg,
            "overlay_cam_height": overlay_cam_height,
            "overlay_forward_offset": overlay_forward_offset,
            "frame_size": list(size) if size else None,
            "instruction": instruction,
            "extra": dict(extra or {}),
        }
        self.records: list[dict[str, Any]] = []
        self._stream = None
        self._jsonl_path = self.root / "actions.jsonl"
        self._closed = False

    # ---- 生命周期 ----

    def open(self) -> "EpisodeRecorder":
        self.root.mkdir(parents=True, exist_ok=True)
        # manifest 先落盘：万一中途崩，至少知道"这一集本来打算跑什么"
        _atomic_write_json(self.root / "manifest.json", self.manifest)
        self._stream = open(self._jsonl_path, "a", encoding="utf-8")
        return self

    def record(self, **fields: Any) -> dict[str, Any]:
        """记一步。**边写边 flush**：崩前的每一步都还在盘上。"""

        if self._stream is None:
            raise RuntimeError("EpisodeRecorder 未 open()")
        step = int(fields.get("step", len(self.records)))
        received_at = fields.get("received_at") or _utc_now_iso_ms()
        step_dt_ms = fields.get("step_dt_ms")
        if step_dt_ms is None:
            step_dt_ms = 0.0 if step == 0 else self._elapsed_ms_since_previous()
        step_fps = fields.get("step_fps")
        if step_fps is None:
            step_fps = (1000.0 / step_dt_ms) if step_dt_ms and step_dt_ms > 0 else None
        record = {
            "step": step,
            "seq": int(fields.get("seq", step)),
            "received_at": received_at,
            "step_dt_ms": float(step_dt_ms),
            "step_fps": step_fps,
            "instruction": fields.get("instruction", self.manifest["instruction"]),
            "waypoints": fields.get("waypoints"),
            "stop": bool(fields.get("stop", False)),
            "visible": fields.get("visible"),
            "raw_text": fields.get("raw_text"),
            "latency_ms": fields.get("latency_ms"),
            "pointing": fields.get("pointing"),
            "frame_size": fields.get("frame_size", self.manifest["frame_size"]),
        }
        record.update({key: value for key, value in fields.items() if key not in record})
        self._stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self.records.append(record)
        self._last_wall_clock = time.monotonic()
        return record

    def close(self) -> Path:
        """收尾：写 actions.json（数组形式，便于人直接看/喂给别的工具）。"""

        if self._closed:
            return self.root
        self._closed = True
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        _atomic_write_json(self._jsonl_path.with_name("actions.json"), self.records)
        return self.root

    def __enter__(self) -> "EpisodeRecorder":
        return self.open()

    def __exit__(self, *_exc: object) -> bool:
        self.close()
        return False  # 不吞异常

    # ---- 内部 ----

    def _elapsed_ms_since_previous(self) -> float:
        previous = getattr(self, "_last_wall_clock", None)
        return round((time.monotonic() - previous) * 1000.0, 3) if previous else 0.0


def _atomic_write_json(path: Path, payload: Any) -> None:
    """先写 .tmp 再 replace：避免"写了一半的 manifest"被当成好数据读走。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_episode(episode_dir: str | os.PathLike[str]) -> dict[str, Any]:
    """读一集。**容忍最后一行被截断**（崩在半步上的 jsonl 仍然可用）。"""

    directory = Path(episode_dir)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"缺 manifest.json：{directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    jsonl_path = directory / "actions.jsonl"
    records: list[dict[str, Any]] = []
    truncated = 0
    if jsonl_path.is_file():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                truncated += 1  # 崩在半行上：丢掉这半步，不丢整集
    return {
        "manifest": manifest,
        "records": records,
        "truncated_records": truncated,
        "dir": str(directory),
    }


def list_episodes(record_root: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """列出所有 episode（供 /api/episode/list）。读不动的那集**跳过但不隐藏**问题。"""

    root = Path(record_root)
    if not root.is_dir():
        return []
    episodes: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("run_*/*/episode_*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        directory = manifest_path.parent
        jsonl = directory / "actions.jsonl"
        steps = 0
        if jsonl.is_file():
            steps = sum(1 for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip())
        episodes.append({
            "run": directory.parent.parent.name,
            "conn": directory.parent.name,
            "episode": manifest.get("episode"),
            "task": manifest.get("task"),
            "created_at": manifest.get("created_at"),
            "instruction": manifest.get("instruction"),
            "steps": steps,
            "dir": str(directory),
        })
    return episodes


# ---- 叠加用的投影（H18 的"预测 vs 实际"） ----

def ground_point_from_waypoint(
    waypoint: Iterable[float] | None,
    *,
    forward_offset: float | None = None,
) -> tuple[float, float] | None:
    """把机体坐标系航点 `[forward_m, lateral_m, yaw_rad]` 投到地面（机体坐标系）。

    **forward_offset 就是那个 0.6 m 的坑**：它不为 None 时，预测点的前向距离要加上它，
    否则预测轨迹与实测轨迹会整体错开一个固定距离（看起来像控制误差，其实是画错了）。
    """

    point = _coerce_point(list(waypoint or [])[:2] if waypoint is not None else None)
    if point is None:
        return None
    forward, lateral = point
    offset = 0.0 if forward_offset is None else float(forward_offset)
    return forward + offset, lateral


def pixel_to_ground(
    pixel: Iterable[float],
    *,
    hfov_deg: float,
    cam_height: float,
    frame_size: Iterable[int],
    forward_offset: float = 0.0,
) -> tuple[float, float] | None:
    """针孔模型：画面像素 → 地面点（机体坐标系，米）。返回 None = 射线朝上/贴地平线（永不相交）。

    相机在高度 `cam_height`、俯角 0（光轴水平）；水平视场 `hfov_deg`。正方形像素 ⇒ `fy = fx`。
    """

    point = _coerce_point(pixel)
    frame = _coerce_point(list(frame_size or [])[:2] if frame_size is not None else None)
    if point is None or frame is None or cam_height <= 0 or not (0 < hfov_deg < 180):
        return None
    px, py = point
    width, height = frame
    fx = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    cy = height / 2.0
    # 光轴水平 ⇒ 画面中央那行是"地平线"，越往下越近
    below = py - cy
    if below <= 1e-9:
        return None
    forward = cam_height * fx / below
    lateral = (px - width / 2.0) * forward / fx
    return forward + float(forward_offset), lateral


def ground_to_pixel(
    ground_point: Iterable[float],
    *,
    hfov_deg: float,
    cam_height: float,
    frame_size: Iterable[int],
    forward_offset: float = 0.0,
) -> tuple[float, float] | None:
    """`pixel_to_ground` 的逆（用于自证：投出去再投回来应当回到原处）。"""

    point = _coerce_point(ground_point)
    frame = _coerce_point(list(frame_size or [])[:2] if frame_size is not None else None)
    if point is None or frame is None or cam_height <= 0 or not (0 < hfov_deg < 180):
        return None
    forward, lateral = point
    forward -= float(forward_offset)
    if forward <= 1e-9:
        return None
    width, height = frame
    fx = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    below = cam_height * fx / forward
    return width / 2.0 + lateral * fx / forward, height / 2.0 + below


def build_overlay(manifest: dict[str, Any], records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """把一集记录整理成"预测 vs 实际"两条轨迹（世界/机体米，供前端 canvas 叠加）。

    * **预测**：每步模型给出的航点（取该步航点的**末端**作为那一步的落点）；
    * **实际**：实测位姿（`pointing.actual` 或 record 里的 `actual_position`），没有就不编；
    * 解码失败（`waypoints: null`）的步**跳过**，并如实计入 `skipped_steps`。
    """

    forward_offset = manifest.get("overlay_forward_offset")
    predicted: list[list[float]] = []
    actual: list[list[float]] = []
    skipped = 0
    for record in records:
        waypoints = record.get("waypoints")
        if not waypoints:
            skipped += 1
        else:
            last = waypoints[-1] if isinstance(waypoints, (list, tuple)) and waypoints else None
            point = ground_point_from_waypoint(last, forward_offset=forward_offset)
            if point is None:
                skipped += 1
            else:
                predicted.append([round(point[0], 6), round(point[1], 6)])
        position = (record.get("pointing") or {}).get("actual") if isinstance(record.get("pointing"), dict) else None
        position = position or record.get("actual_position")
        point = _coerce_point(position)
        if point is not None:
            actual.append([round(point[0], 6), round(point[1], 6)])
    return {
        "predicted": predicted,
        "actual": actual,
        "skipped_steps": skipped,
        "forward_offset": forward_offset,
        # 未标定时明说：没标定就别假装准
        "offset_calibrated": forward_offset is not None,
    }
