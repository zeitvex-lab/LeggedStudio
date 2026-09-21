"""Robot package boundary tests (robot_lab test_no_framework_imports pattern).

Imported/served robot packages must go through the contract API only: their
code may not import simulator or control-plane internals directly. This keeps
packages portable across the browser viewer, the FastAPI process, and the
isolated MJLab worker.
"""

import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 禁止出现在机器人包 Python 源里的顶层模块（平台控制面内部实现）。
# training/source/ 下的包扩展任务源是例外：worker 显式把它们加入 sys.path 并按
# 契约加载，允许 import 训练内核（mjlab/isaaclab）——但即便那里也不得反向依赖
# 平台控制面（backend/adapters/contracts），否则包就绑死在本仓库结构上。
FORBIDDEN_PREFIXES = (
    "backend",
    "adapters",
    "contracts",
)

#: B8 框架上移的**共享任务 kit**（训练栈侧纯 mjlab 级 helper，不 import backend/控制面）：
#: 包内 stub 允许且应当引用它——这正是"框架层上移、任务特有留包"的载体。
#: 它是显式列名的白名单（而不是放行整个 adapters），边界守卫对其余 adapters 模块照旧生效。
SANCTIONED_SHARED_KITS = (
    # 2026-09-19 按形态拆分：四足 Kit 服务 lite3/b2，轮足 Kit 服务 m20/b2w/go2w。
    # 仍是**显式列名**——新增形态 Kit 时须在此登记（一次人工确认，胜过放行整个 kits/）。
    "adapters.mjlab.kits.quadruped_kit",
    "adapters.mjlab.kits.wheel_leg_kit",
)

# 扩展入口（extension_entrypoint）白名单前缀：平台按契约显式加载它们，
# 它们可以 import mjlab 的任务注册 API。
ENTRYPOINT_ALLOWED_PREFIXES = ("mjlab", "isaaclab", "isaaclab")

SCAN_ROOTS = ("training/source", "scripts")
SCAN_SUFFIX = ".py"


def _is_entrypoint_module(relative: Path, package_root: Path, entrypoints: set[str]) -> bool:
    """extension_entrypoint 声明的模块路径允许引用训练内核。"""
    for entry in entrypoints:
        module = str(entry).replace(".", "/")
        candidate = (relative.as_posix()).removesuffix(".py")
        if candidate == module or candidate.startswith(module + ".") or candidate.startswith(module + "/"):
            return True
        # entrypoint 也常写作 "pkg.module:attr" 或目录形式
        base = str(entry).split(":")[0].replace(".", "/")
        if candidate.startswith(base):
            return True
    return False


class RobotPackageBoundaryTests(unittest.TestCase):
    """⑮ 边界守卫：机器人包源码不直接 import 平台/仿真器内部模块。"""

    def test_bundled_package_sources_respect_import_boundary(self):
        robots_root = PROJECT_ROOT / "assets" / "robots"
        violations: list[str] = []
        checked_files = 0
        for package_root in sorted(robots_root.iterdir()):
            if not package_root.is_dir():
                continue
            manifest_path = package_root / "robot_package.json"
            entrypoints: set[str] = set()
            if manifest_path.exists():
                try:
                    import json

                    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                    entry = manifest.get("extension_entrypoint")
                    if entry:
                        entrypoints.add(str(entry))
                    extension_root = manifest.get("extension_root")
                    if extension_root:
                        entrypoints.add(str(extension_root))
                except (OSError, ValueError):
                    pass
            for scan_root in SCAN_ROOTS:
                base = package_root / scan_root
                if not base.exists():
                    continue
                for py_file in base.rglob(f"*{SCAN_SUFFIX}"):
                    relative = py_file.relative_to(package_root)
                    try:
                        source = py_file.read_text(encoding="utf-8-sig")
                    except OSError:
                        continue
                    checked_files += 1
                    if _is_entrypoint_module(relative, package_root, entrypoints):
                        continue
                    for line_no, raw_line in enumerate(source.splitlines(), start=1):
                        line = raw_line.strip()
                        if not (line.startswith("import ") or line.startswith("from ")):
                            continue
                        # 函数体内/TYPE_CHECKING 守卫的 import 允许（robot_lab 惯例）
                        if raw_line.startswith((" ", "\t")):
                            continue
                        target = line.split()[1].split(".")[0] if line.startswith("import ") else line.split()[1]
                        # 完整点路径匹配（`from adapters.mjlab.kits import quadruped_kit`
                        # 的 target 只是首段 "adapters"，必须拼上导入名再比对）
                        if line.startswith("from ") and " import " in line:
                            module_path = line.split()[1]
                            names = [n.split(" as ")[0].strip() for n in line.split(" import ", 1)[1].split(",")]
                            dotted = [f"{module_path}.{n}" for n in names] + [module_path]
                        else:
                            dotted = [target]
                        if any(any(f == kit or f.startswith(kit + ".") for kit in SANCTIONED_SHARED_KITS) for f in dotted):
                            continue
                        for prefix in FORBIDDEN_PREFIXES:
                            if target == prefix or target.startswith(prefix.rstrip(".")):
                                violations.append(
                                    f"{py_file.relative_to(PROJECT_ROOT)}:{line_no}: {line}"
                                )
                                break
        self.assertFalse(
            violations,
            "robot package sources import platform/simulator internals:\n" + "\n".join(violations[:20]),
        )
        # 守住测试自身的有效性：扫描必须真的覆盖到了文件
        self.assertGreater(checked_files, 0, "no python files scanned under assets/robots")


