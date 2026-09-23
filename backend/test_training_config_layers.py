"""B13 终态收口：``training/config.json`` 必须退化为**纯指针文件**（8 包全部指针化，无例外）。

## 这组测试守的是什么

三层拆分（物理→契约 / 任务→Recipe / 运行→Run）落地后，各包 `training/config.json` 的终态
是只含指针字段 `{robot_id, contract_path, profile_id, schema_version, backend}` 的引用文件。
本文件钉三件事：

1. **全仓不变量**：8 个内置包**全部**指针化，每份 config.json 的键集 ⊆ 指针字段集，
   **无任何豁免**（即使不与 profile 同名、没有任何代码读，残留也不允许——go2 曾残留的
   `reward_scales` 就是这类）；失败信息列出 {包: [多出来的键]}；
2. **包清单钉死**：内置包数量钉在 8（family-arch 收敛口径）；增删包是有意动作，须连同本测试一起改；
3. **审计函数语义**：用假包目录（tmp 根）单测 `audit()` / `exit_code()`——合法指针包放行、
   指针外残留判红、双写判红、无 profile 如实报告各造一份，断言报告内容与门禁退出码
   （残留或双写任一出现 → exit 1）。

（此前的 microduck「待取证」豁免已完成使命、机制整体拆除——终态无任何豁免。）

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
    audit,
    exit_code,
)

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"


def _config_keys(robot: str) -> set[str]:
    """直读某内置包的 config.json 顶层键集。"""
    path = ROBOTS / robot / "training" / "config.json"
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return set(value.keys())


class RepoPointerInvariantTest(unittest.TestCase):
    """全仓不变量：8 个内置包**全部**指针化，无任何例外。"""

    def _builtin_robots(self) -> list[str]:
        return sorted(
            d.name for d in ROBOTS.iterdir()
            if d.is_dir() and (d / "training" / "config.json").exists()
        )

    def test_8_builtin_packages_present(self):
        """内置包清单钉在 8（family-arch 收敛口径：4 四足 + 4 轮足）；
        增删包是有意动作，须连同本测试一起改。"""
        self.assertEqual(
            [
                "deeprobotics_lite3",
                "deeprobotics_m20",
                "unitree_b2",
                "unitree_b2w",
                "unitree_go1",
                "unitree_go2",
                "unitree_go2w",
                "zex-w",
            ],
            self._builtin_robots(),
        )

    def test_config_is_pointer_only(self):
        """8 包全部：键集 ⊆ 指针字段集，无例外；失败信息列出 {包: [多出来的键]}。"""
        violations: dict[str, list[str]] = {}
        for robot in self._builtin_robots():
            extra = sorted(_config_keys(robot) - POINTER_FIELDS)
            if extra:
                violations[robot] = extra
        self.assertEqual(
            {}, violations,
            "这些包的 training/config.json 残留指针外字段（终态 = 纯指针文件，8 包无例外），"
            "应归位任务层（Recipe/ profile）或运行层（Run）后删除",
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
