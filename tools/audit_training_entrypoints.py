"""训练 profile entrypoints 的零依赖静态审计（B22）—— 「entrypoint 指向的符号存在」进 CI。

## 背景（B22 事故）

microduck 包的 12 个 training profile 声明了 entrypoints
（``mjlab_microduck.tasks.microduck_velocity_env_cfg:make_microduck_velocity_env_cfg``
等），但工作树源码被截断，包根本 import 不了——静态审计缺位让「14 机型可训练」
（B14）虚盖了很久。本工具把这条契约变成不依赖运行环境的静态事实。

## 规则（纯 AST + 文件系统，标准库 only）

- **不 import 包源码、不 import mjlab/torch/fastapi**：``ast.parse`` 文本即可。
- 扫描 ``assets/robots/*/training/profiles/*.json``，对每个 profile 的
  ``entrypoints.env`` / ``entrypoints.runner``（及 ``runner_class`` / ``configure``，
  若存在）逐条静态解析。
- 模块路径：以 profile 的 ``source_root``（缺省 ``training/source``）为根，把
  ``a.b.c`` 解析为 ``<root>/a/b/c.py`` 或 ``<root>/a/b/c/__init__.py``；两处都在时
  报 .py 优先。规则对 ``local_tasks.robot_profiles``（go2）、``robot.config.env_cfgs``
  （zex-w）、``go2w_velocity``（go2w）这类顶层模块一视同仁。
- 符号存在性：ast 解析目标模块，收集**模块级绑定**（``def`` / ``class`` / 赋值 /
  import 绑定，含 try/if/with 守卫下的模块级绑定）。若符号只来自
  ``from .x import name`` / ``from pkg import name`` 的再导出，允许沿链追踪，
  深度上限 3 跳，带环检测；包内 ``from pkg import submodule`` 解析到子模块文件。
- ``__all__`` 不是存在性证据：``__all__`` 里有、源里没有的算缺失。

## external（不判红，如实单列）

目标模块（或再导出链）的**顶层段在 source_root 下不存在**（如 ``mjlab.tasks.velocity.rl``
——安装的第三方依赖）时，零依赖静态审计天然不可验，该条目归入 ``external`` 单列、
**不判红**；顶层段存在但模块文件缺失 / 符号缺失 / 源码不可解析一律判红。
``audit(..., external_is_missing=True)`` 可一键切换为严格口径（external 也判红），
供主控裁决。已知残留盲区：整个本地顶层包被整体删除时也会归入 external——external
清单逐条列出，供人工核对是否确为第三方依赖。

## 退出码（可进 CI 的门禁）

- 任何缺失（模块缺失 / 符号缺失 / 解析失败）→ ``exit 1``；
- 全部可解析 → ``exit 0``。

纯只读审计，**不修改任何文件**。

用法::

    python tools/audit_training_entrypoints.py
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"

#: 缺省源码根（profile 未写 source_root 时）。
DEFAULT_SOURCE_ROOT = "training/source"

#: 需要静态解析的 entrypoint 键（env/runner 必查，runner_class/configure 若存在才查）。
ENTRY_KEYS = ("env", "runner", "runner_class", "configure")

#: 再导出追踪深度上限（首模块之外的跳数）。
MAX_REEXPORT_HOPS = 3

_TRY_TYPES: tuple[type, ...] = (ast.Try,) + (
    (ast.TryStar,) if hasattr(ast, "TryStar") else ()
)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------- 模块路径解析


def _resolve_module(root: Path, dotted: str) -> Path | None:
    """把 ``a.b.c`` 解析为 ``<root>/a/b/c.py`` 或 ``<root>/a/b/c/__init__.py``。

    两处都在时 .py 优先；都不在返回 None。
    """
    parts = dotted.split(".")
    if not all(parts):
        return None
    # 仅末段补 .py（a/b/c → a/b/c.py；单段 m → m.py）
    mod_file = root.joinpath(*parts[:-1], parts[-1] + ".py")
    if mod_file.is_file():
        return mod_file
    pkg_init = root.joinpath(*parts, "__init__.py")
    if pkg_init.is_file():
        return pkg_init
    return None


def _top_level_exists(root: Path, dotted: str) -> bool:
    """模块路径的顶层段（第一段）是否在 source_root 下存在。"""
    top = dotted.split(".")[0]
    return (root / top).exists() or (root / f"{top}.py").is_file()


# ------------------------------------------------------------- 模块级绑定收集


def _iter_module_level(stmts: list[ast.stmt]):
    """遍历模块级语句，进入 try/if/with/for/while 的分支体（守卫下的模块级绑定
    在对应分支执行时同样成立），但**不进入**函数/类作用域。"""
    for stmt in stmts:
        yield stmt
        if isinstance(stmt, _TRY_TYPES):
            yield from _iter_module_level(stmt.body)
            yield from _iter_module_level(stmt.orelse)
            for handler in stmt.handlers:
                yield from _iter_module_level(handler.body)
            yield from _iter_module_level(stmt.finalbody)
        elif isinstance(stmt, (ast.If, ast.With, ast.For, ast.AsyncFor, ast.While)):
            yield from _iter_module_level(stmt.body)
            yield from _iter_module_level(getattr(stmt, "orelse", []))


def _dunder_all_names(value: ast.expr) -> list[str]:
    """提取 ``__all__ = [...]`` / ``__all__ += [...]`` 字面量里的名字。"""
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        names = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                names.append(elt.value)
        return names
    return []


class _ModuleInfo:
    """一个模块的顶层绑定视图。"""

    def __init__(self) -> None:
        #: 符号 -> 绑定种类（def/class/assign/import）
        self.defined: dict[str, str] = {}
        #: ImportFrom 记录：{"module": str|None, "level": int, "names": [(name, asname)]}
        self.imports: list[dict] = []
        #: ``__all__`` 字面量里声明的名字（不是存在性证据，只用于缺失归因）
        self.dunder_all: list[str] = []

    def add_defined(self, name: str, kind: str) -> None:
        self.defined.setdefault(name, kind)


def _collect_module_info(tree: ast.Module) -> _ModuleInfo:
    info = _ModuleInfo()
    for stmt in _iter_module_level(tree.body):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.add_defined(stmt.name, "def")
        elif isinstance(stmt, ast.ClassDef):
            info.add_defined(stmt.name, "class")
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    if target.id == "__all__":
                        info.dunder_all.extend(_dunder_all_names(stmt.value))
                    info.add_defined(target.id, "assign")
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name):
                info.add_defined(stmt.target.id, "assign")
        elif isinstance(stmt, ast.AugAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id == "__all__":
                info.dunder_all.extend(_dunder_all_names(stmt.value))
        elif isinstance(stmt, ast.ImportFrom):
            info.imports.append({
                "module": stmt.module,
                "level": stmt.level,
                "names": [(alias.name, alias.asname) for alias in stmt.names],
            })
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                # import a.b.c as x 绑定 x；import a.b.c 绑定 a
                info.add_defined(alias.asname or alias.name.split(".")[0], "import")
    return info


def _package_parts(root: Path, module_file: Path) -> list[str]:
    """模块文件的所属包段（``__init__.py`` 的所属包含它自己那一级）。"""
    parts = list(module_file.relative_to(root).parts)
    return parts[:-1]


def _from_import_target(
    pkg_parts: list[str], imp: dict,
) -> tuple[str | None, str | None]:
    """把一条 ImportFrom 解析为源模块的 dotted 路径（相对于 root）。

    返回 (dotted, 错误原因)。``from .x import y`` → ``pkg.x``；
    ``from ..x import y`` → 上一级；``from . import x`` → 所属包自身（x 是名字）。
    """
    level, module = imp["level"], imp["module"]
    if level:
        drop = level - 1
        if drop > len(pkg_parts):
            return None, f"相对导入越出 source_root（level={level}）"
        parts = list(pkg_parts[: len(pkg_parts) - drop]) if drop else list(pkg_parts)
    else:
        parts = []
    if module:
        parts += module.split(".")
    if not parts:
        return None, "无法解析导入源"
    return ".".join(parts), None


# --------------------------------------------------------------- 符号存在性


def _lookup_symbol(root: Path, dotted: str, symbol: str) -> tuple[str, str]:
    """在 source_root 下静态追踪 ``dotted:symbol`` 是否存在。

    返回 (status, detail)，status ∈ {"ok", "external", "missing"}：
    - ``ok``       —— 模块级绑定命中（含沿再导出链追到定义处）；
    - ``external`` —— 链条走出 source_root（顶层段不存在，第三方依赖）；
    - ``missing``  —— 本地可判定的缺失（模块缺/符号缺/不可解析/环/深度用尽）。
    """
    visited: list[str] = []
    cur = dotted
    hops = 0
    while True:
        if cur in visited:
            chain = " -> ".join(visited + [cur])
            return "missing", f"再导出链成环：{chain}"
        visited.append(cur)

        module_file = _resolve_module(root, cur)
        if module_file is None:
            if not _top_level_exists(root, cur):
                return "external", f"模块 {cur} 不在 source_root 下（外部依赖，静态不可验）"
            return "missing", (
                f"模块 {cur} 在 source_root 下不可解析（无 .py 亦无 __init__.py）"
            )

        try:
            tree = ast.parse(module_file.read_text(encoding="utf-8-sig"),
                             filename=str(module_file))
        except SyntaxError as exc:
            return "missing", (
                f"源码不可解析（SyntaxError）: {module_file.name}:{exc.lineno}"
            )
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            return "missing", f"源码不可读取: {module_file}（{exc}）"

        info = _collect_module_info(tree)
        kind = info.defined.get(symbol)
        if kind is not None:
            return "ok", f"{kind} @ {module_file.relative_to(root)}"

        # 包内 `from pkg import submodule` / `from . import submodule`：
        # 符号若是该包的直接子模块，绑定即成立。
        if module_file.name == "__init__.py":
            pkg_dir = module_file.parent
            if (pkg_dir / f"{symbol}.py").is_file() or (pkg_dir / symbol).is_dir():
                return "ok", f"submodule @ {pkg_dir.relative_to(root) / symbol}"

        if hops >= MAX_REEXPORT_HOPS:
            break

        # 沿 from-import 再导出链走一跳。
        pkg_parts = _package_parts(root, module_file)
        nxt: str | None = None
        for imp in info.imports:
            for name, asname in imp["names"]:
                if (asname or name) != symbol:
                    continue
                src_dotted, err = _from_import_target(pkg_parts, imp)
                if src_dotted is None:
                    return "missing", f"无法解析再导出链（{err}）"
                if imp["module"] is None and imp["level"]:
                    # `from . import x`：x 是子模块名，绑定存在当且仅当子模块存在
                    if _resolve_module(root, f"{src_dotted}.{name}") is not None:
                        return "ok", f"submodule @ {src_dotted}.{name}"
                    continue
                nxt = src_dotted
        if nxt is None:
            if symbol in info.dunder_all:
                return "missing", (
                    f"__all__ 声明了 {symbol}，但 {cur} 内无顶层绑定、亦无可追踪的再导出"
                )
            return "missing", f"{cur} 顶层未定义/未再导出 {symbol}"
        cur = nxt
        hops += 1

    chain = " -> ".join(visited)
    return "missing", (
        f"再导出追踪深度用尽（>{MAX_REEXPORT_HOPS} 跳）仍未找到 {symbol}：{chain}"
    )


def _parse_entrypoint(target: str) -> tuple[str, str] | None:
    """``模块:符号`` 拆分；格式不合法返回 None。"""
    text = target.strip()
    if text.count(":") != 1:
        return None
    module, symbol = text.split(":")
    module, symbol = module.strip(), symbol.strip()
    if not module or not symbol or ".." in module:
        return None
    return module, symbol


# ------------------------------------------------------------------- 审计主体


def audit(*, robots_dir: Path | str = ROBOTS, external_is_missing: bool = False) -> dict:
    """逐包逐 profile 静态审计 entrypoints。``robots_dir`` 可注入（测试用假包目录）。

    返回 dict：``total_packages / total_profiles / total_entrypoints / ok /
    missing（判红项）/ external（不判红，如实单列）/ rows``。
    ``external_is_missing=True`` 时 external 亦计入 missing（严格口径）。
    """
    robots_dir = Path(robots_dir)
    rows: list[dict] = []
    missing: list[dict] = []
    external: list[dict] = []
    total_profiles = 0
    total_entrypoints = 0
    ok_count = 0

    for robot_dir in sorted(p for p in robots_dir.iterdir() if p.is_dir()):
        profiles_dir = robot_dir / "training" / "profiles"
        if not profiles_dir.is_dir():
            continue
        profile_rows: list[dict] = []
        for profile_path in sorted(profiles_dir.glob("*.json")):
            profile = _read_json(profile_path)
            if not profile:
                missing.append({
                    "robot": robot_dir.name, "profile": profile_path.name,
                    "key": "-", "target": "-", "reason": "profile JSON 不可读/非对象",
                })
                profile_rows.append({"profile": profile_path.name, "results": []})
                continue
            total_profiles += 1
            source_root = robot_dir / str(profile.get("source_root", DEFAULT_SOURCE_ROOT))
            entrypoints = profile.get("entrypoints")
            results: list[dict] = []
            if not isinstance(entrypoints, dict) or not entrypoints.get("env"):
                missing.append({
                    "robot": robot_dir.name, "profile": profile_path.name,
                    "key": "env", "target": "-", "reason": "profile 缺 entrypoints.env",
                })
            for key in ENTRY_KEYS:
                target = entrypoints.get(key) if isinstance(entrypoints, dict) else None
                if not target or not isinstance(target, str):
                    continue  # runner_class / configure 等若存在才查
                total_entrypoints += 1
                parsed = _parse_entrypoint(target)
                if parsed is None:
                    status, detail = "missing", (
                        f"entrypoint 需为 '模块:符号'，实际：{target!r}"
                    )
                elif not source_root.is_dir():
                    status, detail = "missing", f"source_root 不存在：{source_root}"
                else:
                    module, symbol = parsed
                    status, detail = _lookup_symbol(source_root, module, symbol)
                row = {
                    "robot": robot_dir.name, "profile": profile_path.name,
                    "key": key, "target": target,
                }
                if status == "ok":
                    ok_count += 1
                elif status == "external":
                    external.append(dict(row, module=target.split(":")[0].strip()))
                    if external_is_missing:
                        missing.append(dict(row, reason=f"{detail}（严格口径：external 判红）"))
                else:
                    missing.append(dict(row, reason=detail))
                results.append(dict(row, status=status, detail=detail))
            profile_rows.append({
                "profile": profile_path.name,
                "source_root": str(profile.get("source_root", DEFAULT_SOURCE_ROOT)),
                "results": results,
            })
        rows.append({"robot": robot_dir.name, "profiles": profile_rows})

    return {
        "total_packages": len(rows),
        "total_profiles": total_profiles,
        "total_entrypoints": total_entrypoints,
        "ok": ok_count,
        "missing": missing,
        "external": external,
        "rows": rows,
    }


def exit_code(report: dict) -> int:
    """门禁语义：任何缺失 → 1；否则 0。external 默认不判红（见模块 docstring）。"""
    return 1 if report["missing"] else 0


def main() -> int:
    report = audit()
    print(f"包 {report['total_packages']} 个 / profile {report['total_profiles']} 个"
          f" / entrypoint {report['total_entrypoints']} 条")
    print(f"  静态可解析：{report['ok']} 条")
    print(f"  external（外部依赖，静态不可验，不判红）：{len(report['external'])} 条")
    print(f"  缺失（判红）：{len(report['missing'])} 条")
    if report["external"]:
        print("\nexternal 明细（顶层段不在 source_root 下，须人工核对确为第三方依赖）：")
        for row in report["external"]:
            print(f"  {row['robot']:<22} {row['profile']:<38} {row['key']:<13}"
                  f" {row['module']}")
    if report["missing"]:
        print("\n缺失明细（包 / profile / entrypoint / 目标 / 原因）：")
        for row in report["missing"]:
            print(f"  {row['robot']:<22} {row['profile']:<38} {row['key']:<13}"
                  f" {row['target']}\n{'':<39}→ {row['reason']}")
    code = exit_code(report)
    if code:
        print("\n审计不通过（exit 1）：存在静态不可解析的 entrypoint。")
    else:
        print("\n审计通过（exit 0）：全部 entrypoint 指向的符号静态存在。")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