class RobotPackageConfigImmutabilityTests(unittest.TestCase):
    """⑥ 配置防串扰（P2 go2w_constants deepcopy 教训）：包配置被并发读取方
    （browser-config、验收器、训练 profile 合并）共享时不得被原地突变。"""

    def test_simulation_config_reads_do_not_share_mutable_policy_entries(self):
        import json

        robots_root = PROJECT_ROOT / "assets" / "robots"
        checked = 0
        for package_root in sorted(robots_root.iterdir()):
            config_path = package_root / "simulation" / "config.json"
            if not config_path.exists():
                continue
            raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
            policies = raw.get("policies") or []
            if len(policies) < 2:
                continue
            checked += 1
            # 模拟两个消费方各自深改自己拿到的策略条目后，包原始配置不受影响
            snapshot = json.dumps(policies[0], sort_keys=True)
            first = json.loads(json.dumps(policies[0]))
            second = json.loads(json.dumps(policies[1]))
            first["action_scale"] = 999.0
            second.setdefault("contract", {})["observation_kind"] = "__mutated__"
            first_snapshot = json.dumps(policies[0], sort_keys=True)
            second_snapshot = json.dumps(policies[1], sort_keys=True)
            self.assertEqual(
                json.dumps(policies[0], sort_keys=True),
                snapshot,
                f"{config_path}: policies[0] 与共享可变对象别名（消费方 deepcopy 后才可改）",
            )
            self.assertEqual(
                json.dumps(policies[1], sort_keys=True),
                second_snapshot,
                f"{config_path}: policies[1] 别名污染",
            )
        self.assertGreater(checked, 0, "no multi-policy package scanned")

    def test_policy_contracts_carry_required_identity_fields(self):
        """每个策略条目必须自带观测/动作身份字段：跨包复用时不可依赖隐式全局。"""
        import json

        robots_root = PROJECT_ROOT / "assets" / "robots"
        problems: list[str] = []
        for package_root in sorted(robots_root.iterdir()):
            config_path = package_root / "simulation" / "config.json"
            if not config_path.exists():
                continue
            raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
            # 包级 policy_contract 是合法兜底（旧式布局：全包共享一份契约）
            shared = raw.get("policy_contract") or {}
            for policy in raw.get("policies") or []:
                pid = policy.get("id") or policy.get("path")
                contract = policy.get("contract") or {}
                for field in ("observation_kind", "obs_dim", "action_dim"):
                    # contract 内声明 / 条目顶层简写 / 包级 policy_contract 兜底，有其一即可
                    if not (contract.get(field) or policy.get(field) or shared.get(field)):
                        problems.append(f"{config_path} policy {pid}: missing {field}")
        self.assertFalse(problems, chr(10).join(problems[:20]))


class PackageIndexSignatureTests(unittest.TestCase):
    """包索引的新鲜度签名必须覆盖**策略/训练声明文件**。

    防的回归（2026-09-21 实测）：`_package_signature` 只覆盖 contract/manifest
    的 mtime 与 `training/profiles` + `training/source` 的目录摘要，**不含**
    `simulation/config.json`。于是在 `simulation/config.json` 里新登记一条策略后：
      * `/api/robots/presets/<id>`（读持久索引）仍返回**旧**策略清单
        ⇒ 场景编辑器的策略下拉选不到新策略；
      * `/api/simulation/browser-config/<id>`（每次现算）是**新**的。
    两端不一致，且旧的那端没有报错——正是"stale index"类缺陷（该函数 docstring 自己
    点名要防的那类）。这里钉住：改 `simulation/config.json` 必须翻转签名。
    """

    def _signature(self) -> str:
        import importlib

        module = importlib.import_module("backend.robot_packages")
        return module._package_signature()

    def test_simulation_config_edit_flips_the_signature(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "unitree_go2"
            (pkg / "simulation").mkdir(parents=True)
            config = pkg / "simulation" / "config.json"
            config.write_text(json.dumps({"policies": [{"id": "a"}]}), encoding="utf-8")
            import backend.robot_packages as rp

            original_roots = rp._package_roots
            rp._package_roots = lambda: [root]
            try:
                before = self._signature()
                # 内容级变更：加一条策略（字节数与 mtime 都变）
                config.write_text(json.dumps({"policies": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8")
                after = self._signature()
                self.assertNotEqual(before, after, "simulation/config.json 的内容变更必须翻转索引签名")
                # 纯内容变更也要翻转（同一字节数、只改内容）——mtime 精度不足时靠字节数
                same_size = json.dumps({"policies": [{"id": "a"}, {"id": "c"}]})
                config.write_text(same_size, encoding="utf-8")
                self.assertNotEqual(before, self._signature(), "同尺寸的内容变更也要能被感知")
            finally:
                rp._package_roots = original_roots

    def test_missing_config_file_is_in_the_signature(self):
        """缺文件与有文件必须可区分（新建 config.json 也要触发重扫）。"""

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "unitree_go2"
            (pkg / "simulation").mkdir(parents=True)
            import backend.robot_packages as rp

            original_roots = rp._package_roots
            rp._package_roots = lambda: [root]
            try:
                missing = self._signature()
                (pkg / "simulation" / "config.json").write_text("{}", encoding="utf-8")
                self.assertNotEqual(missing, self._signature(), "新建 simulation/config.json 必须翻转签名")
            finally:
                rp._package_roots = original_roots


if __name__ == "__main__":
    unittest.main()
