"""训练产物回挂（2026-09-16）：产物 → 包内策略条目 → `Pack.policy_ref`。

## 这组测试守的是什么

闭环的最后一环此前是断的（实测取证）：训练产出的 onnx 躺在 `policies/<artifact_id>/` 里，
**包内配置里没有它的条目、Pack 的 `policy_ref` 是 null** —— 于是

* 浏览器看不到它（`simulation_api` 对"解析不到包内 blob"的条目连 URL 都不编）；
* 无头侧 `--policy-id` 找不到它（`policy_acceptance.py` 与 B12 产出端都按包内配置解析）；
* Bundle 里它只能记 `bound_entry=null`。

* 修法是三件：产物记 `robot`/`policy_id` 绑定 → **安装进包**（真副本搬进
  `simulation/policies/`，出库目录改成引用式，维持"一个策略字节只存一处"）→ Pack 回写 `policy_ref`。
* 另外钉住两条纪律：**包内资产文件的写入必须原子**（`simulation/config.json` 是手工维护过的），
  **生成器不得冲掉回挂**（否则下一次 `generate_packs.py` 就把产品数据静默抹了）。
"""

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

from backend import policy_artifacts as pa  # noqa: E402
from backend.policy_artifacts import file_digest  # noqa: E402

ONNX_BYTES = b"fake-onnx-bytes-for-attach-tests" * 8


