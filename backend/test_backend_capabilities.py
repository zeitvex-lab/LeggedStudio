"""K2 回归测试：后端能力契约（声明式 + fail-closed，不回退）。

要点：

* 未声明的能力不是「不支持但可以试试」，而是 ``CapabilityNotImplementedError``；
* ``partial`` 与 ``supported`` 区别对待——**不能**因为"大部分能用"就放行；
* 能力名拼错必须炸（``UnknownCapabilityError``），否则会被当成正常分支走掉；
* 未登记的后端不许回退到 mjlab；
* 能力表与 descriptor 表 id 必须对齐（新增后端不能只补一边）；
* 声明 ``supported`` 的后端必须给出证据路径（不许凭空写"支持"）；
* 本文件同时守住既有 adapter 协议 API 未被破坏（``list_backend_descriptors`` 等）。
"""

from __future__ import annotations

import unittest

from adapters.backend_adapter import (
    BACKEND_CAPABILITIES,
    BACKEND_DESCRIPTORS,
    CAPABILITY_CATALOG,
    PARTIAL,
    SUPPORTED,
    UNSUPPORTED,
    BackendDescriptor,
    CapabilityNotImplementedError,
    DomainRandomizationCapabilities,
    HeightScannerCapabilities,
    PlayCapabilities,
    UnknownCapabilityError,
    adapter_selftest,
    backend_capabilities,
    capability_matrix,
    get_backend_descriptor,
    known_capabilities,
    list_backend_descriptors,
)


class CapabilityLevelTests(unittest.TestCase):
    def test_undeclared_capability_defaults_to_unsupported(self):
        play = PlayCapabilities(levels={"multi_env": SUPPORTED})
        self.assertEqual(play.level("onnx_export"), UNSUPPORTED)
        self.assertFalse(play.supports("onnx_export"))

    def test_require_raises_for_unsupported_and_partial(self):
        play = PlayCapabilities(levels={"multi_env": SUPPORTED, "depth_camera": PARTIAL})
        self.assertEqual(play.require("multi_env"), SUPPORTED)
        for capability in ("onnx_export", "depth_camera"):
            with self.subTest(capability=capability):
                with self.assertRaises(CapabilityNotImplementedError):
                    play.require(capability)

    def test_unknown_capability_name_is_an_error_not_unsupported(self):
        play = PlayCapabilities(levels={"multi_env": SUPPORTED})
        with self.assertRaises(UnknownCapabilityError):
            play.level("teleport")
        with self.assertRaises(UnknownCapabilityError):
            play.require("teleport")

    def test_declared_only_lists_explicit_entries(self):
        play = PlayCapabilities(levels={"multi_env": SUPPORTED}, notes={"multi_env": "why"})
        declared = play.declared()
        self.assertEqual(set(declared), {"multi_env"})
        self.assertEqual(declared["multi_env"]["level"], SUPPORTED)
        self.assertEqual(declared["multi_env"]["note"], "why")
        self.assertIn("批量并行环境", declared["multi_env"]["help"])

    def test_round_trip_and_validation(self):
        play = PlayCapabilities(levels={"multi_env": SUPPORTED}, notes={"multi_env": "n"})
        self.assertEqual(PlayCapabilities.from_dict(play.to_dict()).levels, play.levels)
        with self.assertRaises(ValueError):
            PlayCapabilities.from_dict({"levels": {"multi_env": "sometimes"}})
        with self.assertRaises(UnknownCapabilityError):
            PlayCapabilities.from_dict({"levels": {"teleport": SUPPORTED}})

    def test_specialised_capabilities_fail_closed(self):
        with self.assertRaises(CapabilityNotImplementedError):
            HeightScannerCapabilities(available=False, notes="未接线").require()
        with self.assertRaises(CapabilityNotImplementedError):
            DomainRandomizationCapabilities(available=False).require()
        self.assertTrue(HeightScannerCapabilities(available=True, backend="x").require().available)
        dr = DomainRandomizationCapabilities(available=True, fields=("friction",))
        self.assertTrue(dr.supports_field("friction"))
        self.assertFalse(dr.supports_field("mass"))


