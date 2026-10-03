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
PKG = ROOT / "assets" / "robots" / "deeprobotics_m20" / "training" / "source" / "m20_dreamwaq"
_PLUGIN_MODELS = ROOT / "adapters" / "mjlab" / "algorithms" / "dreamwaq"
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

    def test_per_package_vae_copy_stays_gone(self):
        """包内 DreamWaQ VAE 扩展**不许复活**（2026-10-04 ⑳c 删除后钉死）。

        一切皆插件：算法扩展以 per-package 拷贝存在 = 旧模式的回归——
        DreamWaQ 机制唯一落点是算法插件 `adapters/mjlab/algorithms/dreamwaq`。
        """
        self.assertFalse(
            (PKG / "mdp" / "rl.py").exists(),
            "m20_dreamwaq/mdp/rl.py 已删（⑳c）：包内算法扩展不许回来，真 VAE 走算法插件 dreamwaq",
        )

    def test_plugin_vae_takes_dims_as_parameters_not_literals(self):
        """插件的 VAE 维度全部**形参传入**（调用点从 runner 配置派生），模型源里无字面量。

        原 mdp/rl.py 时代的判词（in_dim 默认值 = HISTORY_OBS_DIM 派生名，写字面量会在
        帧宽/历史长变更时静默错位——225 vs 285 就是这么来的）平移到插件侧：
        `DreamWaQVAE.__init__` 四个维度全是必填形参（无默认值可藏字面量），
        调用点 `DreamWaQVAE(history_dim - obs_dim, …, obs_dim)` 的首末两位是**派生表达式**。
        """
        models = _PLUGIN_MODELS / "models.py"
        self.assertTrue(models.is_file(), "算法插件 dreamwaq/models.py 必须存在（机制唯一落点）")
        tree = ast.parse(models.read_text(encoding="utf-8"))
        vae_init = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "__init__"
             and any(isinstance(a, ast.Name) and a.id == "DreamWaQVAE"
                     for a in n.args.args[:1]) is False and False),
            None,
        )
        # 直接按类找 __init__（上面的 next 只是占位守卫）
        inits = [n for n in ast.walk(tree)
                 if isinstance(n, ast.ClassDef) and n.name == "DreamWaQVAE"
                 for n in n.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
        self.assertEqual(1, len(inits), "DreamWaQVAE 必须有且只有一个 __init__")
        vae_init = inits[0]
        params = [a.arg for a in vae_init.args.args]
        self.assertEqual(
            ["self", "history_dim", "latent_dim", "explicit_dim", "decode_dim"],
            params,
            "DreamWaQVAE 维度必须全走形参（无字面量可藏）",
        )
        self.assertFalse(
            vae_init.args.defaults,
            "DreamWaQVAE.__init__ 不许有默认值（默认值 = 字面量的藏身处）",
        )
        # 调用点派生：history 维 = history_dim - obs_dim（历史展平扣单帧），decode = obs_dim
        call = next((n for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == "DreamWaQVAE"), None)
        self.assertIsNotNone(call, "models.py 必须有 DreamWaQVAE 的装配调用点")
        self.assertEqual(4, len(call.args), "DreamWaQVAE 调用必须显式给满 4 个维度")
        self.assertIsInstance(call.args[0], ast.BinOp, "history 维必须是派生表达式（history_dim - obs_dim）")
        self.assertIsInstance(call.args[3], ast.Name, "decode 维必须取传入的 obs_dim 名字，不是字面量")

    def test_history_term_uses_the_same_frame_dim(self):
        frame = _module_constant("mdp/observations.py", "_FRAME_DIM")
        self.assertIsNotNone(frame, "observations.py 必须声明 _FRAME_DIM")
        self.assertIsInstance(frame, ast.Name, "_FRAME_DIM 必须取自 constants.OBS_FRAME_DIM，不是字面量")
        self.assertEqual("OBS_FRAME_DIM", frame.id)


if __name__ == "__main__":
    unittest.main()
