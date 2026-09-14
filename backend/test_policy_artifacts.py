"""B10 出库测试：声明扫描 / 引用式产物 / hash 对账 / 影子产物检出。

用合成包（临时目录）覆盖逻辑，另加一条**真实仓库**一致性断言 —— 让测试能真正反映本仓现状，
而不只是"自说自话的小世界"。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import policy_artifacts as pa  # noqa: E402


def make_package(root: Path, robot: str, *, onnx_bytes: bytes = b"onnx-bytes",
                 policy_id: str = "walk-100", extra_declared: str | None = None) -> Path:
    """造一个最小机器人包：``<robot>/simulation/{config.json, policies/*.onnx}``。"""
    pkg = root / robot
    policies = pkg / "simulation" / "policies"
    policies.mkdir(parents=True)
    (policies / "walk.onnx").write_bytes(onnx_bytes)
    declarations = [{
        "id": policy_id, "path": "simulation/policies/walk.onnx", "label": "Walk",
        "obs_dim": 48, "action_dim": 12, "history_len": 1, "task_type": "velocity",
        "source": "builtin-package",
        "contract": {"observation_kind": "go2_velocity", "action_scale": 0.25,
                     "action_joint_order": ["FL_hip_joint", "FR_hip_joint"]},
    }]
    if extra_declared:
        declarations.append({"id": extra_declared, "path": f"simulation/policies/{extra_declared}.onnx"})
    (pkg / "simulation" / "config.json").write_text(
        json.dumps({"policies": declarations}, ensure_ascii=False), encoding="utf-8",
    )
    return pkg


class ScanTest(unittest.TestCase):
    def test_scan_collects_both_sections_and_resolves_onnx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            (root / "go2" / "simulation" / "config.json").write_text(
                json.dumps({
                    "policies": [{"id": "walk-100", "path": "simulation/policies/walk.onnx"}],
                    "demo_policies": [{"id": "demo-1", "url": "/api/simulation/browser-package/go2/simulation/policies/walk.onnx"}],
                }), encoding="utf-8",
            )
            declarations = pa.scan_declarations(root)
            self.assertEqual([d["kind"] for d in declarations], ["policies", "demo_policies"])
            self.assertTrue(all(d["onnx"] is not None for d in declarations))
            # URL 形式与相对路径形式解析到同一个文件
            self.assertEqual(declarations[0]["onnx"], declarations[1]["onnx"])

    def test_unresolvable_declaration_is_reported_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2", extra_declared="missing-blob")
            index = pa.build_all(robots_dir=root, out_dir=root / "policies")
            self.assertEqual(index["count"], 2)
            self.assertTrue(any("missing-blob" in problem for problem in index["problems"]))

    def test_artifact_id_is_stable_and_sanitized(self):
        self.assertEqual(pa.artifact_id_for("go2", "walk-100"), "go2__walk-100")
        self.assertEqual(pa.artifact_id_for("zex w", "a/b"), "zex-w__a-b")


class BuildTest(unittest.TestCase):
    def test_build_writes_deploy_and_artifact_with_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2", onnx_bytes=b"payload-123")
            out = root / "policies"
            index = pa.build_all(robots_dir=root, out_dir=out, write=True)

            self.assertEqual(index["count"], 1)
            target = out / "go2__walk-100"
            self.assertTrue((target / pa.ARTIFACT_NAME).is_file())
            self.assertTrue((target / pa.DEPLOY_NAME).is_file())
            self.assertTrue((out / pa.INDEX_NAME).is_file())

            artifact = json.loads((target / pa.ARTIFACT_NAME).read_text(encoding="utf-8"))
            self.assertEqual(artifact["onnx_sha256"], pa.file_digest(root / "go2" / "simulation" / "policies" / "walk.onnx"))
            self.assertEqual(artifact["onnx_bytes"], len(b"payload-123"))
            self.assertTrue(artifact["contract_digest"])
            self.assertIsNone(artifact["run_id"])          # 上游导入：血缘如实留空

            deploy = (target / pa.DEPLOY_NAME).read_text(encoding="utf-8")
            self.assertIn("action_scale: 0.25", deploy)     # 数值不带引号
            self.assertIn("FL_hip_joint", deploy)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            out = root / "policies"
            index = pa.build_all(robots_dir=root, out_dir=out, write=False)
            self.assertEqual(index["count"], 1)
            self.assertFalse(out.exists())

    def test_contract_change_changes_contract_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = make_package(root, "go2")
            first = pa.scan_declarations(root)[0]
            config = json.loads((pkg / "simulation" / "config.json").read_text(encoding="utf-8"))
            config["policies"][0]["contract"]["action_scale"] = 0.5   # 动作约定变了
            (pkg / "simulation" / "config.json").write_text(json.dumps(config), encoding="utf-8")
            second = pa.scan_declarations(root)[0]
            self.assertNotEqual(pa.contract_digest(first), pa.contract_digest(second))


class VerifyTest(unittest.TestCase):
    def test_verify_passes_right_after_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            out = root / "policies"
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            report = pa.verify_artifacts(robots_dir=root, out_dir=out)
            self.assertTrue(report["ok"], report["problems"])
            self.assertEqual(report["checked"], 1)

    def test_verify_detects_swapped_onnx(self):
        """换了包里的 onnx 却不重新出库 —— 必须被抓到（这是"出库"最容易悄悄烂掉的地方）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            out = root / "policies"
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            (root / "go2" / "simulation" / "policies" / "walk.onnx").write_bytes(b"tampered")

            report = pa.verify_artifacts(robots_dir=root, out_dir=out)
            self.assertFalse(report["ok"])
            self.assertTrue(any("onnx 已变" in problem for problem in report["problems"]))

    def test_verify_detects_missing_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = pa.verify_artifacts(robots_dir=Path(tmp), out_dir=Path(tmp) / "policies")
            self.assertFalse(report["ok"])
            self.assertTrue(any(pa.INDEX_NAME in problem for problem in report["problems"]))


class ReferenceTest(unittest.TestCase):
    """B10 收尾：声明从"裸路径"切到"引用 + hash"的读侧。"""

    def test_blob_resolves_from_either_form(self):
        """两种形式并存是迁移能安全落地的关键：消费者不必知道自己读的是哪一种。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            out = root / "policies"
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            index = pa.load_index(out)

            legacy = pa.scan_declarations(root)[0]
            self.assertIsNotNone(pa.policy_blob_path(legacy, robot_dir=root / "go2", index=index))

            migrated = dict(legacy)
            migrated.pop("declared")
            migrated["onnx"] = None
            migrated["artifact_id"] = pa.artifact_id_for("go2", "walk-100")
            blob = pa.policy_blob_path(migrated, robot_dir=root / "go2", index=index)
            self.assertIsNotNone(blob)
            self.assertEqual(blob, legacy["onnx"])       # 两条路径解析到同一个文件

    def test_hash_is_measured_not_copied_from_index(self):
        """"索引说自己是什么"与"文件实际是什么"必须分开 —— 不然漂移查不出来。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            out = root / "policies"
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            index = pa.load_index(out)

            declaration = pa.scan_declarations(root)[0]
            before = pa.policy_reference(declaration, index=index)["onnx_sha256"]
            (root / "go2" / "simulation" / "policies" / "walk.onnx").write_bytes(b"swapped")

            after = pa.policy_reference(declaration, index=index)["onnx_sha256"]
            self.assertNotEqual(before, after)

    def test_id_only_declaration_resolves_via_index(self):
        """**终态**：契约只留 `id`（裸 path/url 已删），仍能解析到 blob —— 这是删除的前提。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            out = root / "policies"
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            index = pa.load_index(out)

            id_only = {"robot": "go2", "policy_id": "walk-100"}          # 无 path / url / artifact_id
            self.assertFalse(pa.declaration_has_raw_path(id_only))
            self.assertIsNotNone(pa.policy_blob_path(id_only, index=index))
            self.assertEqual(
                "simulation/policies/walk.onnx",
                pa.policy_relative_path(id_only, robot_dir=root / "go2", index=index),
            )

    def test_relative_path_is_none_when_blob_lives_outside_package(self):
        """包外的 blob 不该被编出一个"包内相对路径"（否则会产出一个取不到文件的 URL）。

        注意：这里用**包内相对路径能表达、但目标在包外**的形式（``../models/x.onnx``）验证。
        不能用 ``/web/sim2sim/models/`` 那种绝对形式 —— 它是相对**仓库根**解析的，
        临时目录里永远解析不到，测的就不是这个属性了。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            robot_dir = root / "robots" / "go2"                  # root/robots/go2
            (robot_dir / "simulation").mkdir(parents=True)
            outside = root / "models"                            # root/models（包外）
            outside.mkdir()
            (outside / "x.onnx").write_bytes(b"blob")
            declaration = {
                "robot_dir": str(robot_dir),
                "path": "../../models/x.onnx",                   # 上溯两级才回到 root
                "robot": "go2", "policy_id": "x",
            }
            self.assertIsNotNone(pa.policy_blob_path(declaration))       # 能解析到文件
            self.assertIsNone(pa.policy_relative_path(declaration, robot_dir=robot_dir))  # 但不在包内

    def test_reference_gaps_lists_unmigrated_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            out = root / "policies"
            pa.build_all(robots_dir=root, out_dir=out, write=True)

            report = pa.reference_gaps(robots_dir=root, out_dir=out)
            self.assertEqual(report["declared"], 1)
            self.assertEqual(report["legacy_path_declarations"], ["go2__walk-100"])
            self.assertEqual(report["problems"], [])      # hash 一致，只是形式还没切

    def test_missing_blob_is_reported_not_silenced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_package(root, "go2")
            out = root / "policies"
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            (root / "go2" / "simulation" / "policies" / "walk.onnx").unlink()

            report = pa.reference_gaps(robots_dir=root, out_dir=out)
            self.assertFalse(report["ok"])
            self.assertTrue(any("解析不到 blob" in problem for problem in report["problems"]))


class AuxBlobTest(unittest.TestCase):
    """辅助 blob（encoder）：一个策略 = 主 blob + 辅助 blob，**同一个框架**。

    背景：TRON1 的部署策略是两个 onnx 图（encoder + policy），这是**上游的导出约定**
    （`00_resources/tron1-rl-deploy-{python,ros2}` 就是成对发的）。运行时早已统一支持
    （`encoder_rel` + `run_encoder_mode`），只有出库/统计层把 encoder 当外人 ——
    于是那 3 个 encoder 文件被 `unexported_onnx()` 误报成"影子产物"。
    """

    @staticmethod
    def _package(root: Path, *, with_encoder: bool = True) -> Path:
        import json

        robot_dir = root / "go2"
        policies = robot_dir / "simulation" / "policies"
        policies.mkdir(parents=True)
        (policies / "walk.onnx").write_bytes(b"policy-blob")
        entry = {"id": "walk-100", "label": "walk", "path": "simulation/policies/walk.onnx"}
        if with_encoder:
            (policies / "enc.onnx").write_bytes(b"encoder-blob")
            entry["encoder"] = "simulation/policies/enc.onnx"
        (robot_dir / "simulation" / "config.json").write_text(
            json.dumps({"policies": [entry]}), encoding="utf-8",
        )
        return robot_dir

    def test_encoder_is_captured_and_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root)
            aux = pa.policy_aux_blobs(pa.scan_declarations(root)[0])
            self.assertEqual(1, len(aux))
            self.assertEqual("encoder", aux[0]["role"])
            self.assertFalse(aux[0]["missing"])
            self.assertEqual(
                pa.file_digest(root / "go2" / "simulation" / "policies" / "enc.onnx"),
                aux[0]["sha256"],
            )

    def test_missing_encoder_is_reported_not_silenced(self):
        """声明了但文件不在 → 如实记 ``missing``（缺件要被看见，不静默）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            robot_dir = self._package(root)
            (robot_dir / "simulation" / "policies" / "enc.onnx").unlink()
            aux = pa.policy_aux_blobs(pa.scan_declarations(root)[0])
            self.assertTrue(aux[0]["missing"])
            self.assertIsNone(aux[0]["sha256"])
            self.assertIsNone(aux[0]["source"])

    def test_encoder_counts_as_declared_so_no_shadow_report(self):
        """关键：encoder 计入"被声明" → 不再被 ``unexported_onnx()`` 误报成影子产物。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root)
            self.assertEqual([], pa.unexported_onnx(robots_dir=root))

    def test_artifact_metadata_carries_aux_blobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root)
            artifact = pa.build_artifact(pa.scan_declarations(root)[0])
            self.assertEqual(1, len(artifact["aux_blobs"]))
            self.assertEqual("encoder", artifact["aux_blobs"][0]["role"])
            self.assertIsNotNone(artifact["aux_blobs"][0]["sha256"])

    def test_real_repo_has_zero_shadow_onnx(self):
        """**真实仓不变量**：那 3 个 encoder 文件是被声明的 —— 修好后影子产物应为 0。

        这条一旦红，说明包内又出现了"没有任何声明指向"的 onnx（新的影子产物）。
        """
        self.assertEqual([], pa.unexported_onnx())
        missing = [
            f"{d['robot']}/{d['policy_id']}:{aux['role']}"
            for d in pa.scan_declarations()
            for aux in pa.policy_aux_blobs(d)
            if aux["missing"]
        ]
        self.assertEqual([], missing, "声明的辅助 blob 都应找得到")


class ProducedPolicyTest(unittest.TestCase):
    def test_promote_writes_blob_and_links_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "model_final.onnx"
            source.write_bytes(b"produced-policy")
            out = root / "policies"
            artifact = pa.promote_produced_policy(
                artifact_id="go2__velocity-run1", onnx=source,
                deploy={"robot": "go2", "action_scale": 0.25},
                run_id="20260914-120000_velocity_ab12cd34", out_dir=out,
            )
            self.assertEqual(artifact["run_id"], "20260914-120000_velocity_ab12cd34")
            self.assertEqual(artifact["onnx_sha256"], pa.file_digest(out / "go2__velocity-run1" / pa.POLICY_BLOB_NAME))
            self.assertTrue((out / "go2__velocity-run1" / pa.DEPLOY_NAME).is_file())


class RealRepoTest(unittest.TestCase):
    """真实仓库自检：声明数、onnx 实体数、影子产物。"""

    def test_repo_declarations_resolve_and_count_matches_blobs(self):
        """**B10 终态自检**：声明只留 `id`，解析一律经 `policies/index.json`。"""
        declarations = pa.scan_declarations()
        self.assertGreater(len(declarations), 40, "本仓应有 46 条策略声明")
        index = pa.load_index()
        self.assertTrue(index, "先跑 build_all(write=True) 出库")

        unresolved = [
            f"{d['robot']}/{d['policy_id']}"
            for d in declarations
            if pa.policy_blob_path(d, index=index) is None
        ]
        self.assertEqual([], unresolved, "每条声明都应能经索引解析到 blob")

        # 终态：声明里不该再留裸路径（这正是 migrate_policy_refs.py 的严格判据）
        self.assertEqual(
            [], [d["policy_id"] for d in declarations if pa.declaration_has_raw_path(d)],
        )
        gaps = pa.reference_gaps()
        self.assertEqual([], gaps["problems"], gaps["problems"])

        # 包内 46 个 onnx 实体；第 47 个在 `web/sim2sim/models/`（经声明 url 形式引用）。
        blobs = list(pa.iter_onnx_files())
        self.assertEqual(46, len(blobs), "包内 onnx 实体数")
        self.assertIsInstance(pa.unexported_onnx(), list)

    def test_artifact_ids_are_unique(self):
        ids = [pa.artifact_id_for(d["robot"], d["policy_id"]) for d in pa.scan_declarations()]
        self.assertEqual(len(ids), len(set(ids)), "产物 ID 必须唯一，否则出库会互相覆盖")


if __name__ == "__main__":
    unittest.main()
