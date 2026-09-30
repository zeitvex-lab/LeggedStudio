"""B10 出库测试：声明扫描 / 引用式产物 / hash 对账 / 影子产物检出。

用合成包（临时目录）覆盖逻辑，另加一条**真实仓库**一致性断言 —— 让测试能真正反映本仓现状，
而不只是"自说自话的小世界"。
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import unittest.mock
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

    def test_relative_path_falls_back_to_package_copy_when_index_points_outside(self):
        """G1 全机型浏览器实测缺陷 A：索引按源树记录而包根是 workspace 副本时，
        按声明裸 path 的**包内副本**回退（副本由 C6 同步保证逐字节一致）。

        现象：blob 解析命中索引路径（在"包外"）⇒ 旧逻辑返回 None ⇒ browser-config
        对该包静默跳过全部策略 ⇒ 浏览器里整机以"无策略"姿态运行。
        真实仓 46 条存量声明都带裸 path（终态形式只留 id 的包回退按 id 推导文件名，
        文件名≠id 时回退不命中——局限已知，存量数据不受影响）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 包根（模拟 workspace/packages/go2）：副本里 blob 真实存在
            robot_dir = root / "packages" / "go2"
            (robot_dir / "simulation" / "policies").mkdir(parents=True)
            (robot_dir / "simulation" / "policies" / "walk.onnx").write_bytes(b"blob")
            # 索引（模拟出库索引）：source_onnx 指源树 assets/robots/go2/...（不在包根下）
            index = {
                pa.artifact_id_for("go2", "walk-100"): {
                    "source_onnx": str(root / "assets" / "robots" / "go2" / "simulation" / "policies" / "walk.onnx"),
                },
            }
            declaration = {"robot": "go2", "policy_id": "walk-100", "path": "simulation/policies/walk.onnx"}
            self.assertIsNotNone(pa.policy_blob_path(declaration, robot_dir=robot_dir, index=index))
            self.assertEqual(
                "simulation/policies/walk.onnx",
                pa.policy_relative_path(declaration, robot_dir=robot_dir, index=index),
            )

    def test_relative_path_fallback_ignores_missing_package_copy(self):
        """回退只认包内真实存在的文件：包内没有副本 ⇒ 仍 None（不编 URL）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            robot_dir = root / "packages" / "go2"
            (robot_dir / "simulation").mkdir(parents=True)  # 没有 policies/walk.onnx
            declaration = {"robot": "go2", "policy_id": "walk-100", "path": "simulation/policies/walk.onnx"}
            self.assertIsNone(pa.policy_relative_path(declaration, robot_dir=robot_dir))

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

    def test_external_encoder_is_not_a_missing_file(self):
        """`external:<what>` = 由外部提供 ⇒ **不是包内文件、不得报成缺件**。

        它表达"这份输入由部署侧自己产生"（image encoder 的 latent、历史缓冲、
        手部任务里从 ZMQ 读的 cube pose）。与"包内 encoder onnx"（TRON1）是两种形态，
        硬按路径解析会多出一条假的缺件报警。
        """
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            robot_dir = self._package(root, with_encoder=False)
            config_path = robot_dir / "simulation" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["policies"][0]["encoder"] = "external:latent-128"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            aux = pa.policy_aux_blobs(pa.scan_declarations(root)[0])
            self.assertEqual(1, len(aux))
            self.assertFalse(aux[0]["missing"], "外部提供的输入不是缺件")
            self.assertEqual("latent-128", aux[0]["external"])
            self.assertIsNone(aux[0]["sha256"])
            self.assertIsNone(aux[0]["source"])

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


class DeclarationIdentityTest(unittest.TestCase):
    """产物身份唯一（2026-09-19）：一条声明只许有一个身份，同名条目必须**合并**。

    收口前身份有两个来源、两侧规则还不同：写索引一律用 ``artifact_id_for``、
    读引用却优先 ``provenance.artifact_id`` → 带血缘的声明多出一个**永不命中**的别名条目，
    同一份 onnx 在索引里带两个身份、两个哈希。
    """

    def test_identity_prefers_provenance(self) -> None:
        recorded = {"robot": "go2", "policy_id": "go2-trained-1", "provenance": {"artifact_id": "go2__produced-run1"}}
        self.assertEqual("go2__produced-run1", pa.declaration_artifact_id(recorded))
        # 显式 artifact_id 最优先
        self.assertEqual("explicit", pa.declaration_artifact_id({**recorded, "artifact_id": "explicit"}))
        # 无血缘才派生
        self.assertEqual("go2__go2-trained-1", pa.declaration_artifact_id({"robot": "go2", "policy_id": "go2-trained-1"}))

    def test_merge_takes_lineage_from_produced_and_measurements_from_declaration(self) -> None:
        declared = {
            "artifact_id": "go2__produced-run1", "kind": "policies",
            "source_onnx": "assets/robots/go2/simulation/policies/a.onnx",   # 声明侧给仓库相对
            "onnx_sha256": "measured", "run_id": None,
        }
        produced = {
            "artifact_id": "go2__produced-run1", "kind": "produced",
            "run_id": "run1", "installed": {"robot": "go2", "package_path": "simulation/policies/a.onnx"},
            "onnx_sha256": "stale", "source_onnx": "simulation/policies/a.onnx",
        }
        merged = pa._merge_declaration_and_produced(declared, produced)
        self.assertEqual("produced", merged["kind"], "身份性质由血缘决定")
        self.assertEqual("run1", merged["run_id"], "血缘取 produced")
        self.assertEqual({"robot": "go2", "package_path": "simulation/policies/a.onnx"}, merged["installed"])
        self.assertEqual("measured", merged["onnx_sha256"], "实测取声明侧（刚扫出来的真值）")
        # 路径跟 produced：它必须与 installed.package_path 一致（B44 判据），声明侧是仓库相对
        self.assertEqual("simulation/policies/a.onnx", merged["source_onnx"])

    def test_landed_archive_keeps_lineage(self) -> None:
        """端到端回归：同名时**落盘**的档案也不能被声明侧覆盖。

        这正是本轮踩到的坑：``build_all`` 原先把声明侧 ``artifact.json`` 直接写进
        同名目录，produced 档案（``run_id`` / ``installed``）被覆盖后**永久丢失**。
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            robots, out = root / "robots", root / "policies"
            produced_id = "go2__produced-go2_v1_20260918_090509_476414"

            make_package(robots, "go2", policy_id="go2-trained-20260918-090509")
            config_path = robots / "go2" / "simulation" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["policies"][0]["provenance"] = {"artifact_id": produced_id}
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

            source = root / "final.onnx"
            source.write_bytes(b"produced-bytes")
            pa.promote_produced_policy(
                artifact_id=produced_id, onnx=source, deploy={"robot": "go2"},
                run_id="go2_v1_20260918_090509_476414", out_dir=out,
            )

            index = pa.build_all(robots_dir=robots, out_dir=out, write=True)
            ids = [item["artifact_id"] for item in index["artifacts"]]
            self.assertEqual([produced_id], ids, f"同一份产物只许有一个身份：{ids}")

            entry = index["artifacts"][0]
            self.assertEqual("produced", entry["kind"])
            self.assertEqual("go2_v1_20260918_090509_476414", entry["run_id"])

            on_disk = json.loads((out / produced_id / pa.ARTIFACT_NAME).read_text(encoding="utf-8"))
            self.assertEqual("produced", on_disk["kind"], "落盘档案的身份不能被声明侧覆盖")
            self.assertEqual("go2_v1_20260918_090509_476414", on_disk["run_id"], "血缘必须在")


