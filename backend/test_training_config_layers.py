"""B13 终态收口：``training/config.json`` 必须退化为**纯指针文件**（唯一豁免：microduck）。

## 这组测试守的是什么

三层拆分（物理→契约 / 任务→Recipe / 运行→Run）落地后，各包 `training/config.json` 的终态
是只含指针字段 `{robot_id, contract_path, profile_id, schema_version, backend}` 的引用文件。
本文件钉三件事：

1. **全仓不变量**：14 个内置包里，除 microduck 外，每份 config.json 的键集 ⊆ 指针字段集
   （即使不与 profile 同名、没有任何代码读，残留也不允许——go2 曾残留的 `reward_scales`
   就是这类）；
2. **豁免边界**：microduck 的残留键恰好等于已登记待取证的 11 个元数据字段——登记清单在
   测试里**独立钉死**（防新字段悄悄混入豁免伞下、也防登记清单悄悄扩容）；
3. **审计函数语义**：用假包目录（tmp 根）单测 `audit()` / `exit_code()`——合法指针、带残留、
   microduck 式豁免、无 profile 各造一份，断言报告内容与门禁退出码
   （非豁免残留或双写任一出现 → exit 1）。

风格：纯 pytest 兼容的 unittest.TestCase（CI 的 ``unittest discover`` 与本地
``python -m pytest`` 双口径可跑）、仅标准库、直读文件。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_training_config_layers import (
    POINTER_FIELDS,
    REGISTERED_PENDING_EVIDENCE,
    audit,
    exit_code,
)

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"

#: microduck 已登记「待单独取证」的 11 个元数据字段（00_know/01_任务清单.md B13 行）。
#: 刻意**不**从工具里 import——登记清单本身也要被钉住，工具侧偷偷扩容/缩水同样算红。
MICRODUCK_REGISTERED_FIELDS = {
    "framework",
    "source_project",
    "default_profile",
    "runtime_requirements",
    "observation_dim",
    "action_dim",
    "action_scale",
    "control",
    "episode_length_s",
    "command_curriculum",
    "default_runner",
}


def _config_keys(robot: str) -> set[str]:
    """直读某内置包的 config.json 顶层键集。"""
    path = ROBOTS / robot / "training" / "config.json"
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return set(value.keys())


class RepoPointerInvariantTest(unittest.TestCase):
    """全仓不变量：除 microduck 外，每份 config.json 都是纯指针文件。"""

    def _builtin_robots(self) -> list[str]:
        return sorted(
            d.name for d in ROBOTS.iterdir()
            if d.is_dir() and (d / "training" / "config.json").exists()
        )

    def test_14_builtin_packages_present(self):
        """内置包清单钉在 14（B1 口径）；增删包是有意动作，须连同本测试一起改。"""
        self.assertEqual(14, len(self._builtin_robots()))

    def test_config_is_pointer_only_except_microduck(self):
        """键集 ⊆ 指针字段集；失败信息列出具体包与多出来的键。"""
        violations: dict[str, list[str]] = {}
        for robot in self._builtin_robots():
            if robot == "microduck":  # 唯一豁免，边界单独钉（见 MicroduckExemptionTest）
                continue
            extra = sorted(_config_keys(robot) - POINTER_FIELDS)
            if extra:
                violations[robot] = extra
        self.assertEqual(
            {}, violations,
            "这些包的 training/config.json 残留指针外字段（终态 = 纯指针文件），"
            "应归位任务层（Recipe/ profile）或运行层（Run）后删除",
        )


class MicroduckExemptionTest(unittest.TestCase):
    """豁免边界：microduck 的残留必须**恰好**等于登记的 11 个字段。"""

    def test_microduck_residue_exactly_matches_registered_fields(self):
        residue = _config_keys("microduck") - POINTER_FIELDS
        self.assertEqual(
            sorted(MICRODUCK_REGISTERED_FIELDS), sorted(residue),
            "microduck 的 config.json 残留键与登记清单不一致：新字段混入豁免伞下，"
            "或登记字段已被清理——两种情况都须显式更新登记与测试，不允许静默漂移",
        )

    def test_tool_registry_matches_registered_fields(self):
        """工具的豁免注册表与登记清单一致（豁免范围本身不许漂移）。"""
        self.assertEqual(
            MICRODUCK_REGISTERED_FIELDS,
            REGISTERED_PENDING_EVIDENCE["microduck"]["fields"],
        )


class AuditFunctionTest(unittest.TestCase):
    """audit()/exit_code() 单测：tmp_path 式假包目录，逐条钉报告内容与门禁退出码。"""

    POINTER_CONFIG = {
        "robot_id": "robot_a",
        "contract_path": "assets/robots/robot_a/contract.json",
        "profile_id": "a-flat",
        "schema_version": "training-config-1.0",
        "backend": "native_mjlab",
    }

    @staticmethod
    def _package(root: Path, robot: str, config: dict, profiles: dict[str, dict] | None = None) -> None:
        training = root / robot / "training"
        training.mkdir(parents=True, exist_ok=True)
        (training / "config.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8",
        )
        if profiles:
            (training / "profiles").mkdir(exist_ok=True)
            for name, body in profiles.items():
                (training / "profiles" / f"{name}.json").write_text(
                    json.dumps(body, ensure_ascii=False), encoding="utf-8",
                )

    def test_clean_pointer_package_passes(self):
        """合法指针包 → 无双写、无残留、exit 0；与 profile 同名的**指针字段**不算双写。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a", dict(self.POINTER_CONFIG),
                profiles={"a-flat": {"profile_id": "a-flat", "backend": "native_mjlab",
                                     "task_name": "forward_walk"}},
            )
            report = audit(robots_dir=root)
            self.assertEqual(1, report["total"])
            self.assertEqual([], report["with_dup"])
            self.assertEqual([], report["with_residue"])
            self.assertEqual(0, exit_code(report))

    def test_residue_key_is_flagged_even_without_profile_counterpart(self):
        """指针外残留即使不与 profile 同名（无任何覆盖）也判红——终态收口的核心语义。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = dict(self.POINTER_CONFIG, reward_scales={"track_lin_vel": 1.0})
            self._package(root, "robot_a", config, profiles={"a-flat": {"profile_id": "a-flat"}})
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["with_residue"]))
            self.assertEqual(["reward_scales"], report["with_residue"][0]["residue"])
            self.assertEqual([], report["with_dup"])
            self.assertEqual(1, exit_code(report))

    def test_dup_key_is_flagged(self):
        """与 profile 同名的非指针字段 = 双写，判红。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                dict(self.POINTER_CONFIG, task_name="forward_walk"),
                profiles={"a-flat": {"profile_id": "a-flat", "task_name": "forward_walk"}},
            )
            report = audit(robots_dir=root)
            self.assertEqual([["task_name"]], [r["dup_keys"] for r in report["with_dup"]])
            self.assertEqual(1, exit_code(report))

    def test_exempt_package_with_registered_fields_passes(self):
        """microduck 式豁免：登记内的 11 字段如实列进 exempt_residue，不判红。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"robot_id": "microduck", "schema_version": "training-config-1.0",
                      "backend": "native_mjlab", "framework": "mjlab",
                      "observation_dim": 61, "action_dim": 14, "action_scale": 1.0}
            self._package(root, "microduck", config, profiles={"m-flat": {"profile_id": "m-flat"}})
            report = audit(robots_dir=root)
            self.assertEqual([], report["with_residue"])
            self.assertEqual(["action_dim", "action_scale", "framework", "observation_dim"],
                             report["exempt_residue"][0]["exempt_residue"])
            self.assertEqual(0, exit_code(report))

    def test_exempt_package_with_unregistered_new_field_is_flagged(self):
        """豁免包混入登记外的新键 → 照判残留（防新字段悄悄溜进豁免伞下）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"robot_id": "microduck", "framework": "mjlab",
                      "brand_new_metadata": {"nested": True}}
            self._package(root, "microduck", config, profiles={"m-flat": {"profile_id": "m-flat"}})
            report = audit(robots_dir=root)
            self.assertEqual(["brand_new_metadata"], report["with_residue"][0]["residue"])
            self.assertEqual(1, exit_code(report))

    def test_no_profile_package_is_reported_but_not_fatal(self):
        """无 profile 的包如实报告（config.json 是唯一任务真值，不可删），不判红；
        但它同时带残留时，残留照常判红。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root, "robot_a", dict(self.POINTER_CONFIG))
            self._package(root, "robot_b", dict(self.POINTER_CONFIG, robot_id="robot_b",
                                                episode_length_s=20.0))
            report = audit(robots_dir=root)
            self.assertEqual(["robot_a", "robot_b"], [r["robot"] for r in report["no_profile"]])
            self.assertEqual(["robot_b"], [r["robot"] for r in report["with_residue"]])
            self.assertEqual(1, exit_code(report))

    def test_non_robot_dirs_and_missing_config_are_ignored(self):
        """非包目录 / 缺 config.json 的目录不进报告（审计只看有 config.json 的包）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root, "robot_a", dict(self.POINTER_CONFIG))
            (root / "not_a_robot").mkdir()
            (root / "robot_empty" / "training").mkdir(parents=True)
            report = audit(robots_dir=root)
            self.assertEqual(["robot_a"], [r["robot"] for r in report["rows"]])
            self.assertEqual(0, exit_code(report))


if __name__ == "__main__":
    unittest.main()