def _load_tool(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relative))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AttachFixture(unittest.TestCase):
    """临时包 + 临时出库目录（**绝不动仓库里的 assets/packs**）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="attach-")
        root = Path(self._tmp.name)
        self.package = root / "assets" / "robots" / "demo_bot"
        (self.package / "simulation" / "policies").mkdir(parents=True)
        self.config_path = self.package / "simulation" / "config.json"
        self.config_path.write_text(
            json.dumps({"schema_version": "simulation-config-1.0", "policies": [{"id": "upstream-a"}]}, indent=2),
            encoding="utf-8",
        )
        self.out_dir = root / "policies"
        self.artifact_id = "demo_bot__produced-demo-run"
        source = root / "exported" / "policy.onnx"
        source.parent.mkdir(parents=True)
        source.write_bytes(ONNX_BYTES)
        artifact = pa.promote_produced_policy(
            artifact_id=self.artifact_id,
            onnx=source,
            deploy={"robot": "demo_bot", "policy_id": self.artifact_id},
            run_id="demo_bot_contract_v1_20260916_101500_000001",
            out_dir=self.out_dir,
            robot="demo_bot",
            policy_id="demo_bot-trained-20260916-101500",
        )
        pa.write_out_index(self.out_dir, upsert=[artifact])
        self.policy_id = "demo_bot-trained-20260916-101500"

    def tearDown(self):
        self._tmp.cleanup()

    def install(self, **overrides):
        payload = {
            "artifact_id": self.artifact_id,
            "robot_dir": self.package,
            "policy_id": self.policy_id,
            "declaration": {"obs_dim": 53, "action_dim": 16, "label": "演示训练产物"},
            "out_dir": self.out_dir,
        }
        payload.update(overrides)
        return pa.install_produced_policy(**payload)


class InstallProducedPolicyTest(AttachFixture):
    def test_installs_blob_into_package_and_declares_entry(self):
        result = self.install()
        installed = self.package / "simulation" / "policies" / f"{self.policy_id}.onnx"
        self.assertTrue(installed.is_file())
        self.assertEqual(ONNX_BYTES, installed.read_bytes())

        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        entry = next(item for item in config["policies"] if item["id"] == self.policy_id)
        self.assertEqual(f"simulation/policies/{self.policy_id}.onnx", entry["path"])
        self.assertEqual(53, entry["obs_dim"])
        self.assertEqual("演示训练产物", entry["label"])
        # 既有条目不动
        self.assertTrue(any(item["id"] == "upstream-a" for item in config["policies"]))
        # provenance：自产还是上游导入必须一眼可查（V1）
        self.assertEqual("product-training", entry["provenance"]["origin"])
        self.assertEqual(self.artifact_id, entry["provenance"]["artifact_id"])

    def test_artifact_becomes_reference_style_single_copy(self):
        """装进包后出库目录**不再持副本**（source_onnx 指包内），否则同一份字节存了两处。"""

        result = self.install()
        artifact = result["artifact"]
        self.assertFalse((self.out_dir / self.artifact_id / "policy.onnx").exists())
        self.assertTrue(str(artifact["source_onnx"]).endswith(f"simulation/policies/{self.policy_id}.onnx"))
        self.assertEqual(file_digest(self.package / "simulation" / "policies" / f"{self.policy_id}.onnx"),
                         artifact["onnx_sha256"])
        self.assertEqual(self.policy_id, artifact["installed"]["policy_id"])
        self.assertIsNotNone(result["removed_local_blob"])

    def test_policy_id_now_resolves_to_the_installed_blob(self):
        """**这就是回挂的意义**：包内声明 + 统一解析器 ⇒ 按 id 能解析到包内文件。

        浏览器/验收/无头产出端/Bundle 都走这一条解析（`policy_blob_path`）。
        """

        self.install()
        entry = json.loads(self.config_path.read_text(encoding="utf-8"))["policies"][-1]
        resolved = pa.policy_blob_path(entry, robot_dir=self.package, index=pa.load_index(self.out_dir))
        self.assertIsNotNone(resolved, entry)
        assert resolved is not None
        self.assertEqual(self.package.resolve() / f"simulation/policies/{self.policy_id}.onnx", resolved.resolve())

    def test_install_is_idempotent(self):
        self.install()
        self.install()
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(1, sum(1 for item in config["policies"] if item["id"] == self.policy_id))

    def test_unknown_artifact_is_rejected(self):
        with self.assertRaises(ValueError):
            self.install(artifact_id="no-such-artifact")

    def test_non_package_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                self.install(robot_dir=tmp)

    def test_config_write_is_atomic(self):
        """写包内资产文件不留半截：临时文件不得残留。"""

        self.install()
        leftovers = list((self.package / "simulation").glob("*.tmp"))
        self.assertEqual([], leftovers)

    @property
    def tmp_source(self):
        return self.out_dir / self.artifact_id / "policy.onnx"


class AttachPolicyToPackTest(AttachFixture):
    def _packs_dir(self, root: Path, morphology_id: str = "demo_bot") -> Path:
        packs = root / "packs"
        packs.mkdir(parents=True, exist_ok=True)
        (packs / f"{morphology_id}.pack.json").write_text(
            json.dumps({
                "schema_version": "capability-pack-1.0",
                "pack_id": f"{morphology_id}-velocity",
                "morphology_ref": {"id": morphology_id},
                "skill_ref": {"id": "velocity_base"},
                "policy_ref": None,
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return packs

    def test_pack_policy_ref_is_written_with_hash(self):
        self.install()
        packs = self._packs_dir(Path(self._tmp.name))
        result = pa.attach_policy_to_pack("demo_bot", artifact_id=self.artifact_id,
                                          out_dir=self.out_dir, packs_dir=packs)
        ref = result["policy_ref"]
        self.assertEqual(self.artifact_id, ref["id"])
        self.assertEqual(self.policy_id, ref["version"])
        self.assertTrue(str(ref["path"]).endswith(f"simulation/policies/{self.policy_id}.onnx"))
        target = ROOT / ref["path"] if not Path(ref["path"]).is_absolute() else Path(ref["path"])
        if target.is_file():
            self.assertEqual(file_digest(target), ref["sha256"])

    def test_missing_pack_is_rejected(self):
        self.install()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                pa.attach_policy_to_pack("demo_bot", artifact_id=self.artifact_id,
                                         out_dir=self.out_dir, packs_dir=Path(tmp))


class BundleBindingTest(AttachFixture):
    def test_bundle_placement_binds_the_entry_after_install(self):
        """装进包之后，Bundle 的策略落点解析出 `bound_entry`（不再 `null`）。"""

        from backend import bundle_export as bx

        self.install()
        metadata_prefix, onnx_path, bound_entry = bx._policy_placement(
            self.package, self.artifact_id, out_dir_index=self.out_dir,
        )
        self.assertEqual("policy/", metadata_prefix)
        self.assertEqual(f"simulation/policies/{self.policy_id}.onnx", onnx_path)
        self.assertEqual(self.policy_id, bound_entry)


class GeneratePacksPreservesAttachTest(unittest.TestCase):
    """生成器**不得冲掉**回挂的 `policy_ref`（否则一次重生成就静默抹掉产品数据）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="gen-")
        root = Path(self._tmp.name)
        self.robots = root / "assets" / "robots"
        (self.robots / "demo_bot").mkdir(parents=True)
        (self.robots / "demo_bot" / "contract_v3.json").write_text(
            json.dumps({"robot_id": "demo_bot", "family": "Demo", "morphology": {"id": "demo_bot"}}),
            encoding="utf-8",
        )
        self.out = root / "packs"
        self.module = _load_tool("generate_packs_under_test", "tools/generate_packs.py")

    def tearDown(self):
        self._tmp.cleanup()

    def _generate(self):
        return self.module.main(["--robots", str(self.robots), "--out", str(self.out)])

    def test_policy_ref_survives_regeneration(self):
        self.assertEqual(0, self._generate())
        pack_path = self.out / "demo_bot.pack.json"
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        self.assertIsNone(pack["policy_ref"])

        ref = {"id": "demo_bot__produced-x", "path": "assets/robots/demo_bot/simulation/policies/demo.onnx",
               "sha256": "a" * 64}
        pack["policy_ref"] = ref
        pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        self.assertEqual(0, self._generate())
        regenerated = json.loads(pack_path.read_text(encoding="utf-8"))
        self.assertEqual(ref, regenerated["policy_ref"], "重生成把回挂冲掉了")

    def test_existing_policy_ref_helper_ignores_empty_ids(self):
        self.out.mkdir(parents=True, exist_ok=True)
        pack_path = self.out / "demo_bot.pack.json"
        pack_path.write_text(json.dumps({"policy_ref": {"id": ""}}), encoding="utf-8")
        self.assertIsNone(self.module.existing_policy_ref(self.robots / "demo_bot", self.out))


if __name__ == "__main__":
    unittest.main()
