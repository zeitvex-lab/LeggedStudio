"""T2.2：TB events 最小解析器 + 五大健康仪表盘/症状卡测试。"""

from __future__ import annotations

import struct
import unittest

from backend.health_cards import build_health_report
from backend.tb_events import parse_events_file


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _tag(field_no: int, wire_type: int) -> bytes:
    return _varint((field_no << 3) | wire_type)


def _string_field(field_no: int, value: str) -> bytes:
    data = value.encode("utf-8")
    return _tag(field_no, 2) + _varint(len(data)) + data


def _summary_value(tag: str, simple: float) -> bytes:
    return (
        _tag(1, 2) + _varint(len(tag.encode())) + tag.encode()
        + _tag(2, 5) + struct.pack("<f", simple)
    )


def _event(step: int, scalars: list[tuple[str, float]]) -> bytes:
    # Summary 消息体 = repeated Summary.Value 逐条 framed 后直接拼接（不再包一层）
    summary = b"".join(
        _tag(1, 2) + _varint(len(sv)) + sv
        for sv in (_summary_value(tag, simple) for tag, simple in scalars)
    )
    return _tag(1, 1) + struct.pack("<d", 0.0) + _tag(2, 0) + _varint(step) + _tag(5, 2) + _varint(len(summary)) + summary


def _frame(record: bytes) -> bytes:
    return struct.pack("<Q", len(record)) + b"\x00" * 4 + record + b"\x00" * 4


class TbEventsParserTest(unittest.TestCase):
    def test_parse_synthetic_events_file(self) -> None:
        from pathlib import Path
        import tempfile

        records = (
            _frame(_event(0, [("prefix", 0.0)]))
            + _frame(_event(10, [("Episode/rew_tracking_lin_vel", 1.5), ("Episode/rew_action_rate", -0.2)]))
            + _frame(_event(20, [("Episode/rew_tracking_lin_vel", 2.5), ("Episode/rew_action_rate", -0.1)]))
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.out.tfevents.test"
            path.write_bytes(records)
            series = parse_events_file(path)
        self.assertEqual([step for step, _ in series["Episode/rew_tracking_lin_vel"]], [10, 20])
        self.assertAlmostEqual(series["Episode/rew_tracking_lin_vel"][1][1], 2.5, places=5)
        self.assertAlmostEqual(series["Episode/rew_action_rate"][0][1], -0.2, places=5)

    def test_reward_layer_mapping(self) -> None:
        from adapters.mjlab.reward_layers import get_reward_layer

        # 生产约定：端点先把 rsl_rl 的 "Episode/rew_xxx" 归一化为 xxx 再查层
        self.assertEqual(get_reward_layer("rew_tracking_lin_vel".removeprefix("rew_")), "Tracking")
        self.assertEqual(get_reward_layer("rew_action_rate".removeprefix("rew_")), "Regularization")
        self.assertEqual(get_reward_layer("rew_feet_air_time".removeprefix("rew_")), "Contact")
        self.assertEqual(get_reward_layer("rew_totally_unknown".removeprefix("rew_")), "Other")


class HealthGaugesTest(unittest.TestCase):
    def _rows(self, n: int, **series: list[float]) -> list[dict]:
        return [{key: values[i] for key, values in series.items()} for i in range(n)]

    def test_kl_zero_flags_symptom_card(self) -> None:
        rows = self._rows(12, reward=[1.0] * 12, kl=[0.0] * 12, entropy=[0.9] * 12)
        report = build_health_report(rows)
        self.assertEqual(report["gauges"]["kl"]["status"], "warn")
        self.assertTrue(any(card["id"] == "kl_zero" for card in report["cards"]))
        card = next(card for card in report["cards"] if card["id"] == "kl_zero")
        # 铁律：第一步是验接口，最后一步才是调 PPO 参数
        self.assertIn("scale", card["steps"][0]["check"])
        self.assertIn("learning_rate", card["steps"][-1]["jump"])

    def test_reward_up_flags_hacking_card(self) -> None:
        rows = self._rows(40, reward=[float(i) for i in range(40)], kl=[0.01] * 40, entropy=[0.8] * 40)
        report = build_health_report(rows)
        self.assertTrue(any(card["id"] == "reward_up_perf_flat" for card in report["cards"]))
        self.assertIn("分项", report["gauges"]["reward"]["summary"])

    def test_missing_series_reported_honestly(self) -> None:
        report = build_health_report([])
        for gauge in report["gauges"].values():
            self.assertIn("未采集", gauge["summary"])
        self.assertIn("先验接口", report["rule"])


if __name__ == "__main__":
    unittest.main()
