"""DreamWaQ VAE 输入维必须由**历史组宽度**派生，不许写死。

2026-09-25 冒烟抓到真故障：``m20-dreamwaq`` 训练第一次 update 崩
``mat1 and mat2 shapes cannot be multiplied (128x285 and 225x128)`` ——
VEACenet 的 ``in_dim`` 写成字面量 225（从上游对 **45 维帧** 的默认值抄来），
而本机型帧宽 57、历史长 5 ⇒ 实宽 **285**。上游真值
（``00_resources/Dreamwaq/legged_gym/envs/M20/m20_config.py``）本就是派生的::

    num_observations = 57
    num_obs_hist = 5
    num_history_obs = num_obs_hist * num_observations   # = 285

**为什么用 AST 而不是 import**：本测试跑在控制面环境（CI 的 ``discover -s backend``
只有 backend 依赖，没有 torch/mjlab），而 ``m20_dreamwaq`` 的模块 import 链要
mujoco + torch。静态锁在这里是**唯一能在 CI 里守住的形态**；运行期那一半由
真训冒烟守（``tools/validate_training_smoke.py``，m20-dreamwaq 2 iter 真跑）。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "assets" / "robots" / "deeprobotics_m20" / "training" / "source" / "m20_dreamwaq"


def _tree(relative: str) -> ast.Module:
    return ast.parse((PACKAGE / relative).read_text(encoding="utf-8-sig"), filename=relative)


def _assigned_name(node: ast.Assign) -> str | None:
    targets = node.targets
    if len(targets) != 1 or not isinstance(targets[0], ast.Name):
        return None
    return targets[0].id


def _module_constant(relative: str, name: str) -> ast.expr | None:
    for node in _tree(relative).body:
        if isinstance(node, ast.Assign) and _assigned_name(node) == name:
            return node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
    return None


def _names_in(node: ast.AST) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name}")


def _defaults(function: ast.FunctionDef) -> dict[str, ast.expr]:
    """参数名 → 默认值表达式（只取有默认值的形参，按位对齐）。"""
    args = function.args
    positional = list(args.args) + list(args.kwonlyargs)
    defaults = list(args.defaults) + [d for d in args.kw_defaults if d is not None]
    return {
        arg.arg: default
        for arg, default in zip(positional[-len(defaults):] if defaults else [], defaults, strict=True)
    }


class DreamWaQDimTest(unittest.TestCase):
    def test_history_width_is_the_product_of_frame_and_history(self):
        history = _module_constant("constants.py", "HISTORY_OBS_DIM")
        self.assertIsNotNone(history, "constants.py 必须声明 HISTORY_OBS_DIM（派生量，不是字面量）")
        self.assertIsInstance(history, ast.BinOp, "HISTORY_OBS_DIM 必须是乘法表达式，不是字面量")
        self.assertEqual(
            "HISTORY_LENGTH * OBS_FRAME_DIM",
            ast.unparse(history),
            "HISTORY_OBS_DIM 必须是 HISTORY_LENGTH × OBS_FRAME_DIM 的乘积表达式",
        )

    def test_vae_encoder_takes_the_derived_width_not_a_literal(self):
        vae = _function(_tree("mdp/rl.py"), "__init__")
        defaults = _defaults(vae)
        in_dim = defaults.get("in_dim")
        self.assertIsNotNone(in_dim, "_VAE.__init__ 必须有 in_dim 形参")
        self.assertIsInstance(
            in_dim,
            ast.Name,
            "in_dim 的默认值必须是派生的名字（HISTORY_OBS_DIM），不是字面整数 —— "
            "写死会在帧宽/历史长变更时静默错位（225 vs 285 就是这么来的）",
        )
        self.assertEqual("HISTORY_OBS_DIM", in_dim.id)
        self.assertIn("HISTORY_OBS_DIM", _names_in(_tree("mdp/rl.py")), "rl.py 必须从 constants 取该派生量")

    def test_vae_decoder_reconstructs_one_actor_frame(self):
        vae = _function(_tree("mdp/rl.py"), "__init__")
        decode_dim = _defaults(vae).get("decode_dim")
        self.assertIsNotNone(decode_dim, "_VAE.__init__ 必须有 decode_dim 形参")
        self.assertIsInstance(decode_dim, ast.Name, "decode_dim 的默认值必须是 OBS_FRAME_DIM，不是字面量")
        self.assertEqual("OBS_FRAME_DIM", decode_dim.id)

    def test_history_term_uses_the_same_frame_dim(self):
        frame = _module_constant("mdp/observations.py", "_FRAME_DIM")
        self.assertIsNotNone(frame, "observations.py 必须声明 _FRAME_DIM")
        self.assertIsInstance(frame, ast.Name, "_FRAME_DIM 必须取自 constants.OBS_FRAME_DIM，不是字面量")
        self.assertEqual("OBS_FRAME_DIM", frame.id)


if __name__ == "__main__":
    unittest.main()