class PromoteFromRunTest(unittest.TestCase):
    """L7「训练→导出→入库」的入库侧：证据链全取自 Run 档案，缺件如实报、不伪造。"""

    def _make_run(self, root: Path, *, status: str = "completed",
                  with_export: bool = True, with_snapshot: bool = True) -> Path:
        from types import SimpleNamespace

        from backend.training.runs import create_run_for_task

        run_dir = root / "task_20260914_000000_000000"
        contract = SimpleNamespace(robot_id="unitree_go2", compute_hash=lambda: "cafe1234")
        create_run_for_task(
            run_dir, contract=contract,
            config={"robot_id": "unitree_go2", "seed": 7, "num_envs": 16, "max_iterations": 5},
            task="training",
        )
        report: dict = {"status": status, "max_iterations": 5}
        if not with_export:
            report["onnx_export_error"] = "RuntimeError: adapter venv 缺少 onnx 包"
        (run_dir / "status.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        if with_export:
            (run_dir / "exported").mkdir()
            (run_dir / "exported" / "policy.onnx").write_bytes(b"produced-onnx-bytes")
        if with_snapshot:
            (run_dir / "contract_snapshot.json").write_text(
                json.dumps({
                    "observation": {"dimension": 45},
                    "action": {"dimension": 12, "joint_order": ["FL_hip_joint", "FR_hip_joint"]},
                }, ensure_ascii=False), encoding="utf-8",
            )
        return run_dir

    def test_promote_writes_produced_artifact_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "ws", Path(tmp) / "policies"
            run_dir = self._make_run(root)

            artifact = pa.promote_from_run(run_dir, out_dir=out)

            self.assertEqual("produced", artifact["kind"])
            self.assertEqual(run_dir.name, artifact["run_id"])
            self.assertEqual(pa.file_digest(out / artifact["artifact_id"] / "policy.onnx"),
                             artifact["onnx_sha256"], "hash 必须实测而非转抄")
            self.assertEqual(b"produced-onnx-bytes",
                             (out / artifact["artifact_id"] / "policy.onnx").read_bytes())
            # deploy 带血缘与快照里真实有的维度
            deploy_text = (out / artifact["artifact_id"] / "deploy.yaml").read_text(encoding="utf-8")
            self.assertIn(run_dir.name, deploy_text)
            self.assertIn("unitree_go2", deploy_text)
            self.assertIn("45", deploy_text)
            # 索引收录 produced 条目
            index = pa.load_index(out)
            self.assertIn(artifact["artifact_id"], index)

    def test_promote_is_idempotent_for_same_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "ws", Path(tmp) / "policies"
            run_dir = self._make_run(root)
            first = pa.promote_from_run(run_dir, out_dir=out)
            second = pa.promote_from_run(run_dir, out_dir=out)
            self.assertEqual(first["artifact_id"], second["artifact_id"])
            self.assertEqual(1, len(pa.load_index(out)), "同一 Run 重复入库不产生第二条索引")

    def test_promote_requires_completed_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "ws", Path(tmp) / "policies"
            run_dir = self._make_run(root, status="running")
            with self.assertRaisesRegex(RuntimeError, "状态为 running"):
                pa.promote_from_run(run_dir, out_dir=out)
            self.assertFalse(out.exists() and any(out.iterdir()), "失败路径不得落任何产物")
            # train 模式的完成态词表也要放行（worker 的 report 会把模板的 completed 覆盖掉）
            train_done = self._make_run(root / "ws2", status="train_completed")
            artifact = pa.promote_from_run(train_done, out_dir=out)
            self.assertEqual("produced", artifact["kind"])

    def test_promote_requires_export_and_reports_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "ws", Path(tmp) / "policies"
            run_dir = self._make_run(root, with_export=False)
            with self.assertRaisesRegex(FileNotFoundError, "导出失败|onnx_export_error"):
                pa.promote_from_run(run_dir, out_dir=out)

    def test_promote_requires_run_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "not_a_run"
            empty.mkdir()
            with self.assertRaisesRegex(FileNotFoundError, "run.json|Run 档案"):
                pa.promote_from_run(empty, out_dir=Path(tmp) / "policies")

    def test_build_all_regeneration_preserves_produced(self):
        """索引从声明整表重建 —— produced 条目必须跨重建保留，否则一次 build_all 就把它冲掉。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp), Path(tmp) / "policies"
            make_package(root, "go2")
            run_dir = self._make_run(root / "ws")
            artifact = pa.promote_from_run(run_dir, out_dir=out)
            self.assertIn(artifact["artifact_id"], pa.load_index(out))

            pa.build_all(robots_dir=root, out_dir=out, write=True)

            index = pa.load_index(out)
            self.assertIn(artifact["artifact_id"], index, "produced 条目被 build_all 冲掉了")
            self.assertIn("go2__walk-100", index, "声明条目仍在")

    def test_build_all_reports_id_collision_with_produced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp), Path(tmp) / "policies"
            make_package(root, "go2")
            run_dir = self._make_run(root / "ws")
            # 故意与声明条目同名：build_all 必须报冲突而不是静默二选一
            pa.promote_from_run(run_dir, artifact_id="go2__walk-100", out_dir=out)
            result = pa.build_all(robots_dir=root, out_dir=out, write=True)
            self.assertTrue(any("冲突" in str(p) for p in result["problems"]),
                            f"应报 ID 冲突，实得 problems={result['problems']}")

    def test_verify_counts_produced_and_detects_tampering(self):
        """produced 条目不做"悬空"判定，但对账实测其自完整性——被换内容必须红。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp), Path(tmp) / "policies"
            make_package(root, "go2")
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            artifact = pa.promote_from_run(self._make_run(root / "ws"), out_dir=out)

            v = pa.verify_artifacts(robots_dir=root, out_dir=out)
            self.assertTrue(v["ok"], v["problems"])
            self.assertEqual(2, v["checked"], "1 条声明 + 1 条 produced 都要被对账")
            self.assertEqual(1, v["declared"])
            self.assertEqual(2, v["indexed"])

            (out / artifact["artifact_id"] / "policy.onnx").write_bytes(b"tampered")
            v2 = pa.verify_artifacts(robots_dir=root, out_dir=out)
            self.assertFalse(v2["ok"])
            self.assertTrue(any("produced onnx 已变" in p for p in v2["problems"]), v2["problems"])


