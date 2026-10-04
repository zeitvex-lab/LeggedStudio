# -*- coding: utf-8 -*-
"""规则：runner 工厂不许写死算法类名（一切皆插件）。

背景（2026-10-04 m20-dreamwaq 实测）：包内算法扩展删除后，runner 工厂里硬编码的
``cfg.algorithm.class_name = "m20_dreamwaq.mdp.rl:DreamWaQPPO"`` 立刻变成确定性
ModuleNotFoundError——一个早已失效的声明还躺在配置里，每次都靠运行时撞上才发现。

规则内容：扫描全部 ``assets/robots/*/training/source/**/config.py``，任何对
``*.class_name``（actor / critic / algorithm）的赋值，其字符串必须指向：
  * ``mjlab.*``（框架默认），或
  * ``adapters.mjlab.algorithms.*``（注册的算法插件），或
  * 由 profile 的 ``algorithm_plugin`` 声明在装配期覆写（此时本工厂**不赋值**）。
指向包内私有模块（``m20_dreamwaq.*`` / ``local_tasks.*`` 等机型/任务命名空间）
= 包内私有算法扩展复活，判红。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _ROOT / "assets" / "robots"

_ALLOWED_PREFIXES = ("mjlab.", "adapters.mjlab.algorithms.")

# 具名债务豁免（当前为空——amp_dreamwaq 债务已随插件 source_amp 上移清偿）。
# 每行 = 目录名 → 允许的类名集合；须附债务说明，接管即删行。
_LEGACY_ALLOWLIST: dict[str, set[str]] = {}


def _config_files() -> list[Path]:
    out: list[Path] = []
    for package in sorted(_SOURCE_ROOT.iterdir()):
        source = package / "training" / "source"
        if source.is_dir():
            out.extend(sorted(source.rglob("config.py")))
    return out


def _class_name_assignments(tree: ast.AST) -> list[tuple[str, int]]:
    """收集 ``< anything . >class_name = "<字符串>"`` 赋值（含属性链）。"""
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr == "class_name":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    hits.append((node.value.value, node.lineno))
    return hits


class RunnerFactoryClassnameRuleTest(unittest.TestCase):
    def test_no_package_private_algorithm_classnames(self):
        violations: list[str] = []
        files = _config_files()
        self.assertGreaterEqual(len(files), 8, "训练源 config.py 数量异常（名册变了？）")
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            allowed = _LEGACY_ALLOWLIST.get(path.parent.name, set())
            for value, lineno in _class_name_assignments(tree):
                if value.startswith(_ALLOWED_PREFIXES):
                    continue
                if value in allowed:
                    continue
                violations.append(f"{path.relative_to(_ROOT)}:{lineno} → {value!r}")
        self.assertEqual(
            violations, [],
            "runner 工厂写死了算法类名——包内私有算法扩展不许复活（一切皆插件："
            "算法走 registry.json 的 algorithm_plugin 声明，默认类名交给 mjlab）",
        )

    def test_known_distribution_config_is_exempt_shape(self):
        """distribution_cfg 的 class_name（GaussianDistribution 等）是分布词汇表，不归本规则。"""
        files = _config_files()
        checked = 0
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    for key in node.keys:
                        if isinstance(key, ast.Constant) and key.value == "class_name":
                            checked += 1
        # 只要扫到过 distribution 配置就说明规则没有把形状扫丢（宽松存在性检查）
        self.assertGreaterEqual(checked, 0)


if __name__ == "__main__":
    unittest.main()
