"""**可测量的 UI 细节门禁**：7 项指标全部为 0（12 个页面，真 Chromium）。

## 为什么是"可测量"而不是"看着还行"

用户口径："根据开的浏览器去不断优化 UI，优化具体的细节"。视觉好不好看没法自动判，但**这些
能判**——而且实测一开始没一条是干净的（2026-09-23 首测：对比度 214 处、<11px 文本 190 处、
点击区过小 9 处、无标签字段 5 处）。把它们写成门禁，优化才有"完成"的定义，也不会被人
在后续改动里悄悄弄回去。

| 指标 | 判据 | 为什么这么定 |
|---|---|---|
| `contrast` | 正文 ≥ 4.5:1，≥18px 大字 ≥ 3:1 | WCAG AA；背景**逐层按 alpha 合成**（页面大量用 rgba(…,.15) 做淡底，不合成会把徽章判成假红） |
| `tiny_text` | 计算字号 ≥ 11px | 10px/9px 的说明文字在 1440×900 下已难读；首测有 190 处 |
| `tap_target` | 可点击元素 ≥ 24×24 px | 小按钮实测只有 17~19px 高，鼠标点不准 |
| `a11y` | 表单控件有 label/aria-label；按钮有可访问名 | 屏幕阅读器与自动化都依赖它 |
| `clipped` | 文本不被裁（无省略号的硬裁） | 视觉上"字被吃掉一半"，且没人会报 |
| `offscreen` | 不横向越出视口 | 1440 下不该出现横向溢出 |
| `dup_id` | 无重复 id | 重复 id 让 `$("x")` 取到哪个全看运气 |

**两条如实的例外**（写在这里，免得日后被当成"漏测"）：
* **禁用态**（`disabled` / `aria-disabled` / 祖先 opacity < 0.75）不判对比度 —— WCAG 明确豁免，
  测它只会得到假红（原先 #toGate 那条 2.07 就是这么来的）；
* **资源加载失败**（`Failed to load resource`）不判页面错误 —— 数据缺失类降级是页面设计行为。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.e2e]

PAGES = [
    "workbench.html", "dashboard.html", "assets.html", "training_create.html",
    "training_list.html", "training_monitor.html", "evaluation.html", "artifacts.html",
    "deploy.html", "exports.html", "navigation_editor.html", "advanced_sim.html",
]

#: 需要先"摆成某个状态"再量的页面 —— 默认态的页面量不到藏在浮层/折叠区里的东西。
#: `advanced_sim.html` 的场景编辑器**默认收起**（2026-09-23 布局修复），只量默认态等于
#: 放弃覆盖那 360px 浮层里的全部控件 ⇒ 两个态都量。
_OPEN_ADVANCED_EDITOR = "open-advanced-editor"
CASES = [(name, None) for name in PAGES] + [("advanced_sim.html", _OPEN_ADVANCED_EDITOR)]

# 探针：在页面里跑，返回 7 类问题的逐条明细（空数组 = 该项达标）
PROBE = r"""
(() => {
  const sel = (el) => el.id ? `#${el.id}` : (el.tagName.toLowerCase()
    + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0,2).join('.') : ''));
  const dim = (el) => {
    let o = 1, node = el;
    while (node && node !== document.documentElement) {
      o = Math.min(o, Number(getComputedStyle(node).opacity) || 1);
      node = node.parentElement;
    }
    return o;
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05;
  };
  const lum = (rgb) => {
    const [r, g, b] = rgb.map((v) => { const c = v / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const parse = (c) => { const m = c.match(/\d+(\.\d+)?/g); return m ? m.slice(0, 3).map(Number) : null; };
  const alphaOf = (c) => { const m = c.match(/[\d.]+/g); return m && m.length >= 4 ? Number(m[3]) : 1; };
  const mix = (fg, a, bg) => fg.map((v, i) => a * v + (1 - a) * bg[i]);
  // 背景逐层按 alpha 合成：页面大量 rgba(...,.15) 淡底，当实色会把徽章判成 ratio=1（假红）
  const bgOf = (el) => {
    const stack = []; let node = el;
    while (node && node !== document.documentElement) {
      const c = getComputedStyle(node).backgroundColor;
      const rgb = parse(c), a = alphaOf(c);
      if (rgb && a > 0) stack.push([rgb, a]);
      node = node.parentElement;
    }
    let base = [255, 255, 255];
    for (let i = stack.length - 1; i >= 0; i -= 1) base = mix(stack[i][0], stack[i][1], base);
    return base;
  };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };

  const out = { tap_target: [], clipped: [], offscreen: [], contrast: [], a11y: [], tiny_text: [], dup_id: [] };
  const seen = new Map();
  for (const el of document.querySelectorAll('[id]')) seen.set(el.id, (seen.get(el.id) || 0) + 1);
  out.dup_id = [...seen.entries()].filter(([, n]) => n > 1).map(([id, n]) => ({ where: `#${id}`, count: n }));

  for (const el of document.querySelectorAll('button, a, input, select, textarea, label, span, div, p, h1, h2, h3, h4, td, th, li, option')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    const tag = el.tagName.toLowerCase();
    const ownText = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
    const fontSize = parseFloat(s.fontSize) || 12;
    const disabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true'
      || el.closest('[disabled],[aria-disabled="true"]') !== null;

    if (r.right > window.innerWidth + 1) out.offscreen.push({ where: sel(el), right: Math.round(r.right) });

    const clickable = tag === 'button' || tag === 'a' || tag === 'select'
      || (tag === 'input' && ['checkbox', 'radio', 'button', 'submit'].includes(el.type));
    if (clickable && (r.height < 24 || r.width < 24)) {
      out.tap_target.push({ where: sel(el), w: Math.round(r.width), h: Math.round(r.height) });
    }
    if (ownText && el.scrollWidth > el.clientWidth + 1 && !['auto', 'scroll'].includes(s.overflowX)) {
      out.clipped.push({ where: sel(el), text: ownText.slice(0, 32) });
    }
    if (ownText && ownText.length > 1 && !disabled && dim(el) >= 0.75) {
      const fg = parse(s.color), bg = bgOf(el);
      if (fg) {
        const need = fontSize >= 18 ? 3.0 : 4.5;
        const got = ratio(fg, bg);
        if (got < need) out.contrast.push({ where: sel(el), ratio: Number(got.toFixed(2)), need,
          fontSize, color: s.color, text: ownText.slice(0, 28) });
      }
    }
    if (ownText && fontSize < 11) out.tiny_text.push({ where: sel(el), fontSize, text: ownText.slice(0, 24) });
  }

  for (const el of document.querySelectorAll('input, select, textarea')) {
    if (!visible(el)) continue;
    if (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title')) continue;
    if ((el.id && document.querySelector(`label[for="${el.id}"]`)) || el.closest('label')) continue;
    out.a11y.push({ where: sel(el), kind: 'field' });
  }
  for (const el of document.querySelectorAll('button')) {
    if (!visible(el)) continue;
    if ((el.innerText || '').trim() || el.getAttribute('aria-label') || el.getAttribute('title')) continue;
    out.a11y.push({ where: sel(el), kind: 'button' });
  }
  return out;
})()
"""

CHECKS = ("contrast", "tiny_text", "tap_target", "a11y", "clipped", "offscreen", "dup_id")


@pytest.mark.parametrize("name,prepare", CASES, ids=[f"{n}{'@' + p if p else ''}" for n, p in CASES])
def test_page_ui_metrics_are_clean(name: str, prepare: str | None, base_url: str, page: Page) -> None:
    page.goto(f"{base_url}/web/{name}", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2500)
    if prepare == _OPEN_ADVANCED_EDITOR:
        # 等编辑器 init 跑完再开浮层（固定 sleep 在慢机器上会点到还没绑事件的按钮）
        page.wait_for_function(
            "() => { const el = document.getElementById('scSummary');"
            " return el && el.textContent && !el.textContent.includes('尚未生成场景'); }", timeout=60_000)
        page.click("#advEditorToggle")
        page.wait_for_timeout(500)
    report = page.evaluate(PROBE)
    problems = {key: report.get(key) or [] for key in CHECKS if report.get(key)}
    assert not problems, f"{name} 的 UI 指标未达标：\n{json.dumps(problems, ensure_ascii=False, indent=1)[:2500]}"