class RealRepoTest(unittest.TestCase):
    """真实仓库自检：声明数、onnx 实体数、影子产物。"""

    def test_repo_declarations_resolve_and_count_matches_blobs(self):
        """**B10 终态自检**：声明只留 `id`，解析一律经 `policies/index.json`。"""
        declarations = pa.scan_declarations()
        self.assertEqual(46, len(declarations), "本仓 8 机型应有 46 条策略声明（2026-09-30 实测：go2w 清理后 10 条，含上游原生 legs-only v0）")
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

        # 包内 41 个 onnx 实体（2026-09-23 实测；族架构收敛只留 8 机型后：
        # 59 → 41，删除的 18 个属于 microduck / tron1×3 / unitree_g1 / wuji_hand）。
        blobs = list(pa.iter_onnx_files())
        self.assertEqual(44, len(blobs), "包内 onnx 实体数（2026-09-30：+go2w legs-only 冒烟/产品两产物）")
        self.assertIsInstance(pa.unexported_onnx(), list)

    def test_artifact_ids_are_unique(self):
        ids = [pa.artifact_id_for(d["robot"], d["policy_id"]) for d in pa.scan_declarations()]
        self.assertEqual(len(ids), len(set(ids)), "产物 ID 必须唯一，否则出库会互相覆盖")


