#!/usr/bin/env python3
"""N5：仿真分层的**声明—消费**静态门禁（基础仿真 vs 高级仿真）。

## 为什么要有它

任务清单 H26 曾声称"面板归属写成纯函数 `sensor_panels.js::PANEL_OWNERSHIP` + `panelVisible()`
（未知面板 fail-closed），断言扩到 13 组进 CI"。**2026-09-16 审计核实：这些都不存在** ——
全仓没有 `PANEL_OWNERSHIP` 符号、`sensor_panels.js` 也没有该函数，`backend/test_*.py` 零引用，
CI 不跑前端断言。（唯一同名的是 app.js 里 URL 参数 `panel=1/0` 的面板显隐开关，与"观测面板归属"无关。）

**真实机制**是：`web/sim2sim/index.html` 里给元素打 `data-surface="advanced"`，
`app.js` 用 `querySelectorAll('[data-surface="advanced"]')` 把它们按 `SHOW_ADVANCED_PANELS` 显隐。
分层本身**是有实现的**（粗粒度：整个传感器坞在基础仿真里隐藏），但没有 asserted 的契约。

本门禁守**声明与消费两端都在**（少任一端，分层就静默失效）：
1. HTML 至少有一处 `data-surface="advanced"`；
2. **传感器坞必须声明 advanced**（基础仿真的定义是「本体 + 本体感知」，不应出现外部传感器面板）；
3. `app.js` 必须**消费**这个声明（选择器 + 按开关隐藏）；
4. `app.js` 必须定义 `SHOW_ADVANCED_PANELS`（否则消费端引用了不存在的开关）。

## 边界（很重要）

**静态扫描源码，不渲染浏览器**：绿 = "声明与消费都在"，**不等于**"页面在浏览器里显示正确"。
真正的渲染行为需要浏览器（本仓容器内没有），这一条不能靠本门禁声称已验证。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "web" / "sim2sim" / "index.html"
APP_JS = ROOT / "web" / "sim2sim" / "app.js"

#: 基础仿真的定义（app.js 注释）——传感器坞属于高级仿真
REQUIRED_ADVANCED_IDS = ("sensorDock",)


def audit(html_path: Path | None = None, js_path: Path | None = None) -> dict:
    html_path = html_path or INDEX_HTML
    js_path = js_path or APP_JS
    checks: list[dict] = []

    def check(name: str, ok: bool, evidence: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "evidence": evidence})

    if not html_path.is_file() or not js_path.is_file():
        return {
            "ok": False,
            "checks": [{"check": "两个文件都在", "ok": False, "evidence": f"{html_path} / {js_path}"}],
            "problems": ["缺 index.html 或 app.js"],
            "renders_browser": False,
        }

    html = html_path.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")

    declarations = re.findall(r'data-surface=["\']([^"\']+)["\']', html)
    check(
        "HTML 至少有一处 data-surface 声明",
        bool(declarations),
        f"声明 {len(declarations)} 处：{sorted(set(declarations))}",
    )

    for element_id in REQUIRED_ADVANCED_IDS:
        # 该元素标签里必须带 advanced 声明（基础仿真不得显示外部传感器面板）
        pattern = re.compile(
            rf'<[^>]*\bid=["\']{re.escape(element_id)}["\'][^>]*\bdata-surface=["\']advanced["\']'
            rf'|<[^>]*\bdata-surface=["\']advanced["\'][^>]*\bid=["\']{re.escape(element_id)}["\']'
        )
        check(
            f"#{element_id} 声明为 advanced（基础仿真不显示）",
            bool(pattern.search(html)),
            "命中" if pattern.search(html) else "未命中：该元素没有 advanced 声明",
        )

    consumer = re.search(r'querySelectorAll\(\s*[\'"`]\[data-surface="advanced"\][\'"`]\s*\)', js)
    check(
        "app.js 消费该声明（选择器）",
        bool(consumer),
        f"第 {js[:consumer.start()].count(chr(10)) + 1} 行" if consumer else "找不到 querySelectorAll('[data-surface=\"advanced\"]')",
    )

    hide = re.search(r"\.hidden\s*=\s*!\s*SHOW_ADVANCED_PANELS", js)
    check(
        "基础仿真下把 advanced 元素隐藏（fail-closed：不是显式显示）",
        bool(hide),
        f"第 {js[:hide.start()].count(chr(10)) + 1} 行" if hide else "找不到 el.hidden = !SHOW_ADVANCED_PANELS",
    )

    switch = re.search(r"\bSHOW_ADVANCED_PANELS\s*=", js)
    check(
        "app.js 定义了 SHOW_ADVANCED_PANELS 开关",
        bool(switch),
        f"第 {js[:switch.start()].count(chr(10)) + 1} 行" if switch else "未定义",
    )

    problems = [item["check"] for item in checks if not item["ok"]]
    return {
        "ok": not problems,
        "declarations": sorted(set(declarations)),
        "checks": checks,
        "problems": problems,
        # 如实声明边界
        "renders_browser": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N5 仿真分层声明—消费门禁")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 74)
        print("N5 仿真分层（基础/高级）声明—消费门禁")
        print("=" * 74)
        for item in report["checks"]:
            print(f"{'✓' if item['ok'] else '✗'} {item['check']}" + (f"（{item['evidence']}）" if item["evidence"] else ""))
        print("-" * 74)
        print("注意：**静态扫描，不渲染浏览器** —— 绿 = 声明与消费都在，不等于页面显示正确。")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
