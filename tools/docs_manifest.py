#!/usr/bin/env python3
"""内容插件清单工具：稳定 ID、别名解析、链接检查、索引渲染。

设计对应 dsh 的插件思想：**身份是 id，不是路径**。
`00_know/_manifest.json` 是 00_know 文档的单一身份来源；改名只改 manifest，
旧名记录在 `aliases` / `renamed_from`，仓库不保留旧文件。

用法：
    python tools/docs_manifest.py --check
    python tools/docs_manifest.py --index
    python tools/docs_manifest.py --where rl-survey
    python tools/docs_manifest.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "00_know" / "_manifest.json"

_LINK_RE = re.compile(r"\]\(([^)]+)\)")
_FENCE_RE = re.compile(r"```.*?```", re.S)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_STATUS = {"active", "archived"}


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_manifest(path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"manifest 不存在：{path}")
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ValueError("manifest 顶层必须是对象")
    return data


def _docs(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    docs = manifest.get("docs")
    if not isinstance(docs, list):
        raise ValueError("manifest.docs 必须是列表")
    return docs


def _mask_code(text: str) -> str:
    """把代码块/行内代码替换成空格，保留换行以维持行号。"""

    def _blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = _FENCE_RE.sub(_blank, text)
    return _INLINE_CODE_RE.sub(_blank, text)


def _iter_links(path: Path) -> Iterable[Tuple[int, str]]:
    text = _mask_code(path.read_text(encoding="utf-8"))
    for match in _LINK_RE.finditer(text):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1].strip()
        target = raw.split()[0] if raw.split() else ""
        if not target:
            continue
        line = text.count("\n", 0, match.start()) + 1
        yield line, target


def _resolve_link(doc_path: Path, target: str) -> Optional[Path]:
    if not target or target.startswith("#"):
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        return None
    clean = unquote(target.split("#", 1)[0].strip())
    if not clean:
        return None
    if clean.startswith("/"):
        return (ROOT / clean.lstrip("/")).resolve()
    return (doc_path.parent / clean).resolve()


def validate(manifest: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    schema = str(manifest.get("schema") or "")
    if not schema.startswith("knowledge-manifest-"):
        errors.append(f"schema 不认识：{schema!r}")
    docs = _docs(manifest)
    if not docs:
        errors.append("docs 不能为空")

    ids: set[str] = set()
    paths: set[str] = set()
    legacy_seen: set[str] = set()
    entries: Dict[str, Dict[str, Any]] = {}

    for doc in docs:
        if not isinstance(doc, dict):
            errors.append("docs 中存在非对象条目")
            continue
        doc_id = str(doc.get("id") or "")
        rel_path = str(doc.get("path") or "").replace("\\", "/")
        title = str(doc.get("title") or "")
        status = str(doc.get("status") or "")
        if not doc_id:
            errors.append(f"{rel_path or '<no path>'}: 缺少 id")
        elif doc_id in ids:
            errors.append(f"id 重复：{doc_id!r}")
        else:
            ids.add(doc_id)
            entries[doc_id] = doc
        if not rel_path:
            errors.append(f"{doc_id or '<no id>'}: 缺少 path")
        elif Path(rel_path).is_absolute():
            errors.append(f"{doc_id}: path 必须是仓库相对路径：{rel_path!r}")
        elif rel_path in paths:
            errors.append(f"path 重复：{rel_path!r}")
        else:
            paths.add(rel_path)
        if status not in _STATUS:
            errors.append(f"{doc_id}: status {status!r} 不在 {sorted(_STATUS)}")
        if not title:
            errors.append(f"{doc_id}: 缺少 title")
        target = ROOT / rel_path
        if rel_path and not target.exists():
            errors.append(f"{doc_id}: path 不存在：{rel_path}")

        for field in ("aliases", "renamed_from"):
            values = doc.get(field) or []
            if not isinstance(values, list):
                errors.append(f"{doc_id}: {field} 必须是列表")
                continue
            for value in values:
                value = str(value).replace("\\", "/")
                if not value:
                    continue
                if value in legacy_seen:
                    errors.append(f"{field} 重复：{value!r}")
                legacy_seen.add(value)
                if value == rel_path:
                    errors.append(f"{doc_id}: {field} 不能等于规范 path：{value!r}")

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        doc_id = str(doc.get("id") or "")
        for dep in doc.get("depends_on") or []:
            if str(dep) not in ids:
                errors.append(f"{doc_id}: depends_on 引用了未知 id {dep!r}")
        tools = doc.get("tools") or []
        if not isinstance(tools, list) or any(not isinstance(t, str) for t in tools):
            errors.append(f"{doc_id}: tools 必须是字符串列表")
        else:
            for tool in tools:
                if not (ROOT / "tools" / tool).is_file():
                    errors.append(f"{doc_id}: tools 引用了不存在的工具 {tool!r}")

    return errors


def check_links(manifest: Dict[str, Any]) -> Tuple[List[str], int]:
    errors: List[str] = []
    checked = 0
    for doc in _docs(manifest):
        if not isinstance(doc, dict) or doc.get("status") != "active":
            continue
        rel_path = str(doc.get("path") or "").replace("\\", "/")
        doc_path = ROOT / rel_path
        if not doc_path.is_file():
            continue
        for line, target in _iter_links(doc_path):
            resolved = _resolve_link(doc_path, target)
            if resolved is None:
                continue
            checked += 1
            if not resolved.exists():
                errors.append(f"{rel_path}:{line}: 链接目标不存在：{target!r}")
    return errors, checked


def _norm_ref(ref: str) -> str:
    ref = ref.strip().replace("\\", "/")
    while ref.startswith("./"):
        ref = ref[2:]
    return ref


def _doc_keys(doc: Dict[str, Any]) -> set[str]:
    keys = {
        str(doc.get("id") or ""),
        str(doc.get("path") or "").replace("\\", "/"),
        str(doc.get("title") or ""),
    }
    path = str(doc.get("path") or "").replace("\\", "/")
    if path:
        keys.add(Path(path).name)
    for field in ("aliases", "renamed_from"):
        for alias in doc.get(field) or []:
            alias = str(alias).replace("\\", "/")
            keys.add(alias)
            if alias:
                keys.add(Path(alias).name)
    return {_norm_ref(item) for item in keys if item}


def resolve(ref: str, manifest: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    manifest = manifest or load_manifest()
    wanted = _norm_ref(ref)
    for doc in _docs(manifest):
        if not isinstance(doc, dict):
            continue
        if wanted in _doc_keys(doc):
            return doc
    return None


def render_index(manifest: Dict[str, Any]) -> str:
    rows = ["| id | title | status | path |", "|---|---|---|---|"]
    for doc in _docs(manifest):
        if not isinstance(doc, dict):
            continue
        rows.append(
            f"| {doc.get('id', '')} | {doc.get('title', '')} | "
            f"{doc.get('status', '')} | `{doc.get('path', '')}` |"
        )
    return "\n".join(rows)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="内容插件清单：校验、解析、索引")
    parser.add_argument("--check", action="store_true", help="校验 manifest 与文档内相对链接")
    parser.add_argument("--index", action="store_true", help="输出 Markdown 索引")
    parser.add_argument("--where", metavar="REF", help="按 id/path/title/alias 解析文档")
    parser.add_argument("--json", action="store_true", help="输出 manifest JSON")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest()
    except Exception as exc:  # noqa: BLE001 — CLI 边界，直接报错
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.index:
        print(render_index(manifest))
        return 0

    if args.where:
        doc = resolve(args.where, manifest)
        if doc is None:
            print(f"[FAIL] 未知文档：{args.where!r}", file=sys.stderr)
            return 1
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0

    errors = validate(manifest)
    link_errors, checked = check_links(manifest)
    errors.extend(link_errors)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    docs = _docs(manifest)
    legacy = sum(
        len(doc.get("aliases") or []) + len(doc.get("renamed_from") or [])
        for doc in docs
        if isinstance(doc, dict)
    )
    print(f"[OK] manifest ok: {len(docs)} docs / {legacy} legacy names / {checked} links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