try:  # pragma: no cover - 环境相关
    import onnx as _onnx  # noqa: F401

    _ONNX_AVAILABLE = True
except ImportError:  # pragma: no cover - 控制面/最小环境
    _ONNX_AVAILABLE = False

_ONNX_REQUIRED = unittest.skipUnless(
    _ONNX_AVAILABLE,
    "onnx 未安装（B44 产物自证的量具）：pip install onnx（见 requirements-dev.txt / CI 安装行）",
)


class B44OnnxObsDimTest(unittest.TestCase):
    """B44：promote 链的 obs 真值 = **ONNX 图输入实测宽度**（产物自证），快照仅 fallback。

    背景：contract_snapshot 的 observation.dimension 是**部署视图**（go2=45，无
    base_lin_vel、命令在中间——真机 IMU 给不出线速度，E4 历史裁决），worker 导出的
    actor ONNX 吃的是**训练视图**（go2=48，base_lin_vel 打头、command 在帧尾）。
    照抄快照 = 训练图配部署宽度 ⇒ 评测器按声明 45 对实测 48 直接拒载（B44）。
    """

    @staticmethod
    def _write_onnx(path: Path, obs_width: int, *, input_name: str = "obs") -> None:
        import onnx
        from onnx import helper, TensorProto

        graph = helper.make_graph(
            [
                helper.make_node("Identity", ["obs"], ["actions"]),
            ],
            "policy",
            [helper.make_tensor_value_info(input_name, TensorProto.FLOAT, [1, obs_width])],
            [helper.make_tensor_value_info("actions", TensorProto.FLOAT, [1, 12])],
        )
        model = helper.make_model(graph, producer_name="b44-test")
        path.parent.mkdir(parents=True, exist_ok=True)
        onnx.save(model, str(path))

    def _make_run(self, root: Path, *, obs_width: int | None) -> Path:
        """复用 PromoteFromRunTest 的 Run 脚手架；obs_width=None 模拟"不可解析的 onnx"。"""
        from types import SimpleNamespace

        from backend.training.runs import create_run_for_task

        run_dir = root / "task_20260914_000000_000000"
        contract = SimpleNamespace(robot_id="unitree_go2", compute_hash=lambda: "cafe1234")
        create_run_for_task(
            run_dir, contract=contract,
            config={"robot_id": "unitree_go2", "seed": 7, "num_envs": 16, "max_iterations": 800},
            task="training",
        )
        (run_dir / "status.json").write_text(
            json.dumps({"status": "train_completed", "max_iterations": 800}), encoding="utf-8",
        )
        (run_dir / "exported").mkdir(parents=True, exist_ok=True)
        if obs_width is None:
            (run_dir / "exported" / "policy.onnx").write_bytes(b"not-a-real-onnx")
        else:
            self._write_onnx(run_dir / "exported" / "policy.onnx", obs_width)
        (run_dir / "contract_snapshot.json").write_text(
            json.dumps({
                "observation": {"dimension": 45},   # 部署视图（与 ONNX 实测 48 冲突）
                "action": {"dimension": 12, "joint_order": ["FL_hip_joint"]},
            }, ensure_ascii=False), encoding="utf-8",
        )
        return run_dir

    @_ONNX_REQUIRED
    def test_snapshot_conflict_yields_to_onnx_width(self):
        """快照说 45、ONNX 实测 48 ⇒ obs_dim=48 以实测为准，且如实标注来源与布局名。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "ws", Path(tmp) / "policies"
            artifact = pa.promote_from_run(self._make_run(root, obs_width=48), out_dir=out)
            self.assertEqual(48, artifact["obs_dim"])
            self.assertEqual("onnx", artifact["obs_dim_source"])
            self.assertEqual("go2_mjlab_actor_48", artifact["observation_kind"])
            deploy = (out / artifact["artifact_id"] / pa.DEPLOY_NAME).read_text(encoding="utf-8")
            self.assertIn("obs_dim: 48", deploy)
            self.assertIn("observation_kind: go2_mjlab_actor_48", deploy)
            self.assertIn("obs_dim_source: onnx", deploy)

    def test_unparseable_onnx_falls_back_to_snapshot_with_honest_source(self):
        """实测不到（onnx 缺 onnx 包/文件坏）⇒ fallback 快照并标注 contract_snapshot，不静默。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "ws", Path(tmp) / "policies"
            artifact = pa.promote_from_run(self._make_run(root, obs_width=None), out_dir=out)
            self.assertEqual(45, artifact["obs_dim"])
            self.assertEqual("contract_snapshot", artifact["obs_dim_source"])
            deploy = (out / artifact["artifact_id"] / pa.DEPLOY_NAME).read_text(encoding="utf-8")
            self.assertIn("obs_dim_source: contract_snapshot", deploy)

    @_ONNX_REQUIRED
    def test_unregistered_shape_gets_unknown_kind(self):
        """宽度实测到了但布局未取证 ⇒ observation_kind=unknown（B43 先例），不编造布局名。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "ws", Path(tmp) / "policies"
            artifact = pa.promote_from_run(self._make_run(root, obs_width=48), out_dir=out)
            # 上面的 run 造在 root（robot_id=unitree_go2）——换台未登记映射的机器人再看
        with tempfile.TemporaryDirectory() as tmp:
            from types import SimpleNamespace

            from backend.training.runs import create_run_for_task

            run_dir = Path(tmp) / "task_20260914_000000_000000"
            contract = SimpleNamespace(robot_id="unitree_go1", compute_hash=lambda: "cafe1234")
            create_run_for_task(
                run_dir, contract=contract,
                config={"robot_id": "unitree_go1", "seed": 7, "num_envs": 16, "max_iterations": 5},
                task="training",
            )
            (run_dir / "status.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            (run_dir / "exported").mkdir()
            self._write_onnx(run_dir / "exported" / "policy.onnx", 48)
            (run_dir / "contract_snapshot.json").write_text(json.dumps({}), encoding="utf-8")

            artifact = pa.promote_from_run(run_dir, out_dir=Path(tmp) / "policies")
            self.assertEqual(48, artifact["obs_dim"])
            self.assertEqual("unknown", artifact["observation_kind"])

    @_ONNX_REQUIRED
    def test_installed_declaration_carries_kind(self):
        """install 的声明组装：deploy 的 observation_kind 一并落进包内条目与 contract 块。

        走与 :class:`PromoteFromRunTest` 同一条组装路径（promote_from_run 内联在
        install=True 分支里组装 declaration dict），这里直接以同形 declaration 调
        ``install_produced_policy``（挂显式 robot_dir，不动仓库 assets）——评测器
        deep_merge 契约后按 contract.observation_kind 选帧构建器，缺了就拒载。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._make_run(root / "ws", obs_width=48)
            deploy = {
                "obs_dim": 48,
                "action_dim": 12,
                "observation_kind": "go2_mjlab_actor_48",
            }
            out = root / "policies"
            # 先入库一条 produced（与 promote_from_run 同参语义），再走 install
            artifact = pa.promote_from_run(run_dir, out_dir=out)
            robot_dir = root / "pkg" / "unitree_go2"
            (robot_dir / "simulation" / "config.json").parent.mkdir(parents=True)
            (robot_dir / "simulation" / "config.json").write_text(
                json.dumps({"policies": []}), encoding="utf-8",
            )
            installed = pa.install_produced_policy(
                artifact_id=artifact["artifact_id"],
                robot_dir=robot_dir,
                policy_id="unitree_go2-trained-test",
                declaration={
                    "label": f"训练产物（run {artifact['run_id']}）",
                    "obs_dim": deploy["obs_dim"],
                    "action_dim": deploy["action_dim"],
                    **({"observation_kind": deploy["observation_kind"]} if deploy.get("observation_kind") else {}),
                    "contract": {
                        **({"obs_dim": deploy["obs_dim"]} if deploy.get("obs_dim") else {}),
                        **({"action_dim": deploy["action_dim"]} if deploy.get("action_dim") else {}),
                        **({"observation_kind": deploy["observation_kind"]} if deploy.get("observation_kind") else {}),
                    } or None,
                },
                out_dir=out,
            )
            config = json.loads(
                (robot_dir / "simulation" / "config.json").read_text(encoding="utf-8"),
            )
            entry = config["policies"][0]
            self.assertEqual(48, entry["obs_dim"])
            self.assertEqual("go2_mjlab_actor_48", entry["observation_kind"])
            self.assertEqual(
                {"obs_dim": 48, "action_dim": 12, "observation_kind": "go2_mjlab_actor_48"},
                entry["contract"],
            )
            # 索引条目的 contract 同步带 kind（verify 对账口径）
            index = pa.load_index(out)
            self.assertEqual(
                "go2_mjlab_actor_48",
                index[artifact["artifact_id"]]["contract"]["observation_kind"],
            )
            _ = installed

    def test_real_repo_produced_entries_are_machine_independent(self):
        """**真实仓不变量（元数据层）**：索引里任何 ``source_onnx`` 都不得指向机器本地目录。

        索引是随仓跟踪/分发的文件：写 ``workspace/packages/...``（.gitignore）等于
        "生成它的那台机绿、别的机器全解析不到"——2026-09-19 实测 16 条 produced 条目
        （go2 15 + lite3 1）正是这种，且 Pack 的 ``policy_ref`` 是从这里派生的，
        于是一起烂（同一缺陷类的两个落点）。
        """

        from backend.pack_catalog import gitignored_ref_prefix

        offenders = []
        for entry in pa.load_index().values():
            source = str(entry.get("source_onnx") or "")
            if not source or source.startswith("/"):
                continue
            if gitignored_ref_prefix(source):
                offenders.append((entry["artifact_id"], source))
        self.assertEqual([], offenders, f"索引里出现机器本地路径：{offenders}")

        # 安装式条目必须同时留**包内相对**路径（解析侧据此按包根还原）
        for entry in pa.load_index().values():
            installed = entry.get("installed")
            if not isinstance(installed, dict):
                continue
            package_rel = str(installed.get("package_path") or "")
            with self.subTest(artifact=entry["artifact_id"]):
                self.assertTrue(package_rel.startswith("simulation/policies/"), package_rel)
                self.assertEqual(package_rel, str(entry.get("source_onnx")))

    @_ONNX_REQUIRED
    def test_real_repo_produced_entries_measure_correct(self):
        """**真实仓不变量（产物层）**：能解析到的 produced ONNX，实测宽度与声明一致、
        observation_kind 与注册表对齐（标准 PPO=48→go2_mjlab_actor_48；HIM=270→himloco_45_hist6）。

        只在 blob **本机可解析**时判：产物可能产在别的机器、没随仓分发（这是合法状态，
        元数据层的不变量由上面那条守——"没分发"与"路径写错"必须分得开）。
        可解析却对不上 = promote 链回归，必须红。
        """

        index = pa.load_index()
        kind_map = pa._OBSERVATION_KIND_BY_SHAPE
        measured_count = 0
        for entry in index.values():
            if entry.get("kind") != "produced":
                continue
            # 只判**声明完整**（robot + obs_dim）的条目：B44 之前的存量条目没有这两项，
            # 拿它们当判据会变成"测一个没声明的数"，没有意义；B44 之后 promote 必填。
            robot = str(entry.get("robot") or "")
            declared = entry.get("obs_dim")
            if not robot or declared is None:
                continue
            blob = pa.policy_blob_path({"artifact_id": entry["artifact_id"]}, index=index)
            if blob is None:
                continue
            measured = pa.onnx_obs_dim(blob)
            self.assertIsNotNone(measured, entry["artifact_id"])
            self.assertEqual(measured, declared, entry["artifact_id"])
            expected_kind = kind_map.get((robot, measured), "unknown")
            self.assertEqual(expected_kind, entry.get("observation_kind"), entry["artifact_id"])
            measured_count += 1
        # 兜底：本仓至少有一条"声明完整且可解析"的 produced（否则这条测试等于空跑）
        self.assertGreater(measured_count, 0, "没有可检验的 produced 产物——不变量没被真正检验")

    def test_deploy_kind_names_are_registered_builders(self):
        """**对齐口径守卫**：本模块登记/写出的每个 observation_kind 都必须是评测侧
        ``FRAME_BUILDERS`` 的键（或 unknown）——名字两边一漂，评测器就"不支持布局"拒载。"""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from adapters.mjlab.policy_acceptance import FRAME_BUILDERS

        for key in pa._OBSERVATION_KIND_BY_SHAPE.values():
            self.assertIn(key, FRAME_BUILDERS, f"{key} 不在评测侧注册表里")
        # unknown 是"宽度已知、布局未取证"的诚实标记，评测器按不支持如实报错
        self.assertEqual("unknown", pa.observation_kind_for("unitree_go1", 48))
        self.assertEqual("unknown", pa.observation_kind_for("unitree_go2", None))


