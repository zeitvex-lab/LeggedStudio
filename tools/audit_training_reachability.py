#!/usr/bin/env python3
"""B8 训练包可达性审计：算出包内 ``training/source`` 里哪些模块**真的被用到**。

## 为什么要有这个工具（而不是每轮临时写脚本）

B8「训练去包化」要不断回答同一个问题：**包内这几百个 .py，哪些是上游残留的死代码？**
仓库里已有持久索引的是**资源与注册表**（``registry/*.json``：skills / rewards / motions /
licenses / porting_evidence …），但**训练包内 .py 的可达性没有索引** —— B8 只记了
"包内 .py 数量"这种标量。于是每轮都要重新推导一遍可达性，且临时脚本随手丢在
``workspace/`` 里，下一轮重算 + 重新踩一遍同样的坑（2026-09-20 实况：临时脚本先后
被查出"相对导入按父目录解析"与"父包不动点未展开"两个 bug，两次都产出过**假的死代码清单**，
若照单删就是直接崩包）。

本工具把这件事**固化成可复跑、可门禁、结果可落盘**的审计：
- 语义与 Python 真实导入一致（相对导入按「模块 vs 包」分支、祖先 ``__init__.py`` 隐式执行、迭代到不动点）；
- 结果写 ``tools/baselines/training_reachability.json`` 作为**持久索引**，下次先读它、只做增量核对；
- ``--check`` 比对存量索引与实时计算，有漂移即退出码 1（可进 CI），不再"每轮重算还记不住"。

## 用法

::

    # 算并刷新索引（默认全部有 training/source 的机器人）
    python tools/audit_training_reachability.py --write

    # 只算某台机器人的清单（调试用）
    python tools/audit_training_reachability.py --robot unitree_go2 --list

    # 门禁：现算结果与索引不一致 → 退出码 1
    python tools/audit_training_reachability.py --check

## 判据（与 Python 导入语义对齐，逐条都是踩过坑才加上的）

1. **种子** = 每个 ``training/profiles/*.json`` 的 ``entrypoints`` 指向的模块；**源码根也由
   profile 自带的 ``source_root`` 决定**（两者都不写死）。这就是产品真实入口 ——
   不是"看着像入口"的文件。
2. **相对导入**：``from .x import y`` 在普通模块里以**父包**为基准，在包的 ``__init__.py``
   里以**包自身**为基准。（首版漏了后者，把 ``mdp/__init__.py`` 的 ``from .rewards import *``
   算到不存在的 ``go2.rewards``，于是 ``mdp/*`` 全被误判成死代码。）
3. **祖先 ``__init__.py`` 隐式执行**：导入 ``a.b.c`` 会依次执行 ``a/__init__.py``、``a/b/__init__.py``，
   它们内部的 import 同样生效；因此必须**迭代到不动点**，而不是"一次 BFS + 事后给祖先打个保护标"。
   （第二版就错在这里：``parkour/mdp/__init__.py`` 明明 ``from .rewards import *``，
   它的 4 个兄弟模块仍被算成可删。）
4. **字符串边**：``class_name = "local_tasks...."`` 这类配置里的动态引用也算边（mjlab/rl_cfg 常用）。
5. ``__pycache__`` 忽略；不可达模块若同时是**可达模块的祖先包**，归入 ``protected`` 而非 ``deletable``。

**本工具只读不删**：它给出 ``deletable`` 清单与证据，删不删是人的决定（B8 流程里还要跑
``audit_porting_admission`` + 逐 profile 冒烟验证）。

退出码：0 正常；1 ``--check`` 发现漂移。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = PROJECT_ROOT / "assets" / "robots"
INDEX_PATH = PROJECT_ROOT / "tools" / "baselines" / "training_reachability.json"
SCHEMA = "training-reachability-1.0"


def modules_of(source_root: Path) -> dict[str, Path]:
    """模块名 → 文件（``a/b/__init__.py`` 记为 ``a.b``）。"""
    found: dict[str, Path] = {}
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = list(path.relative_to(source_root).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            found[".".join(parts)] = path
    return found


def _longest_existing(text: str, mod_to_path: dict[str, Path]) -> str | None:
    """把 ``a.b.c`` 收敛到**实际存在的**最长模块前缀（``a.b.c.x`` 缺失则试 ``a.b.c``…）。"""
    text = text.split(":", 1)[0].strip().rstrip(",;'\"")
    while text:
        if text in mod_to_path:
            return text
        if "." not in text:
            return None
        text = text.rsplit(".", 1)[0]
    return None


def auto_seeds(
    profiles_dir: Path, mod_to_path: dict[str, Path]
) -> tuple[list[str], list[str]]:
    """种子 = profiles 的 ``entrypoints`` 指向的模块（产品真入口）；返回 (种子, 解析不到的)。

    **不假设前缀叫 ``local_tasks``**。踩过的坑（2026-09-20）：写死该前缀后，zex-w 等
    上游栈是 ``robot.*`` 的包**一个种子都取不到**，工具照样输出"可达 0 / 全部可删"——
    一条足以让人删光整包的**假结论**。故这里改为"按最长存在前缀解析，解析不到就记入
    ``unresolved`` 并在上层 fail-closed"。
    """
    seeds: set[str] = set()
    unresolved: list[str] = []
    # 顶层模块名：用来区分"**声称是包内代码**却解析不到"（真告警）与"框架/外部依赖的
    # entrypoint"（如 ``mjlab.tasks.velocity.rl:VelocityOnPolicyRunner``，它在 adapter
    # venv 里，本就不该在包内——报它只会制造噪声）。
    package_tops = {name.split(".")[0] for name in mod_to_path}
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        for value in (data.get("entrypoints") or {}).values():
            if not isinstance(value, str) or not value.strip():
                continue
            resolved = _longest_existing(value, mod_to_path)
            if resolved:
                seeds.add(resolved)
                continue
            if value.strip().split(":", 1)[0].split(".")[0] in package_tops:
                unresolved.append(value.strip())
    return sorted(seeds), sorted(set(unresolved))


class Graph:
    """模块导入图 + 可达性（含判据 2/3/4）。"""

    def __init__(self, mod_to_path: dict[str, Path]) -> None:
        self.mod_to_path = mod_to_path
        self.edges: dict[str, set[str]] = defaultdict(set)

    def build(self) -> None:
        for name, path in self.mod_to_path.items():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._add(name, self._resolve(alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        target = self._resolve_relative(name, node.level, node.module)
                        self._add(name, target)
                        for alias in node.names:
                            if target and f"{target}.{alias.name}" in self.mod_to_path:
                                self._add(name, f"{target}.{alias.name}")
                    else:
                        # 绝对导入同样有「``from <pkg> import <submodule>``」这条形态，必须与
                        # 相对分支一样补出 ``<pkg>.<alias>`` 子模块边。踩过的坑（2026-09-20，
                        # **第 4 个 bug**）：``locomotion/wtw.py`` 的
                        # ``from ...tasks.locomotion import wtw_mdp`` 只产生了包边，``wtw_mdp``
                        # 因此被误判可删 —— 而它正是 ``go2-wtw`` profile 的入口，照删必 ImportError。
                        # （由子智能体独立交叉验证抓出，我的自证没抓到：自证只重复自己的假设。）
                        target = self._resolve(node.module or "")
                        self._add(name, target)
                        for alias in node.names:
                            if target and f"{target}.{alias.name}" in self.mod_to_path:
                                self._add(name, f"{target}.{alias.name}")
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # 判据 4：配置里的字符串引用。
                    for prefix in ("local_tasks.", "robot."):
                        index = node.value.find(prefix)
                        while index >= 0:
                            token = node.value[index:].split()[0].rstrip(",;'\"")
                            self._add(name, self._resolve(token))
                            index = node.value.find(prefix, index + 1)

    def _add(self, src: str, dst: str | None) -> None:
        if dst and dst != src:
            self.edges[src].add(dst)

    def _resolve(self, text: str) -> str | None:
        """把 ``a.b.c`` 收敛到**实际存在的**最长模块前缀（与 ``auto_seeds`` 同一实现）。"""
        return _longest_existing(text, self.mod_to_path)

    def _resolve_relative(self, module_name: str, level: int, sub: str | None) -> str | None:
        """判据 2：``__init__.py`` 里的相对导入以包自身为基准。"""
        parts = module_name.split(".")
        is_package = self.mod_to_path[module_name].name == "__init__.py"
        base = parts if is_package else parts[:-1]
        if level > 1:
            base = base[: max(0, len(base) - (level - 1))]
        candidate = ".".join([*base, *(sub.split(".") if sub else [])])
        return self._resolve(candidate)

    def _bfs(self, starts) -> set[str]:
        seen: set[str] = set()
        stack = [s for s in starts if s in self.mod_to_path]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.edges.get(current, ()))
        return seen

    def reachable(self, seeds: list[str]) -> set[str]:
        """判据 3：迭代到不动点（祖先 ``__init__.py`` 也会执行，其 import 边必须展开）。

        **必须**把 ``new_roots`` 过滤到"真实存在的模块"。踩过的坑（2026-09-20，代价惨重）：
        ``modules_of`` 会收进任何 ``.py``，包括**所在目录没有 ``__init__.py``** 的文件
        （那种模块名 ``a.b.c`` 的祖先 ``a.b`` 根本不是模块）。此时 ``ancestors - reach``
        永远含这些幻影名字，而 ``_bfs`` 开头会把它们过滤掉 ⇒ 这一轮什么都不加 ⇒
        ``reach`` 不变 ⇒ ``new_roots`` 下一轮还是同一批 ⇒ **死循环 100% CPU 假死**，
        表现出来像"命令卡住"，实际是脚本在满核空转（还占着输出文件的句柄，
        导致后续任何重定向报"文件正由另一进程使用"）。
        加上过滤后本循环可证终止：每轮要么新增至少一个真实模块，要么直接返回。
        """
        reach = self._bfs(seeds)
        while True:
            ancestors: set[str] = set()
            for name in reach:
                parts = name.split(".")
                for index in range(1, len(parts)):
                    ancestors.add(".".join(parts[:index]))
            new_roots = {n for n in ancestors - reach if n in self.mod_to_path}
            if not new_roots:
                return reach
            reach |= self._bfs(new_roots)


def source_roots_of(package_root: Path, profiles_dir: Path) -> list[Path]:
    """包内**实际**的源码根：逐 profile 读 ``source_root``（缺省 ``training/source``）。

    不能写死 ``training/source`` —— profile 可以自带 ``source_root``（``validate_training_smoke``
    就是照此解析的）。踩过的坑（2026-09-20）：写死之后 g1 的 entrypoints
    （``src.tasks.amp_loco...``）一个都解析不到，工具报出"可达 1 / 可删 85"的**假结论**。
    """
    roots: list[Path] = []
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        rel = str(data.get("source_root") or "training/source").replace("\\", "/")
        candidate = Path(rel) if Path(rel).is_absolute() else package_root / rel
        candidate = candidate.resolve()
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    if not roots:
        fallback = (package_root / "training" / "source").resolve()
        if fallback.is_dir():
            roots.append(fallback)
    return roots


def audit_robot(robot_id: str) -> dict | None:
    package_root = ASSETS_ROOT / robot_id
    profiles_dir = package_root / "training" / "profiles"
    roots = source_roots_of(package_root, profiles_dir)
    if not roots:
        return None
    mod_to_path: dict[str, Path] = {}
    for root in roots:
        for name, path in modules_of(root).items():
            mod_to_path.setdefault(name, path)
    seeds, unresolved = auto_seeds(profiles_dir, mod_to_path)
    graph = Graph(mod_to_path)
    graph.build()
    reach = graph.reachable(seeds)

    ancestors: set[str] = set()
    for name in reach:
        parts = name.split(".")
        for index in range(1, len(parts)):
            ancestors.add(".".join(parts[:index]))

    unreachable = set(mod_to_path) - reach
    protected = sorted(unreachable & ancestors)
    deletable = sorted(unreachable - ancestors)

    # fail-closed：没有入口种子 ⇒ 可达性无从谈起，"全部不可达"是伪结论。
    # 此时**拒绝给出 deletable**（宁可不删，也不能给出删光整包的建议），并让上层报警/非零退出。
    warning = None
    if not seeds:
        warning = "no_entrypoint_seeds"
        deletable = []
    elif unresolved:
        warning = "unresolved_entrypoints"

    return {
        "package_root": package_root.relative_to(PROJECT_ROOT).as_posix(),
        "source_roots": [r.relative_to(PROJECT_ROOT).as_posix() for r in roots],
        "seed_modules": seeds,
        "entrypoints_unresolved": unresolved,
        "module_count": len(mod_to_path),
        "reachable_count": len(reach),
        "unreachable_count": len(unreachable),
        # 判据 5：祖先包被 Python 隐式执行 ⇒ 不可删，单列以免误伤。
        "protected_ancestors": protected,
        "deletable": deletable,
        "warning": warning,
    }


def iter_robots(only: str | None) -> list[str]:
    if only:
        return [only]
    return sorted(
        path.name for path in ASSETS_ROOT.iterdir()
        if path.is_dir() and (path / "training" / "profiles").is_dir()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B8 训练包可达性审计")
    parser.add_argument("--robot", default=None, help="只审计该 robot_id")
    parser.add_argument("--list", action="store_true", help="打印逐模块清单")
    parser.add_argument("--write", action="store_true", help=f"把结果写入索引 {INDEX_PATH}")
    parser.add_argument("--check", action="store_true", help="与存量索引比对，漂移则退出码 1")
    args = parser.parse_args(argv)

    robots = iter_robots(args.robot)
    report: dict = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "「可达性」判据见 tools/audit_training_reachability.py 头部 docstring；deletable 只是候选，删前仍需 audit_porting_admission + 逐 profile 冒烟。",
        "robots": {},
    }
    warned = False
    for robot_id in robots:
        entry = audit_robot(robot_id)
        if entry is None:
            continue
        report["robots"][robot_id] = entry
        print(
            f"{robot_id:<20} 模块 {entry['module_count']:>4} / 可达 {entry['reachable_count']:>4} / "
            f"不可达 {entry['unreachable_count']:>4}（可删 {len(entry['deletable'])} + "
            f"祖先保护 {len(entry['protected_ancestors'])}）"
        )
        if entry["warning"] == "no_entrypoint_seeds":
            warned = True
            print("    !! 未解析到任何入口种子 → 可达性无效，deletable 已置空（拒绝给出删包建议）")
        elif entry["warning"] == "unresolved_entrypoints":
            warned = True
            print(f"    !! 有 entrypoints 解析不到模块：{entry['entrypoints_unresolved'][:3]}")
        if args.list:
            for name in entry["deletable"]:
                print(f"       del? {name}")

    if args.write:
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"\n索引已写入 {INDEX_PATH.relative_to(PROJECT_ROOT).as_posix()}")

    if args.check:
        if not INDEX_PATH.exists():
            print(f"\n!! 索引不存在：{INDEX_PATH.relative_to(PROJECT_ROOT).as_posix()}（先跑 --write）")
            return 1
        old = json.loads(INDEX_PATH.read_text(encoding="utf-8-sig")).get("robots", {})
        drift: list[str] = []
        for robot_id, entry in report["robots"].items():
            before = old.get(robot_id)
            if before is None:
                drift.append(f"{robot_id}: 索引无记录")
                continue
            for field in ("module_count", "reachable_count", "deletable", "protected_ancestors"):
                if before.get(field) != entry.get(field):
                    drift.append(f"{robot_id}.{field}: {before.get(field)} -> {entry.get(field)}")
        for robot_id in old:
            if robot_id not in report["robots"]:
                drift.append(f"{robot_id}: 索引有记录但已无 training/source")
        if drift:
            print(f"\n!! 可达性索引漂移 {len(drift)} 处：")
            for item in drift[:20]:
                print(f"   {item}")
            return 1
        print("\n可达性索引一致。")
    if warned:
        print("\n!! 存在 fail-closed 告警（见上）：入口种子缺失时不给删包建议。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
