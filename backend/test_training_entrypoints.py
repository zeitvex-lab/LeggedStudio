"""B22：训练 profile entrypoints 的**零依赖静态审计**——「指向的符号存在」进 CI。

## 这组测试守的是什么

B22 事故：microduck 的 12 个 profile 声明了 entrypoints，但工作树源码被截断、包根本
import 不了——静态审计缺位让「14 机型可训练」（B14）虚盖了很久。本文件钉三件事：

1. **全仓不变量**：8 个内置包所有 profile 的 entrypoints（env / runner / 及
   runner_class / configure，若存在）必须静态可解析——不 import 包代码、不 import
   mjlab/torch，纯 AST + 文件系统；失败信息列出 {包/profile/entrypoint/原因} 明细；
2. **external 白名单**：顶层段不在 source_root 下的目标（安装的第三方依赖，零依赖
   静态审计天然不可验）只允许是已知 external（``mjlab.*``），如实单列、不判红；
   白名单外出现新 external 是有意动作，须连同本测试一起改；
3. **审计函数语义**：tmp 目录假包逐条单测 ``audit()`` / ``exit_code()``——直接 def 过、
   再导出一跳过、模块是包走 ``__init__.py``、``.py`` 优先、指向不存在模块判红、
   符号不存在判红、``__all__`` 有名无实判红、不可解析判红、再导出环/深度用尽判红、
   external 默认不判红（``external_is_missing=True`` 一键翻红）。

风格：纯 pytest 兼容的 unittest.TestCase（CI 的 ``unittest discover`` 与本地
``python -m pytest`` 双口径可跑）、仅标准库、直读文件。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_training_entrypoints import (
    DEFAULT_SOURCE_ROOT,
    MAX_REEXPORT_HOPS,
    audit,
    exit_code,
)

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"

#: 已知 external 白名单：这些顶层模块是安装的第三方依赖（不在任何包的 source_root 下）。
KNOWN_EXTERNAL_MODULES = {"mjlab.tasks.velocity.rl", "mjlab.rl"}


class RepoEntrypointInvariantTest(unittest.TestCase):
    """全仓不变量：8 包所有 profile 的 entrypoints 静态可解析，无例外。"""

    def _builtin_robots(self) -> list[str]:
        return sorted(
            d.name for d in ROBOTS.iterdir()
            if d.is_dir() and (d / "training" / "profiles").is_dir()
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

    def test_all_entrypoints_statically_resolvable(self):
        """8 包所有 profile：entrypoints.env / runner（及 runner_class / configure）
        静态可解析；失败信息列出 {包/profile/entrypoint/原因} 全部明细。"""
        report = audit()
        detail = "\n".join(
            f"  {row['robot']}/{row['profile']}  {row['key']}  {row['target']}"
            f"\n    → {row['reason']}"
            for row in report["missing"]
        )
        self.assertEqual(
            [], report["missing"],
            "这些 profile entrypoint 指向的符号静态不存在（B22 同类事故：声明了入口但"
            "工作树源码给不出该符号）——须补齐源码或修正 entrypoint：\n" + detail,
        )

    def test_externals_are_only_known_third_party_modules(self):
        """external（顶层段不在 source_root 下）只允许已知 mjlab 模块；
        新 external 出现 = 有意动作，须连同本测试一起扩充白名单。"""
        report = audit()
        unexpected = sorted(
            {row["module"] for row in report["external"]} - KNOWN_EXTERNAL_MODULES
        )
        self.assertEqual(
            [], unexpected,
            "出现白名单外的 external entrypoint（零依赖静态审计无法验证的第三方顶层"
            f"模块）：{unexpected}；确认确为第三方依赖后请更新 KNOWN_EXTERNAL_MODULES",
        )


class AuditFunctionTest(unittest.TestCase):
    """audit()/exit_code() 单测：tmp 假包目录，逐条钉报告内容与门禁退出码。"""

    @staticmethod
    def _package(
        root: Path,
        robot: str,
        files: dict[str, str],
        profiles: dict[str, dict],
    ) -> None:
        """造一个假包：``files`` 是 source_root 下的相对路径→源码文本；
        ``profiles`` 是 profile 文件名（不带 .json）→ JSON 体。"""
        source = root / robot / "training" / "source"
        for rel, content in files.items():
            path = source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        profiles_dir = root / robot / "training" / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        for name, body in profiles.items():
            (profiles_dir / f"{name}.json").write_text(
                json.dumps(body, ensure_ascii=False), encoding="utf-8",
            )

    # ------------------------------------------------------------- 通过路径

    def test_direct_def_passes(self):
        """直接 def/class 定义 → 可解析、无缺失、exit 0。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"vehicle_env.py": (
                    "def make_env_cfg():\n    pass\n\n"
                    "class RunnerCfg:\n    pass\n"
                )},
                profiles={"a-flat": {
                    "profile_id": "a-flat",
                    "entrypoints": {
                        "env": "vehicle_env:make_env_cfg",
                        "runner": "vehicle_env:RunnerCfg",
                    },
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual(1, report["total_packages"])
            self.assertEqual(2, report["total_entrypoints"])
            self.assertEqual([], report["missing"])
            self.assertEqual([], report["external"])
            self.assertEqual(0, exit_code(report))

    def test_reexport_one_hop_passes(self):
        """``from .impl import name`` 再导出一跳 → 追到定义处，过。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={
                    "mylib/__init__.py": "from .impl import make_env_cfg\n",
                    "mylib/impl.py": "def make_env_cfg():\n    pass\n",
                },
                profiles={"a-flat": {
                    "entrypoints": {"env": "mylib:make_env_cfg"},
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual([], report["missing"])
            self.assertEqual(0, exit_code(report))

    def test_reexport_chain_up_to_depth_limit_passes(self):
        """再导出链恰好在深度上限（3 跳）内 → 过（a → b → c → d:def）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={
                    "a/__init__.py": "from .b import sym\n",
                    "a/b.py": "from .c import sym\n",
                    "a/c.py": "from .d import sym\n",
                    "a/d.py": "def sym():\n    pass\n",
                },
                profiles={"a-flat": {"entrypoints": {"env": "a:sym"}}},
            )
            report = audit(robots_dir=root)
            self.assertEqual([], report["missing"])

    def test_module_is_package_resolves_via_init(self):
        """module 是包（无 .py）→ 解析到 ``__init__.py``；符号直接定义在 init → 过。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"mylib/__init__.py": "def g1_flat_env_cfg():\n    pass\n"},
                profiles={"a-flat": {
                    "entrypoints": {"env": "mylib:g1_flat_env_cfg"},
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual([], report["missing"])
            self.assertEqual(0, exit_code(report))

    def test_py_file_preferred_over_package_init(self):
        """``m.py`` 与 ``m/__init__.py`` 两处都在 → 报 .py 优先（符号只在 .py → 过）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={
                    "dual.py": "def sym():\n    pass\n",
                    "dual/__init__.py": "# 包初始化，无 sym\n",
                },
                profiles={"a-flat": {"entrypoints": {"env": "dual:sym"}}},
            )
            report = audit(robots_dir=root)
            self.assertEqual([], report["missing"])

    def test_custom_source_root_is_honored(self):
        """profile 显式 ``source_root``（g1 式子目录）→ 以它为解析根，过。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"g1_like/src/thing.py": "def make_it():\n    pass\n"},
                profiles={"a-flat": {
                    "source_root": "training/source/g1_like",
                    "entrypoints": {"env": "src.thing:make_it"},
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual([], report["missing"])
            self.assertEqual(0, exit_code(report))

    def test_external_top_level_is_reported_but_not_fatal_by_default(self):
        """顶层段不在 source_root 下（第三方依赖）→ external 单列、不判红、exit 0；
        严格口径（external_is_missing=True）下判红、exit 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"local_mod.py": "def local_sym():\n    pass\n"},
                profiles={"a-flat": {
                    "entrypoints": {
                        "env": "local_mod:local_sym",
                        "runner_class": "some_pypi_pkg.rl:TheirRunner",
                    },
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual([], report["missing"])
            self.assertEqual(
                [("robot_a", "some_pypi_pkg.rl")],
                [(r["robot"], r["module"]) for r in report["external"]],
            )
            self.assertEqual(0, exit_code(report))

            strict = audit(robots_dir=root, external_is_missing=True)
            self.assertEqual(1, len(strict["missing"]))
            self.assertEqual(1, exit_code(strict))

    # ------------------------------------------------------------- 判红路径

    def test_missing_module_is_fatal(self):
        """顶层段存在但指向的模块文件不存在 → 判红、exit 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"mylib/__init__.py": ""},
                profiles={"a-flat": {
                    "entrypoints": {"env": "mylib.nosuch_module:make_env_cfg"},
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["missing"]))
            self.assertIn("不可解析", report["missing"][0]["reason"])
            self.assertEqual(1, exit_code(report))

    def test_missing_symbol_is_fatal(self):
        """模块存在但符号未定义/未再导出 → 判红、exit 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"vehicle_env.py": "def make_env_cfg():\n    pass\n"},
                profiles={"a-flat": {
                    "entrypoints": {"env": "vehicle_env:nope_env_cfg"},
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["missing"]))
            self.assertIn("nope_env_cfg", report["missing"][0]["reason"])
            self.assertEqual(1, exit_code(report))

    def test_dunder_all_without_binding_is_fatal(self):
        """``__all__`` 里有、源里没有 → 不是存在性证据，判红且归因提到 __all__。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"truncated.py": '__all__ = ["make_env_cfg"]\n'},
                profiles={"a-flat": {
                    "entrypoints": {"env": "truncated:make_env_cfg"},
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["missing"]))
            self.assertIn("__all__", report["missing"][0]["reason"])

    def test_unparseable_source_is_fatal(self):
        """源码被截断成语法错误（B22 本尊形态）→ 判红、exit 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"vehicle_env.py": "def make_env_cfg(:\n    pass\n"},
                profiles={"a-flat": {
                    "entrypoints": {"env": "vehicle_env:make_env_cfg"},
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["missing"]))
            self.assertIn("SyntaxError", report["missing"][0]["reason"])
            self.assertEqual(1, exit_code(report))

    def test_reexport_cycle_is_fatal(self):
        """再导出链成环 → 判红（环检测），不挂死。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={
                    "a/__init__.py": "from .b import sym\n",
                    "a/b.py": "from a import sym\n",
                },
                profiles={"a-flat": {"entrypoints": {"env": "a:sym"}}},
            )
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["missing"]))
            self.assertIn("成环", report["missing"][0]["reason"])

    def test_reexport_beyond_depth_limit_is_fatal(self):
        """再导出链超出深度上限（MAX_REEXPORT_HOPS=3 跳仍未到定义）→ 判红。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chain = {
                "a/__init__.py": "from .b import sym\n",
                "a/b.py": "from .c import sym\n",
                "a/c.py": "from .d import sym\n",
                "a/d.py": "from .e import sym\n",
                "a/e.py": "def sym():\n    pass\n",
            }
            self._package(root, "robot_a", files=chain,
                          profiles={"a-flat": {"entrypoints": {"env": "a:sym"}}})
            self.assertEqual(MAX_REEXPORT_HOPS, 3)
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["missing"]))
            self.assertIn("深度", report["missing"][0]["reason"])

    def test_missing_source_root_is_fatal(self):
        """profile 声明的 source_root 目录不存在 → 逐条判红、exit 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a", files={},
                profiles={"a-flat": {
                    "source_root": "training/nowhere",
                    "entrypoints": {"env": "anything:sym"},
                }},
            )
            report = audit(robots_dir=root)
            self.assertEqual(1, len(report["missing"]))
            self.assertIn("source_root", report["missing"][0]["reason"])
            self.assertEqual(1, exit_code(report))

    # ------------------------------------------------------------- 杂项语义

    def test_empty_robots_dir_is_clean(self):
        """空 robots 目录 → 0 包、无缺失、exit 0（门禁语义的零值基线）。"""
        with tempfile.TemporaryDirectory() as tmp:
            report = audit(robots_dir=Path(tmp))
            self.assertEqual(0, report["total_packages"])
            self.assertEqual([], report["missing"])
            self.assertEqual(0, exit_code(report))

    def test_missing_env_entrypoint_is_fatal(self):
        """profile 连 entrypoints.env 都没有 → 判红（env 是必需入口）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root, "robot_a",
                files={"vehicle_env.py": "def make_env_cfg():\n    pass\n"},
                profiles={"a-flat": {"entrypoints": {"runner": "vehicle_env:make_env_cfg"}}},
            )
            report = audit(robots_dir=root)
            self.assertEqual(
                ["env"], [row["key"] for row in report["missing"]],
            )
            self.assertEqual(1, exit_code(report))


if __name__ == "__main__":
    unittest.main()
