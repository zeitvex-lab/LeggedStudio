"""profile extends 层叠回归锁（Phase 2 插件化）：组合协议是吞吐闸，语义错了锁死实验。"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("profile_extends", ROOT / "adapters" / "mjlab" / "profile_extends.py")
pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pe)


def _write_profile(dir_: Path, profile_id: str, body: dict) -> None:
    body = {"profile_id": profile_id, **body}
    (dir_ / f"{profile_id}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


class ProfileExtendsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir_ = Path(self._tmp.name)
        _write_profile(self.dir_, "base", {
            "entrypoints": {"env": "m:base_env", "runner": "m:base_runner"},
            "commands": {"twist": {"ranges": {"lin_vel_x": [-0.1, 0.25]}}},
            "note": "base",
        })

    def tearDown(self):
        self._tmp.cleanup()

    def test_child_overrides_shallow_keys_and_inherits_rest(self):
        _write_profile(self.dir_, "child", {
            "extends": "base",
            "note": "child note",       # 浅键整覆盖
            "overrides": {"commands": {"twist": {"ranges": {"lin_vel_x": [-0.2, 0.5]}}}},
        })
        raw = json.loads((self.dir_ / "child.json").read_text(encoding="utf-8"))
        out = pe.resolve_profile_extends(raw, self.dir_)
        self.assertEqual("child", out["profile_id"])          # id 保持子档案
        self.assertNotIn("extends", out)                       # 链已剥离（全量视图）
        self.assertEqual("child note", out["note"])            # 浅键覆盖
        self.assertEqual("m:base_env", out["entrypoints"]["env"])  # 基键继承
        self.assertEqual([-0.2, 0.5], out["commands"]["twist"]["ranges"]["lin_vel_x"])  # 深合并覆盖
        # overrides 未给的兄弟键（lin_vel_y 若基档案有则保留）——深合并不整树替换
        self.assertEqual("m:base_runner", out["entrypoints"]["runner"])

    def test_missing_base_fails_loud_with_available(self):
        _write_profile(self.dir_, "orphan", {"extends": "no-such-base"})
        raw = json.loads((self.dir_ / "orphan.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(pe.ProfileExtendsError, "no-such-base.*可用.*base"):
            pe.resolve_profile_extends(raw, self.dir_)

    def test_cycle_fails_loud(self):
        _write_profile(self.dir_, "a", {"extends": "b"})
        _write_profile(self.dir_, "b", {"extends": "a"})
        raw = json.loads((self.dir_ / "a.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(pe.ProfileExtendsError, "环或过深"):
            pe.resolve_profile_extends(raw, self.dir_)

    def test_no_extends_returns_as_is(self):
        raw = {"profile_id": "solo", "note": "x"}
        self.assertIs(pe.resolve_profile_extends(raw, self.dir_), raw)  # 原对象返回（零迁移）


if __name__ == "__main__":
    unittest.main()
