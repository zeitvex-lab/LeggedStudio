import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from contracts import load_robot_contract
from contracts.validator import normalized_sha256


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "go2.v1.json"
#: 仓库根（`contracts/tests/` → `contracts/` → 仓库根）。
REPO_ROOT = Path(__file__).resolve().parents[2]

#: v1 契约的证据全部来自**仓库之外的上游快照**（当初与这些目录并列开发，路径里不带
#: `00_resources/` 前缀）。它们不在本仓库里，冻结哈希无法在此复算——**登记**它们，
#: 而不是把测试删掉：
#: ① 解析落在候选根之外 → 失败（防止"证据来源被悄悄换掉"，登记表见 EXTERNAL_EVIDENCE_ROOTS）；
#: ② 命中的文件若与冻结哈希一致 → 逐字节强校验（同修订）；
#: ③ 命中但属于**已登记的不同修订**（见 IN_REPO_DIFFERENT_REVISION）→ 登记差异、不重签冻结哈希。
#:
#: 2026-09-16 修正（云开发容器/CI 首跑暴露）：原实现把候选根写成 `parents[3]`（仓库的**父**
#: 目录）并把"外部计数"钉成 0，注释声称"6 条已补进仓库、逐字节可核"——实测**不成立**：
#: `00_resources/<path>` 下 6 条全部存在但**哈希逐条不同**（既非原始字节口径、也非
#: CRLF→LF 归一口径，是**上游快照的不同修订**）。于是本用例只在"作者机器上恰好还留着
#: 那批并列目录"时通过，在任何干净检出（CI）上恒红 —— 与任务清单 B39 同族。
#: 现改为**仓库内确定化解析**（候选根与平台无关），并把差异如实登记。
EXTERNAL_EVIDENCE_ROOTS = ("lain_job/", "kaiwu_rl/", "uni_rl/")
#: 解析候选根（按顺序取第一个存在的）：仓库内历史布局 → 入库快照落点。
EVIDENCE_ROOTS = (REPO_ROOT, REPO_ROOT / "00_resources")

#: 已登记的"入库副本 = 不同修订"清单（只登记**路径**，不重签冻结哈希）。
#:
#: **2026-09-17 清空并重签（修正 2026-09-16 的误诊）**：当时把"冻结哈希 ≠ 入库副本哈希"
#: 判成了"上游快照的不同修订"；2026-09-17 复测发现那 6 条的差异**逐条恰好等于
#: CRLF→LF 归一差**（下表"入库"值 = 归一哈希）——是**行尾口味差**，不是内容差。
#: 根因与 B39 同族：冻结哈希当年在 Windows 工作树按 CRLF 字节烤入，git blob 是 LF，
#: 于是"匹配与否"随检出平台翻转（本机全匹配、CI 全不匹配 ⇒ 登记清单只在一边成立）。
#: 处置：**6 条证据哈希全部重签为归一口径**（`contracts.validator.normalized_sha256`，
#: 与 validator / pack_catalog / generate_packs 同口径），比对也改归一——任何机器、任何
#: 检出方式下逐字节同判。登记清单随之清空；漂移守卫保持：今后内容真被换过 ⇒ 归一哈希
#: 必然不符 ⇒ 无登记的差异照旧判红。
IN_REPO_DIFFERENT_REVISION: frozenset = frozenset()

#: 候选根都找不到的证据条数（仓库内确定化解析后：每台机器都是 0，故不再随机器漂）。
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
        """证据要么在仓库内且哈希一致（或属**已登记的不同修订**），要么属**已登记的外部快照根**。"""

        contract = load_robot_contract(FIXTURE)
        external = 0
        different_revision: set[str] = set()
        for evidence in contract.evidence:
            normalized = str(evidence.path).replace("\\", "/")
            source = next(
                (root / evidence.path for root in EVIDENCE_ROOTS if (root / evidence.path).is_file()),
                None,
            )
            if source is not None:
                # 归一口径比对（2026-09-17）：冻结哈希已重签为 CRLF→LF 归一值，
                # 原始字节比对会随检出平台（autocrlf）翻转——见 IN_REPO_DIFFERENT_REVISION 的订正说明。
                actual = normalized_sha256(source.read_bytes())
                if actual == evidence.sha256:
                    continue  # 同修订：逐字节强校验通过
                self.assertIn(
                    normalized,
                    IN_REPO_DIFFERENT_REVISION,
                    f"仓库内证据 {evidence.path} 与登记的 sha256 不一致，且不在「已登记的不同修订」清单里"
                    f"（实测 {actual[:16]}… vs 冻结 {str(evidence.sha256)[:16]}…）——"
                    f"证据来源不许悄悄改变；若确为上游快照换版，请登记进 IN_REPO_DIFFERENT_REVISION",
                )
                different_revision.add(normalized)
                continue
            with self.subTest(path=evidence.path):
                self.assertTrue(
                    normalized.startswith(EXTERNAL_EVIDENCE_ROOTS),
                    f"{evidence.path} 既不在仓库候选根 {[str(r) for r in EVIDENCE_ROOTS]} 下，"
                    f"也不属于已登记的外部快照根——证据来源不许悄悄改变"
                    f"（登记表见 EXTERNAL_EVIDENCE_ROOTS）",
                )
            external += 1
        self.assertEqual(
            external,
            EXTERNAL_EVIDENCE_COUNT,
            "外部队列数量与登记不符（仓库内确定化解析后应为 0）：候选根被改动、或证据被移出仓库",
        )
        self.assertEqual(
            different_revision,
            set(IN_REPO_DIFFERENT_REVISION),
            "「已登记的不同修订」清单与实际对不上：清单里的路径已消失/已回到同修订，"
            "或出现了未登记的差异 —— 两侧必须一起改",
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
