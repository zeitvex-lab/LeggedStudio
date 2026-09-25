"""序 15：保留 `terrain_scan` 的机型必须把它的 frame 重指到**本机型根 body**（回归锁）。

背景（2026-09-20 实测）：`terrain_scan` 是 mjlab velocity 基座自带的通用传感器，
其默认 frame 是 ``ObjRef(entity="robot", name="")`` → 解析成 ``robot/``（**空 body 名**），
Scene 初始化时 ``mj_model.body("robot/")`` 抛
``KeyError: Invalid name 'robot/'``。lite3 / b2 靠 ``kit.repoint_height_scan_sensors``
重指，**go1 从未重指** ⇒ `go1-velocity-rough` 自引入起就无法建环境（漏实现，非回归）。

**2026-09-25 起这条不变式换了挂载点**：go1 / b2 / lite3 的 velocity 装配已上移到族级
（`quadruped_kit/skills/velocity/config.py`），重指由 Kit 统一做、机型侧只剩薄委托。
所以本锁改成两段：

1. **族级**：Kit 的 velocity 配置必须真的调用重指（否则所有保留该传感器的机型一起裸奔）；
2. **机型侧**：这些机型的入口模块必须**委托给族级工厂**（否则 Kit 的重指落不到它身上）。

为什么用 **AST 静态锁**而不是跑一遍环境：本测试要能在**控制面 venv（无 mjlab）**与 CI 里跑。
真正建环境的验证是 ``tools/validate_training_smoke.py --robot unitree_go1``（实测 4/4 ok）。
"""

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KIT_VELOCITY = (
    REPO_ROOT / "adapters" / "mjlab" / "kits" / "quadruped_kit" / "skills" / "velocity" / "config.py"
)
#: 保留 `terrain_scan` 的机型：入口模块必须委托族级工厂（族级重指才作用到它）。
KEEPERS = {
    "unitree_go1": REPO_ROOT / "assets" / "robots" / "unitree_go1" / "training" / "source" / "go1_velocity" / "env_cfg.py",
    "deeprobotics_lite3": REPO_ROOT / "assets" / "robots" / "deeprobotics_lite3" / "training" / "source" / "lite3_velocity" / "env_cfg.py",
    "unitree_b2": REPO_ROOT / "assets" / "robots" / "unitree_b2" / "training" / "source" / "b2_velocity" / "env_cfg.py",
}
#: 族级重指符号：家族既有 `repoint_height_scan_sensors`（对外工厂），也有 Kit 内的
#: 私有包装（velocity 用后者）。两者任一在场即算"真的重指了"。
REPOINT_SYMBOLS = ("repoint_height_scan_sensors", "_repoint_terrain_scan")
#: 机型侧委托的静态证据：导入族级 velocity 模块 + 调它的 `make_env_cfg`。
FAMILY_VELOCITY_MODULE = "quadruped_kit.skills.velocity"
FAMILY_FACTORY = "make_env_cfg"


def _calls(tree: ast.AST, attr: str) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == attr:
            found.append(node)
    return found


def _mentions(tree: ast.AST, name: str) -> bool:
    """模块里出现过该名字（导入名、属性名或调用名）——"委托"的静态证据。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split(".")[-1]) == name:
            return True
    return False


class TerrainScanRepointTests(unittest.TestCase):
    def test_family_velocity_repoints_terrain_scan(self):
        self.assertTrue(KIT_VELOCITY.is_file(), f"族级 velocity 配置不存在：{KIT_VELOCITY}")
        tree = ast.parse(KIT_VELOCITY.read_text(encoding="utf-8"))
        self.assertTrue(
            any(_calls(tree, symbol) or _mentions(tree, symbol) for symbol in REPOINT_SYMBOLS),
            "族级 velocity 配置没有重指 terrain_scan —— 保留该传感器的机型会停在 mjlab "
            "默认的 'robot/'（空 body 名），建环境必然 KeyError",
        )

    def test_terrain_scan_keepers_delegate_to_the_family_factory(self):
        """保留了 terrain_scan 的机型必须走族级工厂 —— 族级的重指才作用到它。"""
        missing = []
        for robot, path in KEEPERS.items():
            if not path.is_file():
                continue
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source)
            if FAMILY_VELOCITY_MODULE not in source or not _mentions(tree, FAMILY_FACTORY):
                missing.append(robot)
        self.assertEqual(
            missing, [],
            f"这些机型保留了 terrain_scan 却没走族级 velocity 工厂（重指落不到它）：{missing}",
        )


if __name__ == "__main__":
    unittest.main()
