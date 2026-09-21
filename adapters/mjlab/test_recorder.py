"""ChunkRecorder（RecorderSinkProtocol 实现）的单元测试。

真落盘：npz 块写进临时目录、算真实 sha256、原子提交；close() 产出能通过
:class:`contracts.simulation_run_contract.EpisodeManifest` 校验的清单。背压按
``queue_budget_bytes`` 在 tick 边界返回 False（不丢样本、不阻塞）。
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from contracts import simulation_run_contract as rc
from contracts.tests.test_simulation_run_contract import _spec

from .recorder import ChunkRecorder


def _tensor_sample(
    *,
    run_id: str,
    instance_id: str,
    output: str,
    tick: int,
    sim_time: float,
    data,
    seq: int = 0,
    unit: str = "m/s^2",
):
    array = np.ascontiguousarray(np.asarray(data, dtype=np.float32))
    payload = array.tobytes()
    envelope = rc.SampleEnvelope(
        run_id=run_id,
        epoch=0,
        seq=seq,
        instance_id=instance_id,
        plugin_id="imu",
        plugin_version="1.0.0",
        output=output,
        sample_tick=tick,
        available_tick=tick,
        sim_time=sim_time,
        shape=tuple(int(dim) for dim in array.shape),
        dtype="f4",
        unit=unit,
        payload_kind="tensor",
        payload_bytes=len(payload),
        checksum=hashlib.sha256(payload).hexdigest(),
    )
    return envelope, payload


class ChunkRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _recorder(self, spec: rc.ResolvedRunSpec) -> ChunkRecorder:
        recorder = ChunkRecorder(base_dir=self.base, run_id="run1", episode_id="ep1")
        recorder.open(spec)
        return recorder

    def test_open_creates_run_directory_under_data_root(self) -> None:
        recorder = self._recorder(_spec())

        run_dir = self.base / "episodes" / "ep1"
        self.assertTrue(run_dir.is_dir())
        self.assertIsNotNone(recorder.current_chunk_id())

    def test_flush_writes_npz_chunk_with_real_sha256_that_roundtrips(self) -> None:
        recorder = self._recorder(_spec())
        data = [[1.0, 2.0, 3.0]]
        envelope, payload = _tensor_sample(
            run_id="run1", instance_id="imu0", output="accel", tick=0, sim_time=0.0, data=data
        )
        self.assertTrue(recorder.accept_sample(envelope, payload))

        recorder.flush()
        manifest = recorder.close()

        chunk = manifest["index"]["chunks"][0]
        chunk_file = self.base / "episodes" / chunk["path"]
        self.assertTrue(chunk_file.is_file())
        # sha256 是块文件字节的真实摘要。
        self.assertEqual(chunk["sha256"], hashlib.sha256(chunk_file.read_bytes()).hexdigest())
        self.assertEqual(chunk["size_bytes"], chunk_file.stat().st_size)
        with np.load(chunk_file) as blob:
            self.assertEqual(blob["data"].tolist(), [data])
            self.assertEqual(blob["sample_tick"].tolist(), [0])

    def test_close_returns_manifest_that_satisfies_the_contract(self) -> None:
        recorder = self._recorder(_spec())
        envelope, payload = _tensor_sample(
            run_id="run1", instance_id="imu0", output="accel", tick=5, sim_time=0.01, data=[[0.0, 0.0, 9.8]]
        )
        recorder.accept_sample(envelope, payload)
        recorder.flush()

        manifest = recorder.close()
        parsed = rc.EpisodeManifest.model_validate(manifest)

        self.assertEqual(parsed.episode_id, "ep1")
        self.assertEqual(parsed.run_id, "run1")
        self.assertEqual(parsed.status, "finalized")
        self.assertTrue(parsed.index.complete)
        self.assertEqual(parsed.index.final_chunk_count, len(parsed.index.chunks))
        self.assertEqual(parsed.start_tick, 5)
        self.assertEqual(parsed.end_tick, 5)

    def test_backpressure_returns_false_at_the_queue_budget_boundary(self) -> None:
        recording = rc.RecordingOptions(
            queue_budget_bytes=24,
            per_run_budget_bytes=1 << 20,
            directory_budget_bytes=1 << 20,
            min_free_disk_bytes=0,
        )
        recorder = self._recorder(_spec(recording=recording))
        # 每个样本 3×f4 = 12 字节；第三个会超过 24 字节队列预算。
        first, first_payload = _tensor_sample(
            run_id="run1", instance_id="imu0", output="accel", tick=0, sim_time=0.0, data=[[1.0, 2.0, 3.0]]
        )
        self.assertTrue(recorder.accept_sample(first, first_payload))
        second, second_payload = _tensor_sample(
            run_id="run1", instance_id="imu0", output="accel", tick=1, sim_time=0.002, data=[[1.0, 2.0, 3.0]], seq=1
        )
        self.assertTrue(recorder.accept_sample(second, second_payload))
        third, third_payload = _tensor_sample(
            run_id="run1", instance_id="imu0", output="accel", tick=2, sim_time=0.004, data=[[1.0, 2.0, 3.0]], seq=2
        )
        self.assertFalse(recorder.accept_sample(third, third_payload))
        # flush 清空队列后即可继续接收（背压是暂停，不是丢样本）。
        recorder.flush()
        self.assertTrue(recorder.accept_sample(third, third_payload))

    def test_events_and_status_are_recorded_in_the_manifest(self) -> None:
        recorder = self._recorder(_spec())
        envelope, payload = _tensor_sample(
            run_id="run1", instance_id="imu0", output="accel", tick=0, sim_time=0.0, data=[[1.0, 2.0, 3.0]]
        )
        recorder.accept_sample(envelope, payload)
        recorder.accept_event({"tick": 0, "sim_time": 0.0, "type": "reset", "epoch": 0})
        recorder.accept_status({"tick": 0, "sim_time": 0.0, "status": "running"})
        recorder.flush()

        manifest = recorder.close()
        kinds = {chunk["kind"] for chunk in manifest["index"]["chunks"]}
        self.assertIn("tensors", kinds)
        self.assertIn("status", kinds)
        self.assertEqual(manifest["events_count"], 1)
        events_path = self.base / "episodes" / manifest["events_path"]
        self.assertEqual(json.loads(events_path.read_text(encoding="utf-8").strip())["type"], "reset")


if __name__ == "__main__":
    unittest.main()