class OnnxActionDimSelfCertTest(unittest.TestCase):
    """action_dim 的**ONNX 输出自证**（B44 输出侧对称，2026-09-30 go2w legs-only 首评实测驱动）。

    背景：快照的 action.dimension 是**包级动作面**（go2w 混合=16），legs-only 变体导出的
    actor 只吐 12——照抄快照就把 12 维策略配 16 维动作面，评测器 last_action 按 16 衬
    （帧 57≠53 拒）/ actuate 按 16 关节序映射 12 维动作（IndexError）。图输出宽度 +
    metadata ``joint_names``（执行关节序）是导出时刻唯一可靠的执行面真值。
    """

    LEGS = [
        "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
        "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
        "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
        "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
    ]

    def test_output_width_and_joint_names_self_certify(self):
        import onnx
        from onnx import helper, TensorProto

        work = Path(tempfile.mkdtemp(prefix="onnx-action-dim-"))
        try:
            graph = helper.make_graph(
                [helper.make_node("Identity", ["obs"], ["actions"])],
                "policy",
                [helper.make_tensor_value_info("obs", TensorProto.FLOAT, [1, 53])],
                [helper.make_tensor_value_info("actions", TensorProto.FLOAT, [1, 12])],
            )
            model = helper.make_model(graph, producer_name="action-dim-test")
            pair = model.metadata_props.add()
            pair.key, pair.value = "joint_names", ",".join(self.LEGS)
            blob = work / "policy.onnx"
            onnx.save(model, str(blob))

            self.assertEqual(12, pa.onnx_action_dim(blob))
            self.assertEqual("go2w_mjlab_legs_53", pa.observation_kind_for("unitree_go2w", 53))
            meta = pa.onnx_deploy_metadata(blob) or {}
            self.assertEqual(self.LEGS, meta.get("joint_names"))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_joint_names_width_mismatch_is_carried_not_trusted(self):
        """16 名 joint_names 配 12 维输出：解析层**如实带出**、deploy 层长度守卫不采信
        （采信了就是静默错位——守卫在 promote_from_run，这里钉解析+守卫的合约）。"""
        import onnx
        from onnx import helper, TensorProto

        work = Path(tempfile.mkdtemp(prefix="onnx-action-dim-"))
        try:
            graph = helper.make_graph(
                [helper.make_node("Identity", ["obs"], ["actions"])],
                "policy",
                [helper.make_tensor_value_info("obs", TensorProto.FLOAT, [1, 53])],
                [helper.make_tensor_value_info("actions", TensorProto.FLOAT, [1, 12])],
            )
            model = helper.make_model(graph, producer_name="action-dim-test")
            wheels = ["FR_wheel_joint", "FL_wheel_joint", "RR_wheel_joint", "RL_wheel_joint"]
            pair = model.metadata_props.add()
            pair.key, pair.value = "joint_names", ",".join([*self.LEGS, *wheels])
            blob = work / "policy.onnx"
            onnx.save(model, str(blob))

            meta = pa.onnx_deploy_metadata(blob) or {}
            self.assertEqual(16, len(meta.get("joint_names") or []))
            # deploy 层守卫：长度 ≠ 实测动作宽 ⇒ 不覆盖 action_joint_order
            deploy = {"action_dim": pa.onnx_action_dim(blob), "action_joint_order": []}
            meta_joint_names = meta.get("joint_names")
            if (meta_joint_names and deploy.get("action_dim") is not None
                    and len(meta_joint_names) == int(deploy["action_dim"])):
                deploy["action_joint_order"] = list(meta_joint_names)
            self.assertEqual([], deploy["action_joint_order"])
        finally:
            shutil.rmtree(work, ignore_errors=True)


