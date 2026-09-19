"""内容摘要单一来源：一个工件只有一个哈希（B39 口径的守卫）。

要求原文（`00_know/05` B39 / B40）：同一个工件（契约、模型、motion、离线包、插件包）
只能有**一套**摘要口径，否则"对账"就只在某一台机器上成立。

本类守护三件性质（漂移即失败，而不是靠"两侧必须同步修改"的注释）：

  1. **归一规则唯一**：``normalize_line_endings`` 是全仓唯一一处 CRLF → LF 实现；
     任何模块都不许再写 ``replace(b"\\r\\n", b"\\n")`` 或直接 ``hashlib.sha256(...)``
     做内容摘要（要么委托 :func:`normalized_sha256`，要么委托 :func:`package_digest`）。
  2. **单文件 / 多文件共享同一归一**：``package_digest`` 与 ``normalized_sha256`` 同源。
  3. **真实缺陷不再复现**：``project_api._tree_hash`` 曾经少了归一 —— 与
     ``model_api`` 写进 ``robot_package.json`` 的 ``content_sha256`` 不同口径，
     同一份内容会被判成两份（实测本仓 4 个包两种口径**全都不同**）。
"""

from __future__ import annotations

import ast
import hashlib
import tempfile
import unittest
from pathlib import Path

from contracts.validator import normalize_line_endings, normalized_sha256, package_digest

REPO = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("backend", "contracts", "tools", "adapters", "scripts")

#: 允许出现"内容摘要实现"的文件——**只有这一个**。
DIGEST_HOME = REPO / "contracts" / "validator.py"


def _python_files() -> list[Path]:
    files: list[Path] = []
    for base in SCAN_DIRS:
        root = REPO / base
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts and not path.name.startswith("test_")]


class NormalizedSha256Test(unittest.TestCase):
    def test_crlf_and_lf_are_the_same_artifact(self) -> None:
        self.assertEqual(normalized_sha256(b"a\r\nb\r\n"), normalized_sha256(b"a\nb\n"))

    def test_content_change_is_still_detected(self) -> None:
        """归一不能掩盖内容改动，否则摘要就失去意义。"""

        self.assertNotEqual(normalized_sha256(b"a\nb\n"), normalized_sha256(b"a\nc\n"))

    def test_binary_with_crlf_bytes_is_normalised_too(self) -> None:
        """如实记录口径边界：二进制里的 ``0D 0A`` 序列也会被归一。

        这是"一个工件只有一个哈希"的代价（B39 明确选择一致优先），
        写出来是为了让下一个人知道：这不是 bug，是取舍。
        """

        self.assertEqual(normalized_sha256(b"\x00\r\n\xff"), normalized_sha256(b"\x00\n\xff"))


class PackageDigestTest(unittest.TestCase):
    def test_matches_the_documented_construction(self) -> None:
        entries = [(Path("a.txt"), b"1\r\n2"), (Path("b/x.obj"), b"mesh")]
        expected = hashlib.sha256()
        for relative, data in sorted(entries, key=lambda pair: pair[0].as_posix()):
            expected.update(relative.as_posix().encode("utf-8"))
            expected.update(b"\0")
            expected.update(normalize_line_endings(data))
            expected.update(b"\0")
        self.assertEqual(expected.hexdigest(), package_digest(entries))

    def test_order_does_not_matter_but_paths_do(self) -> None:
        first = package_digest([(Path("a"), b"x"), (Path("b"), b"y")])
        self.assertEqual(first, package_digest([(Path("b"), b"y"), (Path("a"), b"x")]))
        # 同一份字节放在不同路径 = 不同的包
        self.assertNotEqual(first, package_digest([(Path("a"), b"x"), (Path("c"), b"y")]))

    def test_directory_digest_agrees_for_a_crlf_package(self) -> None:
        """目录口径与 entries 口径必须同值（这就是"同一份内容"的定义）。"""

        from backend.project_api import _tree_hash

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            (root / "contract.json").write_bytes(b'{"a": 1}\r\n')
            (root / "nested" / "mesh.obj").write_bytes(b"v 0 0 0\r\nv 1 0 0\r\n")
            entries = [
                (path.relative_to(root), path.read_bytes())
                for path in sorted(root.rglob("*"))
                if path.is_file()
            ]
            self.assertEqual(package_digest(entries), _tree_hash(root))


class ExistingArtifactsAgreeTest(unittest.TestCase):
    """既有资产上"两个域"现在必须同判 —— 这是缺陷已修的活证据。"""

    def test_robot_packages_agree_between_import_and_export_digests(self) -> None:
        from backend.model_api import _content_hash
        from backend.project_api import _tree_hash

        robots = REPO / "assets" / "robots"
        packages = [item for item in sorted(robots.iterdir()) if (item / "contract.json").is_file()]
        self.assertTrue(packages, "至少应有一个机器人包")
        for package in packages:
            with self.subTest(package=package.name):
                entries = [
                    (path.relative_to(package), path.read_bytes())
                    for path in sorted(package.rglob("*"))
                    if path.is_file()
                ]
                self.assertEqual(package_digest(entries), _content_hash(entries))
                self.assertEqual(package_digest(entries), _tree_hash(package))


class DigestImplementationIsDelegatedTest(unittest.TestCase):
    """源码级守卫：摘要实现只许有 ``contracts/validator.py`` 一处。"""

    def test_no_raw_crlf_normalisation_outside_the_home(self) -> None:
        offenders: list[str] = []
        for path in _python_files():
            if path == DIGEST_HOME:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if 'replace(b"\\r\\n", b"\\n")' in text or "replace(b'\\r\\n', b'\\n')" in text:
                offenders.append(str(path.relative_to(REPO)))
        self.assertEqual([], offenders, f"CRLF 归一只许在 contracts/validator.py：{offenders}")

    def test_no_raw_sha256_of_file_bytes_outside_the_home(self) -> None:
        """文件字节的 sha256 只许在 ``contracts/validator.py`` 一处（薄封装随意，实现唯一）。

        判定标准是"**对文件字节**摘要"：``sha256(x.read_bytes())`` / ``sha256(f.read())``。
        内存摘要（``contracts.contract_legacy_v2.compute_hash``、``training.runs.canonical_digest``
        这类对 canonical JSON 求摘要）是另一个问题，不算违规 —— 它们不随检出平台漂移。
        """

        offenders: list[str] = []
        for path in _python_files():
            if path == DIGEST_HOME:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
                    target = call.func
                    if not (isinstance(target, ast.Attribute) and target.attr == "sha256"):
                        continue
                    if any(self._reads_file(arg) for arg in call.args):
                        offenders.append(f"{path.relative_to(REPO)}::{node.name}")
        self.assertEqual([], offenders, f"文件内容的 sha256 需委托 contracts.validator：{offenders}")

    @staticmethod
    def _reads_file(node: ast.AST) -> bool:
        """参数里是否出现 ``.read_bytes()`` / ``.read()``（含 ``open(...)`` 的返回值）。"""

        return any(
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Attribute)
            and item.func.attr in {"read_bytes", "read"}
            for item in ast.walk(node)
        )


if __name__ == "__main__":
    unittest.main()
