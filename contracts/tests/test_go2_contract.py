import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from contracts import load_robot_contract


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "go2.v1.json"
WORKSPACE = Path(__file__).resolve().parents[3]

#: v1 契约的证据全部来自**仓库之外的上游快照**（当初与这些目录并列开发）。
#: 它们不在本仓库里，哈希无法在此复算——**登记**它们，而不是把测试删掉：
#: ① 出现未登记的根 → 失败（防止"证据来源被悄悄换掉"）；
#: ② 在仓库内的证据 → 必须存在且哈希逐字节一致。
EXTERNAL_EVIDENCE_ROOTS = ("lain_job/", "kaiwu_rl/", "uni_rl/")
#: 6 条证据（lain_job / kaiwu_rl / uni_rl）**已全部补进仓库**（现在 `00_resources/<project>/...` 下
#: 逐字节可核），因此"外部"计数归 0 —— 这正是本断言在自己报错信息里要求的动作：
#: 「证据补进仓库时，请同步更新本断言」。哈希逐字节校验（本用例的强部分）保持不变。
EXTERNAL_EVIDENCE_COUNT = 0


class Go2ContractTest(unittest.TestCase):
    def test_load_go2_contract_fixture(self) -> None:
        contract = load_robot_contract(FIXTURE)

        self.assertEqual(contract.robot_id, "unitree_go2")
        self.assertEqual(contract.model_revision, "go2-joint-map-v1")
        self.assertEqual(len(contract.joints.canonical_order), 12)
        self.assertEqual(contract.joints.training_indices, list(range(12)))
        self.assertEqual(contract.joints.mujoco_indices, list(range(7, 19)))
        self.assertEqual(
            contract.joints.deploy_indices,
            [3, 4, 5, 0, 1, 2, 9, 10, 11, 6, 7, 8],
        )
        self.assertIsNone(contract.joints.direction_multipliers)
        self.assertIsNone(contract.physics_hz)
        self.assertEqual(contract.control_hz, 50)

    def test_go2_evidence_files_match_hashes(self) -> None:
        """证据要么在仓库内且哈希一致，要么属于**已登记的外部快照根**（缺失数固定）。"""

        contract = load_robot_contract(FIXTURE)
        external = 0
        for evidence in contract.evidence:
            normalized = str(evidence.path).replace("\\", "/")
            source = WORKSPACE / evidence.path
            if source.is_file():
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                    evidence.sha256,
                    f"仓库内证据 {evidence.path} 与登记的 sha256 不一致",
                )
                continue
            with self.subTest(path=evidence.path):
                self.assertTrue(
                    normalized.startswith(EXTERNAL_EVIDENCE_ROOTS),
                    f"{evidence.path} 既不在仓库内，也不属于已登记的外部快照根——"
                    f"证据来源不许悄悄改变（登记表见 EXTERNAL_EVIDENCE_ROOTS）",
                )
            external += 1
        self.assertEqual(
            external,
            EXTERNAL_EVIDENCE_COUNT,
            "外部队列数量与登记不符：上游快照被换掉、或证据补进仓库时，请同步更新本断言",
        )

    def test_invalid_go2_contract_fails(self) -> None:
        cases = [
            (lambda data: data["joints"].update(training_indices=[0]), "training_indices"),
            (lambda data: data.update(default_pose=[0.0]), "default_pose length"),
            (lambda data: data["evidence"][0].update(sha256="bad"), "sha256"),
        ]
        for mutate, error in cases:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                data = json.loads(FIXTURE.read_text(encoding="utf-8"))
                mutate(data)
                invalid = Path(directory) / "invalid.json"
                invalid.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(ValidationError, error):
                    load_robot_contract(invalid)


if __name__ == "__main__":
    unittest.main()