class RealRepoB44StockTest(unittest.TestCase):
    """真实仓存量一致性：installed 声明的 obs_dim 与索引/实测三方一致。"""

    def test_installed_b44_family_declarations_agree_with_index(self):
        index = pa.load_index()
        for robot_dir in sorted(pa.ROBOTS_DIR.iterdir()):
            config_path = robot_dir / "simulation" / "config.json"
            if not config_path.is_file():
                continue
            for declaration in pa.scan_declarations(pa.ROBOTS_DIR):
                if declaration["robot"] != robot_dir.name:
                    continue
                provenance = declaration.get("provenance") or {}
                artifact_id = str(provenance.get("artifact_id") or "")
                entry = index.get(artifact_id)
                if entry is None or entry.get("kind") != "produced":
                    continue
                measured = pa.onnx_obs_dim(pa.ROOT / entry["source_onnx"]) if entry.get("source_onnx") else None
                if measured is None or measured == 1:
                    continue  # 不可实测的如实跳过（fallback 条目另有标注）
                declared = declaration.get("obs_dim")
                self.assertEqual(
                    measured, declared,
                    f"{artifact_id}: 包内声明 obs_dim={declared} vs ONNX 实测 {measured}",
                )


def _assets_recorded_index(repo: Path, artifact_id: str, source_onnx: str) -> dict[str, dict]:
    return {artifact_id: {"artifact_id": artifact_id, "kind": "asset", "source_onnx": source_onnx}}


