"""Tests for the unified sys.path bootstrap (contracts/path_bootstrap.py).

These tests load ``path_bootstrap`` directly via importlib so they can run in a
minimal environment that does not yet have pydantic/fastapi on ``sys.path``
(the module itself only depends on ``pathlib``/``sys``).
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MOD = load_path_bootstrap = None


def _load_path_bootstrap():
    global _MOD
    if _MOD is None:
        spec = importlib.util.spec_from_file_location(
            "path_bootstrap", _REPO_ROOT / "contracts" / "path_bootstrap.py"
        )
        _MOD = importlib.util.module_from_spec(spec)
        sys.modules["path_bootstrap"] = _MOD
        spec.loader.exec_module(_MOD)
    return _MOD


class PathBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pb = _load_path_bootstrap()

    def _snapshot(self):
        return list(sys.path)

    def test_project_root_is_repo_root(self):
        self.assertEqual(self.pb.PROJECT_ROOT, _REPO_ROOT)

    def test_ensure_on_path_prefixes(self):
        before = self._snapshot()
        try:
            expected = str(Path("/tmp").resolve())
            self.pb.ensure_on_path("/tmp")
            self.assertEqual(sys.path[0], expected)
        finally:
            sys.path[:] = before

    def test_ensure_on_path_idempotent(self):
        before = self._snapshot()
        try:
            p = str(_REPO_ROOT)
            normalized = str(Path(p).resolve())
            # sys.path 可能已由上游（discovery/其它模块）带有重复项，故只断言
            # "ensure_on_path 不再新增重复"，不假设全局唯一。
            baseline = sys.path.count(normalized)
            self.pb.ensure_on_path(p)
            self.pb.ensure_on_path(p)
            self.pb.ensure_on_path(p)
            self.assertLessEqual(
                sys.path.count(normalized), max(baseline, 1),
                "ensure_on_path 非幂等：重复调用增加了重复条目",
            )
        finally:
            sys.path[:] = before

    def test_ensure_many_preserves_order(self):
        before = self._snapshot()
        try:
            expected = [str(Path("/aaa").resolve()), str(Path("/bbb").resolve())]
            ensured = self.pb.ensure_many_on_path(["/aaa", "/bbb"])
            self.assertEqual(ensured, expected)
            self.assertIn(expected[0], sys.path)
            self.assertIn(expected[1], sys.path)
        finally:
            sys.path[:] = before

    def test_ensure_project_root(self):
        before = self._snapshot()
        try:
            self.pb.ensure_project_root_on_path()
            self.assertIn(str(_REPO_ROOT), sys.path)
        finally:
            sys.path[:] = before

    def test_bootstrap_root_returns_repo_root_and_ensures_it(self):
        before = self._snapshot()
        try:
            root = self.pb.bootstrap_root()
            self.assertEqual(root, _REPO_ROOT)
            self.assertIn(str(_REPO_ROOT), sys.path)
        finally:
            sys.path[:] = before


if __name__ == "__main__":
    unittest.main()
