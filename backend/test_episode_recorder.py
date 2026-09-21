"""H18：Episode 记录 schema + 轨迹回放契约。

守三件事：
1. **schema 齐**（manifest/record 的必备键一个不少，客户端不会拿到缺字段的数据）；
2. **崩了也算数**（jsonl 边写边 flush：不 close 就能读到已写步；末行被截断仍能读出整集）；
3. **0.6 m 的坑不许再踩**（forward_offset 必须真的挪动预测轨迹；未标定时如实说"没标定"）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.episode_recorder import (  # noqa: E402
    EPISODE_SCHEMA_VERSION,
    MANIFEST_FIELDS,
    RECORD_FIELDS,
    EpisodeRecorder,
    build_overlay,
    ground_point_from_waypoint,
    ground_to_pixel,
    list_episodes,
    pixel_to_ground,
    read_episode,
)


def _step(recorder: EpisodeRecorder, step: int, **fields):
    """写一步导航记录（合成数据：不依赖真仿真/真机器人）。"""

    payload = {
        "step": step,
        "waypoints": [[0.5, 0.0, 0.0], [1.5 + step * 0.1, 0.05, 0.0]],
        "pointing": {"actual": [1.4 + step * 0.1, -0.02]},
        "instruction": "follow the man in the black shirt",
        "latency_ms": 12.5,
    }
    payload.update(fields)
    return recorder.record(**payload)


class EpisodeSchemaTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_manifest_and_record_have_all_schema_fields(self):
        with EpisodeRecorder(self.root, conn="robot-01", episode=0, overlay_forward_offset=0.6) as recorder:
            _step(recorder, 0)
            _step(recorder, 1)
            directory = recorder.root

        payload = read_episode(directory)
        manifest = payload["manifest"]
        self.assertEqual(manifest["schema"], EPISODE_SCHEMA_VERSION)
        for key in MANIFEST_FIELDS:
            self.assertIn(key, manifest, f"manifest 缺字段 {key}")
        for record in payload["records"]:
            for key in RECORD_FIELDS:
                self.assertIn(key, record, f"record 缺字段 {key}")

    def test_directory_layout_matches_documented_shape(self):
        """目录形态：run_<ts>/<conn>/episode_NNN/{manifest.json, actions.jsonl, actions.json}。"""

        with EpisodeRecorder(self.root, conn="conn001", episode=7) as recorder:
            _step(recorder, 0)
            directory = recorder.root
        self.assertRegex(directory.parent.parent.name, r"^run_\d{8}_\d{6}$")
        self.assertEqual(directory.parent.name, "conn001")
        self.assertEqual(directory.name, "episode_007")
        self.assertTrue((directory / "manifest.json").is_file())
        self.assertTrue((directory / "actions.jsonl").is_file())
        self.assertTrue((directory / "actions.json").is_file())

    def test_jsonl_is_readable_before_close(self):
        """**崩了也算数**：不 close（模拟断电）也能读到已写的步。"""

        recorder = EpisodeRecorder(self.root, conn="robot-01", episode=1).open()
        _step(recorder, 0)
        _step(recorder, 1)
        payload = read_episode(recorder.root)  # 还没 close
        self.assertEqual(len(payload["records"]), 2)
        self.assertEqual([item["step"] for item in payload["records"]], [0, 1])
        recorder.close()

    def test_truncated_last_line_does_not_lose_the_episode(self):
        """末行被截断（崩在半行）：丢掉那半步，**不丢整集**。"""

        with EpisodeRecorder(self.root, conn="robot-01", episode=2) as recorder:
            _step(recorder, 0)
            _step(recorder, 1)
            directory = recorder.root
        with open(directory / "actions.jsonl", "a", encoding="utf-8") as handle:
            handle.write('{"step": 2, "waypo')  # 半行

        payload = read_episode(directory)
        self.assertEqual(len(payload["records"]), 2)
        self.assertEqual(payload["truncated_records"], 1)

    def test_actions_json_mirrors_jsonl(self):
        with EpisodeRecorder(self.root, conn="robot-01", episode=3) as recorder:
            _step(recorder, 0)
            _step(recorder, 1)
            directory = recorder.root
        mirror = json.loads((directory / "actions.json").read_text(encoding="utf-8"))
        self.assertEqual(len(mirror), 2)
        self.assertEqual(mirror[1]["step"], 1)


class OverlayProjectionTest(unittest.TestCase):
    def test_forward_offset_actually_shifts_prediction(self):
        """**0.6 m 的坑**：不给偏移 vs 给偏移，预测落点必须差 0.6 m（否则等于没实现）。"""

        without = ground_point_from_waypoint([2.0, 0.1], forward_offset=None)
        with_offset = ground_point_from_waypoint([2.0, 0.1], forward_offset=0.6)
        self.assertEqual(without, (2.0, 0.1))
        self.assertEqual(with_offset, (2.6, 0.1))
        self.assertAlmostEqual(with_offset[0] - without[0], 0.6, places=9)
        self.assertAlmostEqual(with_offset[1], without[1], places=9, msg="偏移只该动前向，不该动侧向")

    def test_uncalibrated_offset_is_reported_honestly(self):
        overlay = build_overlay({"overlay_forward_offset": None}, [{"waypoints": [[1.0, 0.0, 0.0]]}])
        self.assertFalse(overlay["offset_calibrated"], "未标定必须如实报 False")

    def test_pinhole_projection_round_trips(self):
        """自证：地面点 → 像素 → 地面，必须回到原处（否则叠加是歪的）。"""

        for ground in ((2.0, -0.3), (5.0, 0.8), (1.5, 0.0)):
            pixel = ground_to_pixel(ground, hfov_deg=90.0, cam_height=0.5, frame_size=(480, 270))
            self.assertIsNotNone(pixel)
            back = pixel_to_ground(pixel, hfov_deg=90.0, cam_height=0.5, frame_size=(480, 270))
            self.assertAlmostEqual(back[0], ground[0], places=6)
            self.assertAlmostEqual(back[1], ground[1], places=6)

    def test_horizon_pixels_have_no_ground_intersection(self):
        """地平线及以上不落地：返回 None，**不能**编出一个巨大的距离。"""

        self.assertIsNone(pixel_to_ground((240, 135), hfov_deg=90.0, cam_height=0.5, frame_size=(480, 270)))
        self.assertIsNone(pixel_to_ground((240, 10), hfov_deg=90.0, cam_height=0.5, frame_size=(480, 270)))

    def test_failed_decode_is_skipped_not_faked(self):
        """解码失败（waypoints=None）的步跳过并计数，**不补零、不外推**。"""

        manifest = {"overlay_forward_offset": 0.0}
        records = [
            {"waypoints": [[1.0, 0.0, 0.0]], "pointing": {"actual": [0.9, 0.0]}},
            {"waypoints": None, "pointing": {"actual": [1.4, 0.1]}},
            {"waypoints": [[2.0, 0.0, 0.0]], "pointing": {"actual": [1.9, 0.0]}},
        ]
        overlay = build_overlay(manifest, records)
        self.assertEqual(len(overlay["predicted"]), 2, "失败步不该进预测轨迹")
        self.assertEqual(len(overlay["actual"]), 3, "实测步与解码成败无关")
        self.assertEqual(overlay["skipped_steps"], 1)
        self.assertTrue(overlay["offset_calibrated"])

    def test_actual_trail_works_without_pointing_payload(self):
        """没有 pointing 时用 actual_position；两者都没有就不编（不产生假轨迹）。"""

        overlay = build_overlay({}, [{"waypoints": None, "actual_position": [1.0, 2.0]}, {"waypoints": None}])
        self.assertEqual(overlay["actual"], [[1.0, 2.0]])
        self.assertEqual(overlay["predicted"], [])


class EpisodeListingTest(unittest.TestCase):
    def test_list_episodes_reports_steps_and_skips_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with EpisodeRecorder(root, conn="robot-01", episode=0) as recorder:
                _step(recorder, 0)
                _step(recorder, 1)
            with EpisodeRecorder(root, conn="robot-01", episode=1) as recorder:
                _step(recorder, 0)
            # 一集坏掉（manifest 是坏 JSON）：跳过，但不该让整个列表失败
            broken = root / "run_20260916_000000" / "robot-01" / "episode_002"
            broken.mkdir(parents=True)
            (broken / "manifest.json").write_text("{not json", encoding="utf-8")

            episodes = list_episodes(root)
            self.assertEqual(len(episodes), 2, "坏掉的那集被跳过，好集不许丢")
            self.assertEqual({item["steps"] for item in episodes}, {1, 2})
            self.assertTrue(all(item["conn"] == "robot-01" for item in episodes))

    def test_list_on_missing_root_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list_episodes(Path(tmp) / "nope"), [])


class EpisodeApiEndToEndTest(unittest.TestCase):
    """**真跑一遍回路**：记录器写盘 → HTTP 列表 → HTTP 详情 → 得到"预测 vs 实际"叠加。"""

    def _client(self, root: Path):
        os.environ["LEGGED_STUDIO_EPISODE_DIR"] = str(root)
        try:
            from fastapi.testclient import TestClient

            from backend.api_complete import app
        except Exception as error:  # pragma: no cover - 重依赖缺失时如实跳过
            self.skipTest(f"API 依赖不可用：{error}")
        return TestClient(app)

    def test_record_then_serve_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with EpisodeRecorder(root, conn="robot-01", episode=0, run_id="run_20260916_120000",
                                 instruction="follow the man in the black shirt",
                                 overlay_forward_offset=0.6) as recorder:
                _step(recorder, 0)
                _step(recorder, 1, waypoints=None)  # 一步解码失败：回路要能扛住
                _step(recorder, 2)

            client = self._client(root)
            listing = client.get("/api/episode/list")
            self.assertEqual(listing.status_code, 200)
            body = listing.json()
            self.assertEqual(body["count"], 1)
            self.assertEqual(body["episodes"][0]["steps"], 3)
            self.assertEqual(body["episodes"][0]["conn"], "robot-01")

            detail = client.get("/api/episode/run_20260916_120000/robot-01/0")
            self.assertEqual(detail.status_code, 200)
            payload = detail.json()
            self.assertEqual(payload["step_count"], 3)
            self.assertEqual(payload["truncated_records"], 0)
            overlay = payload["overlay"]
            self.assertTrue(overlay["offset_calibrated"], "标定了偏移就该报 True")
            self.assertEqual(len(overlay["predicted"]), 2, "失败步不进预测轨迹")
            self.assertEqual(len(overlay["actual"]), 3)
            self.assertEqual(overlay["skipped_steps"], 1)
            # 偏移真的生效：预测点比"航点末端原值"各多 0.6 m
            raw_forward = 1.5 + 2 * 0.1
            self.assertAlmostEqual(overlay["predicted"][-1][0] - raw_forward, 0.6, places=6)

    def test_missing_episode_is_404_not_empty_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(Path(tmp))
            response = client.get("/api/episode/run_20260916_120000/robot-01/9")
            self.assertEqual(response.status_code, 404, "缺集必须 404（不许用空数据冒充成功）")


if __name__ == "__main__":
    unittest.main()


class EpisodeImportRouteTests(unittest.TestCase):
    """B4：浏览器运行产出的 episode 必须能落盘并被同一读侧读出。

    防的回归：`EpisodeRecorder` 曾只在测试里实例化 ⇒ `/api/episode/list` 结构上恒空、
    回放页永远空态。现在写侧是 `POST /api/episode/import`（浏览器场景跑完调用），
    这里钉三件事：落盘布局与 recorder 一致、不覆盖既有 episode、非法 run/conn 拒收。
    """

    def setUp(self):
        # 与既有用例同一套隔离：把 episode 根指到临时目录，绝不写用户主目录
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._root = Path(self._tmp.name)
        import backend.episode_api as api

        original = api.episode_root
        api.episode_root = lambda **kw: self._root
        self.addCleanup(lambda: setattr(api, "episode_root", original))

    def _client(self):
        from fastapi.testclient import TestClient

        from backend.api_complete import app

        return TestClient(app)

    def _payload(self, run="b4_case"):
        return {
            "run": run,
            "conn": "browser-wasm",
            "episode": 1,
            "manifest": {"task": "scenario", "instruction": "b4", "extra": {"scenario_id": "b4"}},
            "records": [
                {"step": 0, "waypoints": [[0.0, 0.0]], "pointing": {"actual": [0.0, 0.0]}},
                {"step": 1, "waypoints": [[0.5, 0.0]], "pointing": {"actual": [0.45, 0.02]}},
            ],
        }

    def test_import_round_trip(self):
        client = self._client()
        response = client.post("/api/episode/import", json=self._payload())
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual(2, body["steps"])
        self.assertIn("replay_url", body)
        # 同一读侧必须能读回来（布局一致），且 overlay 有预测/实际两条
        detail = client.get(f"/api/episode/{body['run']}/browser-wasm/1")
        self.assertEqual(200, detail.status_code, detail.text)
        overlay = detail.json()["overlay"]
        self.assertEqual([[0.0, 0.0], [0.5, 0.0]], overlay["predicted"])
        self.assertEqual([[0.0, 0.0], [0.45, 0.02]], overlay["actual"])
        self.assertFalse(overlay["offset_calibrated"], "浏览器运行未做相机标定，必须如实说未标定")

    def test_import_refuses_overwrite(self):
        client = self._client()
        self.assertEqual(200, client.post("/api/episode/import", json=self._payload()).status_code)
        again = client.post("/api/episode/import", json=self._payload())
        self.assertEqual(409, again.status_code, "episode 是证据，不静默覆盖")

    def test_import_rejects_traversal_names(self):
        client = self._client()
        for bad in ("../escape", "a/b", ".."):
            response = client.post("/api/episode/import", json={**self._payload(), "run": bad})
            self.assertEqual(400, response.status_code, f"run={bad} 必须拒收")

    def test_import_requires_records(self):
        client = self._client()
        response = client.post("/api/episode/import", json={**self._payload(), "records": []})
        self.assertEqual(400, response.status_code)
