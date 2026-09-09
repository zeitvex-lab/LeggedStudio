"""backend_adapter Protocol / registry 测试（无 torch 依赖，可独立单测）。"""

from __future__ import annotations

import unittest

from adapters.backend_adapter import (
    BACKEND_DESCRIPTORS,
    BackendDescriptor,
    get_backend_descriptor,
    list_backend_descriptors,
    load_backend_adapter,
)


class DescriptorTest(unittest.TestCase):
    def test_native_mjlab_available(self) -> None:
        desc = get_backend_descriptor("native_mjlab")
        self.assertIsNotNone(desc)
        assert desc is not None
        self.assertTrue(desc.available)
        self.assertEqual(desc.python_env, "mjlab-py312")
        self.assertTrue(desc.env_entrypoint)

    def test_unilab_planned_not_available(self) -> None:
        desc = get_backend_descriptor("unilab")
        self.assertIsNotNone(desc)
        assert desc is not None
        self.assertFalse(desc.available)

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(get_backend_descriptor("nope"))

    def test_list_includes_three(self) -> None:
        ids = {item.id for item in list_backend_descriptors()}
        self.assertEqual(ids, {"native_mjlab", "unilab", "isaacgym"})


class LoadAdapterTest(unittest.TestCase):
    def test_load_missing_entrypoint_returns_none(self) -> None:
        desc = BackendDescriptor(
            id="x", label="X", python_env="x", available=False,
            env_entrypoint="", runner_entrypoint="", exporter_entrypoint="",
        )
        result = load_backend_adapter(desc)
        self.assertEqual(result, {"env": None, "runner": None, "exporter": None})

    def test_load_unknown_module_returns_none_gracefully(self) -> None:
        desc = BackendDescriptor(
            id="x", label="X", python_env="x", available=True,
            env_entrypoint="no_such_module:xyz",
        )
        result = load_backend_adapter(desc)
        self.assertIsNone(result["env"])

    def test_load_builtin_stdlib_callable(self) -> None:
        # 解析一个标准库 callable，验证正路径。
        desc = BackendDescriptor(
            id="x", label="X", python_env="x", available=True,
            env_entrypoint="os:getcwd",
        )
        result = load_backend_adapter(desc)
        self.assertTrue(callable(result["env"]))


if __name__ == "__main__":
    unittest.main()
