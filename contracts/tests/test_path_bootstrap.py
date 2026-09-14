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


class AdapterInterpreterResolutionTest(unittest.TestCase):
    """训练适配器解释器解析：单一事实源，支持三组覆盖环境变量。

    这些测试保护"训练栈落点只有一处定义"这条纪律——曾经它被硬编码在 10 个
    调用点，导致镜像里的 CPU 训练 venv（仓库外）无法被发现。
    """

    @classmethod
    def setUpClass(cls):
        cls.pb = _load_path_bootstrap()

    def setUp(self):
        import os

        self._saved = {name: os.environ.get(name) for name in
                       (self.pb.ADAPTER_VENV_ENV, *self.pb.ADAPTER_PYTHON_ENVS)}
        for name in self._saved:
            os.environ.pop(name, None)

    def tearDown(self):
        import os

        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_default_venv_layout_is_posix(self):
        self.assertEqual(
            self.pb.venv_python("/x/y", platform="linux"),
            Path("/x/y/bin/python"),
        )

    def test_default_venv_layout_is_windows(self):
        self.assertEqual(
            self.pb.venv_python("/x/y", platform="win32"),
            Path("/x/y/Scripts/python.exe"),
        )

    def test_venv_env_overrides_default(self):
        import os

        os.environ[self.pb.ADAPTER_VENV_ENV] = "/opt/legged-studio/mjlab-cpu/.venv"
        self.assertEqual(
            self.pb.adapter_venv_dir(),
            Path("/opt/legged-studio/mjlab-cpu/.venv"),
        )
        # 解释器在 venv 内的相对落点**随平台不同**（POSIX `bin/python` / Windows `Scripts/python.exe`）。
        # 期望值用被测模块自己的 helper 推出来，避免把 Linux 路径写死进断言（在 Windows 上必红）。
        self.assertEqual(
            self.pb.adapter_python(),
            self.pb.venv_python(Path("/opt/legged-studio/mjlab-cpu/.venv")),
        )

    def test_explicit_interpreter_env_wins_over_venv_dir(self):
        import os

        os.environ[self.pb.ADAPTER_VENV_ENV] = "/opt/legged-studio/mjlab-cpu/.venv"
        for name in self.pb.ADAPTER_PYTHON_ENVS:
            os.environ[name] = f"/custom/{name}/python"
        # 显式解释器优先级最高（桌面启动器 / 精简运行时的既有约定）
        self.assertEqual(self.pb.adapter_python(), Path("/custom/LEGGED_STUDIO_MJLAB_PYTHON/python"))

    def test_venv_dir_falls_back_to_default(self):
        self.assertEqual(
            self.pb.adapter_venv_dir(default="/fallback/venv"),
            Path("/fallback/venv"),
        )


if __name__ == "__main__":
    unittest.main()