class BackendDeclarationTests(unittest.TestCase):
    def test_capability_and_descriptor_tables_are_aligned(self):
        self.assertEqual(set(BACKEND_CAPABILITIES), set(BACKEND_DESCRIPTORS))

    def test_declared_levels_are_legal_and_known(self):
        for backend_id, capabilities in BACKEND_CAPABILITIES.items():
            with self.subTest(backend=backend_id):
                for capability, level in capabilities.play.levels.items():
                    self.assertIn(capability, CAPABILITY_CATALOG)
                    self.assertIn(level, {SUPPORTED, PARTIAL, UNSUPPORTED})

    def test_supported_declarations_carry_evidence(self):
        """声明了 supported 的后端必须给出证据路径——不许凭空写"支持"。"""
        for backend_id, capabilities in BACKEND_CAPABILITIES.items():
            if not any(level == SUPPORTED for level in capabilities.play.levels.values()):
                continue
            with self.subTest(backend=backend_id):
                self.assertTrue(capabilities.evidence, f"{backend_id} 声明 supported 但无 evidence")

    def test_mjlab_usable_but_unfinished_capabilities_not_pretended(self):
        mjlab = backend_capabilities("native_mjlab")
        self.assertTrue(mjlab.supports("multi_env"))
        self.assertTrue(mjlab.supports("onnx_export"))
        self.assertFalse(mjlab.supports("domain_randomization"))
        self.assertFalse(mjlab.supports("height_scan"))
        self.assertEqual(mjlab.play.level("deterministic_replay"), PARTIAL)

    def test_only_declared_backends_exist(self):
        """2026-09-13 裁决：先做精 mjlab+mujoco，第二后端规划已删除。

        能力机制保留（第二后端将来重新决策时直接插表即可），但**表里不许留幽灵条目**
        ——"规划中"的后端一并清掉，避免 UI/调用方看到一个永远不会可用的后端。
        """
        self.assertEqual(set(BACKEND_CAPABILITIES), {"native_mjlab", "unilab", "isaacgym"})
        for backend_id in ("motrixsim", "motrix"):
            with self.subTest(backend=backend_id):
                with self.assertRaises(UnknownCapabilityError):
                    backend_capabilities(backend_id)

    def test_unknown_backend_raises_and_does_not_fall_back(self):
        with self.assertRaises(UnknownCapabilityError):
            backend_capabilities("isaaclab")
        with self.assertRaises(UnknownCapabilityError):
            backend_capabilities("no-such-engine")

    def test_matrix_covers_all(self):
        matrix = capability_matrix()
        self.assertEqual(set(matrix["backends"]), set(BACKEND_CAPABILITIES))
        for row in matrix["backends"].values():
            self.assertEqual(set(row), set(known_capabilities()))

    def test_report_marks_specialised_capabilities(self):
        report = backend_capabilities("native_mjlab").report()
        self.assertEqual(report["height_scan"], UNSUPPORTED)
        self.assertEqual(report["domain_randomization"], UNSUPPORTED)
        self.assertEqual(report["multi_env"], SUPPORTED)

    def test_descriptor_delegates_to_capability_table(self):
        descriptor = get_backend_descriptor("native_mjlab")
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.capabilities().backend_id, "native_mjlab")
        self.assertTrue(descriptor.supports("multi_env"))
        with self.assertRaises(CapabilityNotImplementedError):
            descriptor.require("height_scan")

    def test_unregistered_descriptor_defaults_to_all_unsupported(self):
        ghost = BackendDescriptor(id="ghost_engine", label="Ghost", python_env="ghost", available=False)
        self.assertFalse(ghost.supports("mjcf_load"))
        with self.assertRaises(CapabilityNotImplementedError):
            ghost.require("multi_env")
        self.assertIn("未登记能力声明", ghost.capabilities().notes or "")

    def test_adapter_selftest_passes(self):
        result = adapter_selftest()
        self.assertEqual(result["verdict"], "pass", result["failures"])


class ExistingProtocolRegressionTests(unittest.TestCase):
    """守住文件里既有的协议/注册表 API（K2 是增补，不是替换）。"""

    def test_descriptor_registry_still_lists_known_backends(self):
        ids = {descriptor.id for descriptor in list_backend_descriptors()}
        self.assertIn("native_mjlab", ids)
        self.assertIn("unilab", ids)
        self.assertIn("isaacgym", ids)
        self.assertIsNone(get_backend_descriptor("nope"))

    def test_native_mjlab_descriptor_keeps_its_entrypoints(self):
        descriptor = get_backend_descriptor("native_mjlab")
        self.assertTrue(descriptor.available)
        self.assertEqual(descriptor.env_entrypoint, "adapters.mjlab.env_factory:build_env")
        self.assertEqual(descriptor.exporter_entrypoint, "adapters.mjlab.onnx_exporter:export_policy_to_onnx")

    def test_load_backend_adapter_resolves_declared_entrypoint(self):
        from adapters.backend_adapter import load_backend_adapter

        descriptor = get_backend_descriptor("native_mjlab")
        resolved = load_backend_adapter(descriptor)
        self.assertEqual(set(resolved), {"env", "runner", "exporter"})
        # 控制面环境不装 torch/mjlab：解析失败按 None 占位而不是抛异常
        self.assertTrue(callable(resolved["env"]) or resolved["env"] is None)


if __name__ == "__main__":
    unittest.main()
