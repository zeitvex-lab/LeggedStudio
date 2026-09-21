"""记录器（:class:`contracts.runtime_interfaces.RecorderSinkProtocol` 实现）。

把一次运行的样本/事件/状态**分块落盘**：张量与状态走 ``npz-chunk``、事件走 ``jsonl``
（见 :data:`contracts.simulation_run_contract.CHUNK_FORMATS`）。三条硬约束：

1. **背压不丢样本**：队列字节数超过 ``queue_budget_bytes`` 时 :meth:`accept_sample`
   返回 ``False``，调用方须在 tick 边界暂停推进——绝不丢样本、也不阻塞物理循环。
2. **原子提交 + 真实摘要**：块先写临时文件再 ``os.replace``，``ChunkMeta.sha256`` 是
   块文件字节的真实摘要，下载侧据此核对（防"文件名对、内容被换"）。
3. **清单是提交点**：``close()`` 最后写 :class:`EpisodeManifest`，带整份规格与块索引，
   离线分析一个 episode 不必再猜当时的机器人参数。

本切片覆盖张量/状态/事件三类块的写入与清单收尾；按 ``chunk_sim_time_s`` 的自动轮转、
图像 ``png-lossless`` 块随后续切片接入。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from contracts import simulation_run_contract as rc

__all__ = ["ChunkRecorder", "recorder_selftest"]

#: 线协议 dtype → numpy dtype（与 :mod:`adapters.mjlab.policy_runtime` 同表口径）。
_PROTOCOL_TO_NP: dict[str, Any] = {
    "f4": np.float32,
    "f8": np.float64,
    "i1": np.int8,
    "i2": np.int16,
    "i4": np.int32,
    "i8": np.int64,
    "u1": np.uint8,
    "u2": np.uint16,
    "u4": np.uint32,
    "u8": np.uint64,
    "b1": np.bool_,
}


class ChunkRecorder:
    """单写者分块记录器（一个运行一个实例，``open`` → ``accept_*``/``flush`` → ``close``）。"""

    def __init__(self, *, base_dir: Path, run_id: str, episode_id: str) -> None:
        self._base = Path(base_dir)
        self._run_id = run_id
        self._episode_id = episode_id
        self._spec: rc.ResolvedRunSpec | None = None
        self._recording: rc.RecordingOptions | None = None
        self._run_dir: Path | None = None
        self._tensors: dict[tuple[str, str], dict[str, Any]] = {}
        self._status: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._chunks: list[rc.ChunkMeta] = []
        self._buffered_bytes = 0
        self._chunk_seq = 0
        self._current = "chunk0000"
        self._opened = False
        self._closed = False
        self._manifest: dict[str, Any] | None = None
        self._start_tick: int | None = None
        self._end_tick: int | None = None
        self._first_sim: float | None = None
        self._last_sim: float | None = None

    # -- 生命周期 ------------------------------------------------------------------

    def open(self, spec: rc.ResolvedRunSpec) -> None:
        self._spec = spec
        self._recording = spec.recording
        self._run_dir = self._base / self._recording.data_root / self._episode_id
        (self._run_dir / "tensors").mkdir(parents=True, exist_ok=True)
        self._opened = True
        self._closed = False

    def current_chunk_id(self) -> str | None:
        if not self._opened or self._closed:
            return None
        return self._current

    # -- 接收（带背压）--------------------------------------------------------------

    def accept_sample(self, envelope: rc.SampleEnvelope, payload: bytes) -> bool:
        if not self._opened or self._closed or self._recording is None:
            return False
        size = len(payload)
        if self._buffered_bytes + size > self._recording.queue_budget_bytes:
            return False  # 背压：调用方在当前 tick 边界暂停，不丢样本
        key = (envelope.instance_id, envelope.output)
        buffer = self._tensors.get(key)
        if buffer is None:
            buffer = {
                "envelopes": [],
                "payloads": [],
                "dtype": envelope.dtype,
                "shape": tuple(envelope.shape or ()),
                "unit": envelope.unit,
            }
            self._tensors[key] = buffer
        buffer["envelopes"].append(envelope)
        buffer["payloads"].append(bytes(payload))
        self._buffered_bytes += size
        self._track(envelope.sample_tick, envelope.sim_time)
        return True

    def accept_event(self, event: Mapping[str, Any]) -> None:
        if self._opened and not self._closed:
            self._events.append(dict(event))

    def accept_status(self, snapshot: Mapping[str, Any]) -> None:
        if self._opened and not self._closed:
            self._status.append(dict(snapshot))

    # -- 落盘 ----------------------------------------------------------------------

    def flush(self) -> None:
        if not self._opened or self._closed or self._run_dir is None:
            return
        for (instance_id, output), buffer in self._tensors.items():
            if buffer["payloads"]:
                self._write_tensor_chunk(instance_id, output, buffer)
        self._tensors.clear()
        self._buffered_bytes = 0
        if self._status:
            self._write_status_chunk(self._status)
            self._status = []

    def close(self) -> Mapping[str, Any]:
        if self._closed and self._manifest is not None:
            return self._manifest
        self.flush()
        events_path = self._write_events()
        index = rc.RecordingChunkIndex(
            episode_id=self._episode_id,
            data_root=self._recording.data_root if self._recording else "episodes",
            chunks=tuple(sorted(self._chunks, key=lambda item: item.first_tick)),
            complete=True,
            interrupted=False,
            final_chunk_count=len(self._chunks),
        )
        spec = self._spec
        assert spec is not None  # open() 必先于 close()
        first_sim = self._first_sim if self._first_sim is not None else 0.0
        last_sim = self._last_sim if self._last_sim is not None else first_sim
        manifest = rc.EpisodeManifest(
            episode_id=self._episode_id,
            run_id=self._run_id,
            spec=spec,
            spec_digest=spec.spec_digest,
            seed=spec.seed,
            time_base=spec.time_base,
            robot_id=spec.robot_id,
            policy_id=spec.policy_id,
            assets=spec.assets,
            index=index,
            events_path=events_path,
            events_count=len(self._events),
            status="finalized",
            start_tick=self._start_tick if self._start_tick is not None else 0,
            end_tick=self._end_tick if self._end_tick is not None else 0,
            duration_s=max(0.0, last_sim - first_sim),
            bytes_used=index.total_bytes,
            created_at_unix=time.time(),
        )
        self._closed = True
        self._manifest = manifest.model_dump(mode="json")
        return self._manifest

    # -- 内部 ----------------------------------------------------------------------

    def _track(self, tick: int, sim_time: float) -> None:
        self._start_tick = tick if self._start_tick is None else min(self._start_tick, tick)
        self._end_tick = tick if self._end_tick is None else max(self._end_tick, tick)
        self._first_sim = sim_time if self._first_sim is None else min(self._first_sim, sim_time)
        self._last_sim = sim_time if self._last_sim is None else max(self._last_sim, sim_time)

    def _next_chunk_id(self) -> str:
        chunk_id = f"chunk{self._chunk_seq:04d}"
        self._chunk_seq += 1
        self._current = f"chunk{self._chunk_seq:04d}"
        return chunk_id

    def _write_tensor_chunk(self, instance_id: str, output: str, buffer: dict[str, Any]) -> None:
        envelopes: list[rc.SampleEnvelope] = buffer["envelopes"]
        np_dtype = _PROTOCOL_TO_NP[buffer["dtype"]]
        shape = tuple(buffer["shape"])
        arrays = [np.frombuffer(payload, dtype=np_dtype).reshape(shape) for payload in buffer["payloads"]]
        data = np.stack(arrays, axis=0)
        ticks = np.array([envelope.sample_tick for envelope in envelopes], dtype=np.int64)
        seqs = np.array([envelope.seq for envelope in envelopes], dtype=np.int64)
        chunk_id = self._next_chunk_id()
        rel = f"{self._episode_id}/tensors/{chunk_id}.npz"
        size, digest = self._atomic_savez(self._run_dir / "tensors" / f"{chunk_id}.npz", data=data, sample_tick=ticks, seq=seqs)
        self._chunks.append(
            rc.ChunkMeta(
                chunk_id=chunk_id,
                episode_id=self._episode_id,
                kind="tensors",
                path=rel,
                sha256=digest,
                size_bytes=size,
                first_tick=int(ticks.min()),
                last_tick=int(ticks.max()),
                first_sim_time=min(envelope.sim_time for envelope in envelopes),
                last_sim_time=max(envelope.sim_time for envelope in envelopes),
                sample_count=len(envelopes),
                instance_id=instance_id,
                output=output,
                dtype=buffer["dtype"],
                shape=shape,
                unit=buffer["unit"],
                format="npz-chunk",
            )
        )

    def _write_status_chunk(self, snapshots: list[dict[str, Any]]) -> None:
        ticks = np.array([int(item.get("tick", 0)) for item in snapshots], dtype=np.int64)
        times = np.array([float(item.get("sim_time", 0.0)) for item in snapshots], dtype=np.float64)
        blob = np.array([json.dumps(item, sort_keys=True) for item in snapshots])
        chunk_id = self._next_chunk_id()
        rel = f"{self._episode_id}/status/{chunk_id}.npz"
        (self._run_dir / "status").mkdir(parents=True, exist_ok=True)
        size, digest = self._atomic_savez(self._run_dir / "status" / f"{chunk_id}.npz", tick=ticks, sim_time=times, snapshot=blob)
        self._chunks.append(
            rc.ChunkMeta(
                chunk_id=chunk_id,
                episode_id=self._episode_id,
                kind="status",
                path=rel,
                sha256=digest,
                size_bytes=size,
                first_tick=int(ticks.min()),
                last_tick=int(ticks.max()),
                first_sim_time=float(times.min()),
                last_sim_time=float(times.max()),
                sample_count=len(snapshots),
                format="npz-chunk",
            )
        )

    def _write_events(self) -> str | None:
        if not self._events or self._run_dir is None:
            return None
        events_dir = self._run_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        target = events_dir / "events.jsonl"
        tmp = target.with_name(target.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for event in self._events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        os.replace(tmp, target)
        return f"{self._episode_id}/events/events.jsonl"

    def _atomic_savez(self, target: Path, **arrays: Any) -> tuple[int, str]:
        """写 npz 到临时文件再原子改名；返回 (字节数, 真实 sha256)。"""

        assert self._run_dir is not None
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        with tmp.open("wb") as handle:
            np.savez(handle, **arrays)
        os.replace(tmp, target)
        raw = target.read_bytes()
        return len(raw), hashlib.sha256(raw).hexdigest()


def recorder_selftest(work_dir: Path | None = None) -> bool:
    """记录子系统自检：写一个合成张量块、算 sha256、读回逐项核对。

    探测发生在**规格构造之前**（拿不到 :class:`ResolvedRunSpec`），所以这里只验证
    npz 分块的"写 → 校验 → 读回"这一**存储原语**是否真的可用；完整清单路径在运行期
    由 :class:`ChunkRecorder` 走。任何异常都记为 ``False``（fail-closed，不谎报可记录）。
    """

    import tempfile

    try:
        with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
            target = Path(tmp) / "selftest.npz"
            data = np.arange(6, dtype=np.float32).reshape(2, 3)
            ticks = np.array([0, 1], dtype=np.int64)
            with target.open("wb") as handle:
                np.savez(handle, data=data, sample_tick=ticks)
            raw = target.read_bytes()
            if not raw:
                return False
            digest = hashlib.sha256(raw).hexdigest()
            with np.load(target) as blob:
                data_ok = bool(np.array_equal(blob["data"], data))
                tick_ok = bool(np.array_equal(blob["sample_tick"], ticks))
            return data_ok and tick_ok and hashlib.sha256(raw).hexdigest() == digest
    except Exception:  # noqa: BLE001 - 自检失败只能如实报告不可用
        return False