class RuntimePackageFallbackTest(unittest.TestCase):
    """运行期包根优先回退：索引按源树记录的 blob，也要能在 workspace 副本包根上解析。

    病象（2026-09-20 P1③ 收尾实测）：id-only 终态（B10）＋索引按 `assets/robots/<pkg>/…`
    记录的组合里，`robot_dir` 是 workspace 副本时解析只回源树路径，
    `policy_relative_path` 求 `relative_to(副本)` 失败、而无 path 声明时的文件名猜谜
    （`simulation/policies/<policy_id>`）又命不中真实的下划线文件名 → browser-config
    把这些策略**整条静默丢掉**。源树 go2 全部 18 条 id-only 声明如此；老副本只因残留裸
    `path` 字段才没暴露，干净 clone 上必然复现。副本与源树 blob 由 C6 同步保证逐字节
    一致，故按"同一包内相对路径"在副本上命中时优先返回副本是安全的。
    """

    ONNX = b"onnx-bytes"

    def _repo_tree(self, tmp: Path, source_onnx: str) -> Path:
        repo = tmp / "repo"
        blob = repo / Path(source_onnx)
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(self.ONNX)
        return repo

    def _runtime_copy(self, tmp: Path, *, with_blob: bool = True) -> Path:
        copy = tmp / "workspace" / "packages" / "go2"
        if with_blob:
            policies = copy / "simulation" / "policies"
            policies.mkdir(parents=True)
            (policies / "walk.onnx").write_bytes(self.ONNX)
        return copy

    def test_assets_recorded_blob_resolves_into_runtime_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._repo_tree(root, "assets/robots/go2/simulation/policies/walk.onnx")
            copy = self._runtime_copy(root)
            artifact_id = pa.artifact_id_for("go2", "walk-100")
            index = _assets_recorded_index(repo, artifact_id, "assets/robots/go2/simulation/policies/walk.onnx")
            declaration = {"robot": "go2", "policy_id": "walk-100"}      # id-only 终态
            with unittest.mock.patch.object(pa, "ROOT", repo):
                blob = pa.policy_blob_path(declaration, robot_dir=copy, index=index)
                self.assertEqual(
                    copy / "simulation" / "policies" / "walk.onnx", blob.resolve(),
                    "源树记录的 blob 应解析到运行期副本（而非源树），serv 层才能给出包内 URL",
                )
                self.assertEqual(
                    "simulation/policies/walk.onnx",
                    pa.policy_relative_path(declaration, robot_dir=copy, index=index),
                )

    def test_copy_missing_blob_falls_back_to_source_tree(self):
        """副本上没有该 blob（干净 clone / 用户删过）：回源树路径，旧行为不变。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._repo_tree(root, "assets/robots/go2/simulation/policies/walk.onnx")
            copy = self._runtime_copy(root, with_blob=False)
            artifact_id = pa.artifact_id_for("go2", "walk-100")
            index = _assets_recorded_index(repo, artifact_id, "assets/robots/go2/simulation/policies/walk.onnx")
            declaration = {"robot": "go2", "policy_id": "walk-100"}
            with unittest.mock.patch.object(pa, "ROOT", repo):
                blob = pa.policy_blob_path(declaration, robot_dir=copy, index=index)
                self.assertEqual(repo / "assets/robots/go2/simulation/policies/walk.onnx", blob)
                self.assertIsNone(pa.policy_relative_path(declaration, robot_dir=copy, index=index))

    def test_robot_dir_absent_keeps_source_tree_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._repo_tree(root, "assets/robots/go2/simulation/policies/walk.onnx")
            artifact_id = pa.artifact_id_for("go2", "walk-100")
            index = _assets_recorded_index(repo, artifact_id, "assets/robots/go2/simulation/policies/walk.onnx")
            with unittest.mock.patch.object(pa, "ROOT", repo):
                self.assertEqual(
                    repo / "assets/robots/go2/simulation/policies/walk.onnx",
                    pa.policy_blob_path({"robot": "go2", "policy_id": "walk-100"}, index=index),
                )

    def test_recordings_outside_assets_robots_are_not_remapped(self):
        """`assets/robots` 之外的记录（如仓库根的 `policies/<id>/policy.onnx`）不重映射进包根。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._repo_tree(root, "policies/go2__walk-100/policy.onnx")
            copy = self._runtime_copy(root)
            (copy / "policies" / "go2__walk-100").mkdir(parents=True)
            (copy / "policies" / "go2__walk-100" / "policy.onnx").write_bytes(b"decoy")
            artifact_id = pa.artifact_id_for("go2", "walk-100")
            index = _assets_recorded_index(repo, artifact_id, "policies/go2__walk-100/policy.onnx")
            with unittest.mock.patch.object(pa, "ROOT", repo):
                self.assertEqual(
                    repo / "policies/go2__walk-100/policy.onnx",
                    pa.policy_blob_path({"robot": "go2", "policy_id": "walk-100"}, robot_dir=copy, index=index),
                    "诱饵文件不得被选中：这类记录按仓库根解析，与包根无关",
                )

    def test_package_relative_component_is_stripped_exactly_once(self):
        """只剥"源树根"会多带一层 `<包目录>/`：钉住 strip 掉包目录本身。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._repo_tree(root, "assets/robots/go2/simulation/policies/nested/deep/walk.onnx")
            copy = self._runtime_copy(root)
            (copy / "simulation" / "policies" / "nested" / "deep").mkdir(parents=True)
            (copy / "simulation" / "policies" / "nested" / "deep" / "walk.onnx").write_bytes(self.ONNX)
            artifact_id = pa.artifact_id_for("go2", "walk-100")
            index = _assets_recorded_index(
                repo, artifact_id, "assets/robots/go2/simulation/policies/nested/deep/walk.onnx",
            )
            with unittest.mock.patch.object(pa, "ROOT", repo):
                blob = pa.policy_blob_path({"robot": "go2", "policy_id": "walk-100"}, robot_dir=copy, index=index)
                self.assertEqual(copy / "simulation/policies/nested/deep/walk.onnx", blob)


class RealRepoRuntimeCopyTest(unittest.TestCase):
    """真实仓库自检（2026-09-20 P1③ 收尾）：源树 id-only 声明必须在副本包根上解析出包内路径。

    这是上面那条病的线上形态：browser-config 以 D7/C6 解析出的 workspace 副本为包根读
    `simulation/config.json`，而声明全是 id-only、索引按源树记录 —— 任何一条解析不出
    "包内路径"，浏览器里就少一个可选策略。断言同时检查 blob 字节可达（副本上真实存在）。
    """

    def test_source_side_declarations_resolve_against_runtime_copy(self):
        from backend.package_locator import resolve_package_root

        index = pa.load_index()
        unresolved = []
        for robot_id in ("unitree_go2",):
            copy = resolve_package_root(robot_id)
            config_path = Path(pa.ROBOTS_DIR) / robot_id / "simulation" / "config.json"
            declared = json.loads(config_path.read_text(encoding="utf-8-sig")).get("policies") or []
            for item in declared:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                relative = pa.policy_relative_path(item, robot_dir=copy, index=index)
                if not relative or not (copy / relative).is_file():
                    unresolved.append(str(item.get("id")))
        self.assertEqual([], unresolved, "源树声明须在 workspace 副本上解析出可下载的包内路径")


if __name__ == "__main__":
    unittest.main()
