"""Web 页面结构级 UI 巡检（第三批）—— 仿真三页的 UI/外观/交互细节维度。

与既有 e2e 的分工（不重复）：
    test_sim2sim.py          基础页：加载/确定性回放/物理存活（行为层）
    test_all_models.py       基础页：14 机型 sweep（策略下发链路，默认档只跑 smoke）
    test_policy_hot_switch.py 基础页：策略热切换
    test_navigation_route.py 基础页：导航 7 路线
    → 本文件补 **UI/外观/交互细节**：
      · 基础仿真页：侧栏控件（地形 optgroup G5 归组 / 扰动徽标）、播放暂停按钮态、
        状态栏三色（ready/pending/error）、装配编辑六格输入、快捷键（C/R/Space）、
        canvas 视口尺寸自适应（1280×720 / 1920×1080 / 窗口拉伸）
      · 高级仿真页（直连 URL 与 embedded iframe 两路）：加载健康、传感器坞九来源
        逐个切换（无 console error、无空白面板）、插件勾选联动
      · 外观：布局错位/水平溢出、中文文案、canvas 与 DOM 控件叠层
        （悬浮窗不与品牌/工具栏重叠、不随面板滚动）

会话类断言复用既有 fastForward 模式（?debug=1），不重复 14 机型全量。
截图证据落 workspace/e2e-screenshots/audit/（gitignore 内）。

运行：
    uv run --no-sync python -m pytest tests/e2e/test_ui_audit_3.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "audit"

# 资源加载类 console error（"Failed to load resource: ..."）由 response/requestfailed
# 监听按 URL+状态码归类为 resource_errors（诚实记录但不拦）——页面自身 JS 错误才算失败。
_RESOURCE_CONSOLE_NOISE = re.compile(r"Failed to load resource", re.I)
_BENIGN_RESOURCE = re.compile(r"/favicon\.ico$", re.I)

READY_TIMEOUT_MS = 180_000
ADVANCED_URL = (
    "/web/sim2sim/index.html?debug=1&surface=advanced"
    "&robot=unitree_go2&policy=go2-rlsar-robotlab"
)
BASIC_URL = "/web/sim2sim/index.html?debug=1&robot=unitree_go2&policy=go2-moe-cts"

pytestmark = [pytest.mark.e2e]


def _dock_source_ids() -> set[str]:
    """从 `web/sim2sim/sensor_dock.js::DOCK_SOURCES` **现取**视图来源 id（跨语言真值）。

    为什么不在测试里抄一份：这份清单已经涨过两次（`contact` 足底接触、`lidar_height_scan`
    LiDAR 聚合高度），而**抄在测试里的那份不会自己更新** —— 上一次就是这么红的
    （e2e 长期不在 CI 里 ⇒ 没人看见）。读 JS 是文本级的，但比第二份清单可靠。
    """

    source = (ROOT / "web" / "sim2sim" / "sensor_dock.js").read_text(encoding="utf-8")
    start = source.index("export const DOCK_SOURCES = [")
    block = source[start:source.index("\n];", start)]
    ids = set(re.findall(r'\{\s*id:\s*"([^"]+)"', block))
    assert len(ids) >= 9, f"从 DOCK_SOURCES 只抽到 {len(ids)} 个来源，抽取逻辑可能失效"
    return ids


# ---------------------------------------------------------------------------
# 公共工具
# ---------------------------------------------------------------------------

def _watch(page: Page) -> dict[str, list[str]]:
    """三类错误收集器：page_errors / console_errors / resource_errors。"""
    watched: dict[str, list[str]] = {"page_errors": [], "console_errors": [], "resource_errors": []}
    page.on("pageerror", lambda exc: watched["page_errors"].append(str(exc)[:400]))

    def _on_console(msg) -> None:
        if msg.type != "error":
            return
        text = str(msg.text or "")
        if _RESOURCE_CONSOLE_NOISE.search(text):
            return  # 资源级错误由 response/requestfailed 按 URL 归类
        watched["console_errors"].append(text[:400])

    page.on("console", _on_console)
    page.on(
        "response",
        lambda response: watched["resource_errors"].append(f"{response.status} {response.url}")
        if response.status >= 400 and not _BENIGN_RESOURCE.search(response.url) else None,
    )
    page.on(
        "requestfailed",
        lambda req: watched["resource_errors"].append(f"FAILED {req.url} {req.failure}")
        if not _BENIGN_RESOURCE.search(req.url) else None,
    )
    return watched


def _open_sim(page: Page, base_url: str, query: str) -> None:
    """打开仿真页并等会话就绪（#loading 遮罩加 is-hidden；attached 口径见 test_sim2sim.py）。"""
    page.goto(f"{base_url}{query}", wait_until="domcontentloaded")
    page.wait_for_selector("#loading.is-hidden", state="attached", timeout=READY_TIMEOUT_MS)
    page.wait_for_function("() => window.__probe && Number.isFinite(window.__probe.z)", timeout=30_000)


def _shot(page: Page, name: str) -> Path | None:
    """截图**尽力而为**：它是证据，不是判据。

    2026-09-23 实测：整目录连跑时 `Page.captureScreenshot` 会抛
    `Protocol error: Unable to capture screenshot`（页面还在跑 WASM/WebGL 仿真、内存吃紧），
    于是**断言全过的用例因为一张截图被判红** —— 这类"证据链反过来咬判据"的形态本仓吃过不止一次
    （同 `_watch` 把资源加载失败单列的口径）。所以：截不到就如实打印一句，不让它影响判定。
    """

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / name
    try:
        page.screenshot(path=str(path), timeout=10_000)
    except Exception as exc:  # noqa: BLE001 - 任何截图失败都不该判红用例
        print(f"[shot] 截图失败（不影响判定）：{name} -> {exc}")
        return None
    return path


def _overflow_px(page: Page) -> int:
    return page.evaluate(
        "() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)"
        " - Math.max(window.innerWidth, 1)"
    )


def _rect(page: Page, selector: str) -> dict:
    return page.eval_on_selector(selector, "el => el.getBoundingClientRect().toJSON()")


@pytest.fixture(scope="module")
def audit_browser(browser):
    """模块级复用浏览器实例，页面级开短命 context（隔离监听器与视口）。"""
    return browser


# ---------------------------------------------------------------------------
# 1) 基础仿真页 —— 侧栏控件 / 状态色 / 播放暂停 / 快捷键 / 视口自适应
# ---------------------------------------------------------------------------

def test_basic_sidebar_controls_and_terrain_groups(audit_browser, base_url):
    """侧栏控件在位 + 地形下拉 G5 optgroup 归组渲染 + 扰动徽标样式（基础页）。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        _open_sim(page, base_url, BASIC_URL)

        # 三个一级下拉都渲染出非空选项
        for sel in ("#robotSelect", "#modelSelect", "#policySelect", "#terrainSelect"):
            count = page.eval_on_selector(sel, "el => el.options.length")
            assert count >= 1, f"{sel} 无选项"
        assert page.input_value("#policySelect") == "go2-moe-cts", "URL 声明的策略未被选中"

        # G5 地形归组：<optgroup> 至少 2 组、每组有中文标签、地图总数不丢（fail-closed 兜底）
        terrain = page.evaluate(
            """() => Array.from(document.querySelectorAll('#terrainSelect optgroup')).map(g => ({
                label: g.label, count: g.querySelectorAll('option').length,
            }))"""
        )
        assert len(terrain) >= 2, f"地形下拉没有 optgroup 归组：{terrain}"
        assert all(g["label"].strip() for g in terrain), f"optgroup 缺中文标签：{terrain}"
        total = page.eval_on_selector("#terrainSelect", "el => el.querySelectorAll('option').length")
        assert total >= 7, f"地形选项数异常（应含内置场景 + 公共地图库）：{total}"
        # 组标签应是仓库声明的中文组名（基础平地/楼梯台阶/坡道斜面/高台障碍/崎岖起伏/综合场景/比赛地图）
        # **2026-09-23 补**：`比赛地图`（`terrain_groups.js::TERRAIN_CATEGORIES.competition` +
        # `assets/maps/_index.json` 的 competition 类）是后来加的合法分组，本期望集合漏了它 ⇒
        # 这条 e2e 一直红（而 e2e 不在 CI 里，没人看见）。真值以 `terrain_groups.js` / `_index.json` 为准，
        # 两者漂移由 `npm run test:maps` 守着；这里只核"页面渲染出来的组名是不是这套中文名"。
        known = {"基础平地", "楼梯台阶", "坡道斜面", "高台障碍", "崎岖起伏", "综合场景", "比赛地图", "其他"}
        unknown = [g["label"] for g in terrain if g["label"] not in known]
        assert not unknown, f"出现未知组标签 {unknown}（terrain_groups.js 与 _index.json 漂移？）"

        # 扰动徽标：附加负载 + 接触摩擦两处，带「扰动」字样且可见
        badges = page.eval_on_selector_all(
            ".disturbance-badge",
            "els => els.map(e => ({text: e.textContent.trim(), visible: !!(e.offsetWidth || e.offsetHeight)}))",
        )
        assert len(badges) >= 2 and all(b["text"] == "扰动" and b["visible"] for b in badges), (
            f"扰动徽标缺失或不可见：{badges}"
        )

        # 装配编辑六格输入框：高级 dock 属于 advanced surface，基础页应整体隐藏（分层规则）
        dock_hidden = page.eval_on_selector("#sensorDock", "el => el.hidden")
        assert dock_hidden, "基础仿真页不应显示传感器悬浮窗（dockVisible 分层规则）"

        # 中文文案抽查：状态栏/按钮/页脚都是面向用户的中文
        assert "已就绪" in page.inner_text("#engineStatus"), (
            f"引擎状态非中文就绪文案：{page.inner_text('#engineStatus')}"
        )
        assert page.inner_text("#playButton").strip() in ("暂停", "继续")

        assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"console error：{watched['console_errors']}"
    finally:
        context.close()


def test_basic_status_dot_colors_and_play_pause(audit_browser, base_url):
    """状态栏三态色（ready/pending/error 的 dot 样式类）+ 播放/暂停按钮态与 Space 快捷键。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        _open_sim(page, base_url, BASIC_URL)

        # 就绪后引擎状态点应为 ready（绿）；CSS 里 .dot-label.ready/.error 各有独立配色
        engine_class = page.eval_on_selector("#engineStatus", "el => el.className")
        assert "ready" in engine_class, f"就绪后引擎状态点未置 ready：{engine_class}"
        ready_color = page.eval_on_selector("#engineStatus i", "el => getComputedStyle(el).backgroundColor")
        assert ready_color != "rgba(0, 0, 0, 0)", "状态点无背景色（三态配色丢了？）"

        # error 态配色类真实存在且可切换（直接验证 setStatus 的两个类名有 CSS 规则）
        css = page.evaluate(
            "() => Array.from(document.styleSheets).flatMap(s => {try {return Array.from(s.cssRules)} catch {return []}})"
            ".map(r => r.selectorText || '').join('\\n')"
        )
        assert ".dot-label.ready" in css and ".dot-label.error" in css, "dot-label 三态配色规则缺失"

        # 播放/暂停：点按钮 → 文案换态 → Space 换回来（Space 在轮腿跳跃策略下是跳跃，速度策略下是暂停）
        before = page.inner_text("#playButton").strip()
        page.click("#playButton")
        page.wait_for_timeout(150)
        after = page.inner_text("#playButton").strip()
        assert {before, after} == {"暂停", "继续"}, f"播放/暂停按钮态未切换：{before} → {after}"

        page.keyboard.press("Space")
        page.wait_for_timeout(150)
        after_space = page.inner_text("#playButton").strip()
        assert after_space != after, f"Space 未触发暂停/继续：{after} → {after_space}"

        # R 快捷键重置：仿真时钟应归零重来
        page.wait_for_function("() => window.__probe && window.__probe.playing", timeout=15_000)
        page.keyboard.press("KeyR")
        page.wait_for_timeout(400)
        clock = page.inner_text("#simClock")
        match = re.search(r"(-?\d+(?:\.\d+)?)", clock)
        assert match and float(match.group(1)) < 1.5, f"R 重置后仿真时钟未归零：{clock}"

        assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"console error：{watched['console_errors']}"
    finally:
        context.close()


def test_basic_canvas_viewport_adaptation(audit_browser, base_url):
    """canvas 尺寸自适应：1280×720 / 1920×1080 / 运行中拉伸窗口，画布始终铺满视口。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        _open_sim(page, base_url, BASIC_URL)

        for width, height in ((1280, 720), (1920, 1080)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(400)  # ResizeObserver + resize 回调下一帧生效
            rect = _rect(page, "#viewer")
            assert abs(rect["width"] - width) <= 2 and abs(rect["height"] - height) <= 2, (
                f"{width}×{height}：视口未铺满（{rect['width']}×{rect['height']}）"
                "—— #viewer 定位被覆盖成 relative 时会塌到内容高度（实测过 640/720）"
            )
            # 主渲染画布（高级页 dock 移入后 viewer 里有第二块小 canvas，须按样式挑主画布）
            canvas = page.evaluate(
                """() => {
                  const main = document.querySelector('#viewer canvas[style*="100%"]')
                    || Array.from(document.querySelectorAll('#viewer canvas')).at(-1);
                  return main.getBoundingClientRect().toJSON();
                }"""
            )
            assert abs(canvas["width"] - width) <= 2 and abs(canvas["height"] - height) <= 2, (
                f"{width}×{height}：canvas 未跟随视口（{canvas['width']}×{canvas['height']}）"
            )

        # 窗口拉伸到非标准尺寸也不破版
        page.set_viewport_size({"width": 1024, "height": 640})
        page.wait_for_timeout(400)
        assert _overflow_px(page) <= 2, f"1024×640 水平溢出 {_overflow_px(page)}px"

        _shot(page, "sim2sim-basic-1024x640.png")
        assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 2) 高级仿真页 —— 加载健康 + 传感器坞九来源逐个切换 + 插件勾选联动
# ---------------------------------------------------------------------------

def test_advanced_page_top_bar_and_iframe(audit_browser, base_url):
    """高级仿真容器页（advanced_sim.html）：顶栏在位、iframe 指向高级 surface、无 JS 错误。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        page.goto(f"{base_url}/web/advanced_sim.html", wait_until="domcontentloaded")
        assert page.inner_text(".adv-bar strong").strip() == "高级仿真"
        frame_url = page.eval_on_selector("#advSimFrame", "el => el.src")
        assert "surface=advanced" in frame_url and "embedded=1" in frame_url, (
            f"iframe 未指向高级仿真会话：{frame_url}"
        )
        # 容器页自身零错误（iframe 内的错误算在 iframe 文档上，不进这里）
        assert watched["page_errors"] == [], f"容器页 JS 异常：{watched['page_errors']}"
        _shot(page, "advanced-sim-top.png")
    finally:
        context.close()


def test_advanced_dock_all_nine_sources(audit_browser, base_url):
    """传感器坞九个来源逐个切一遍：无 console error、面板/读数非空（无数据时也有明确 note）。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        _open_sim(page, base_url, ADVANCED_URL)

        # dock 在视口内、属于 viewer（不与品牌/工具栏重叠的布局前提）
        assert page.eval_on_selector("#sensorDock", "el => !el.hidden && !!el.parentElement.closest('#viewer')"), (
            "传感器悬浮窗不可见或未挂在 viewer 下"
        )

        sources = page.evaluate(
            """() => Array.from(document.querySelectorAll('#dockSource option')).map(o => o.value)"""
        )
        # **默认插件 = 只有本体自知**（`sensors/sensor_catalog.js` 的 onboard 口径 + 2026-09-21 用户裁决：
        # odom 是外部估计管线的输出、属**外挂、默认关**）⇒ 默认来源里应有 imu 与 trail（trail 不依赖插件），
        # 而 odom 必须**先勾上插件**才可选。**2026-09-23 改**：期望原先写的是"默认就有 odom" ——
        # 与上面那条设计口径相矛盾（同样因为 e2e 不在 CI 里而长期没人发现）；现在按设计判，
        # 并把"勾上插件 ⇒ 来源立即可选"这条链单独钉一句（下面勾满九个来源那段继续覆盖全覆盖）。
        assert {"imu", "trail"} <= set(sources), f"默认来源缺失：{sources}"
        assert "odom" not in sources, f"odom 是外挂、默认关，不该默认出现在来源里：{sources}"
        page.evaluate(
            """() => { const box = document.querySelector('#dockPlugins input[data-plugin="odom"]');
                       if (box && !box.checked) box.click(); }"""
        )
        page.wait_for_timeout(200)
        assert "odom" in page.evaluate(
            "() => Array.from(document.querySelectorAll('#dockSource option')).map(o => o.value)"
        ), "勾上 odom 插件后来源仍不可选（插件→来源这条链断了）"

        page.evaluate(
            """() => {
              for (const box of document.querySelectorAll('#dockPlugins input[data-plugin]')) {
                if (!box.checked) box.click();
              }
            }"""
        )
        page.wait_for_timeout(200)
        sources_all = page.evaluate(
            """() => Array.from(document.querySelectorAll('#dockSource option')).map(o => o.value)"""
        )
        # **2026-09-23 修**：期望集合原先**在测试里抄了一份**（九个来源），后来新增的
        # `contact`（足底接触）与 `lidar_height_scan`（LiDAR 聚合高度，派生件）都没跟上 ⇒ 这条长期红
        # （e2e 不在 CI 里，没人看见）。现在**从 `sensor_dock.js::DOCK_SOURCES` 现取**真值——
        # 跨语言（Python 测试 ↔ JS 数据）只能靠"读那段代码"，但至少不会再有第二份会过期的清单。
        expected_sources = _dock_source_ids()
        assert set(sources_all) == expected_sources, (
            f"勾满插件后来源与 DOCK_SOURCES 不符（差集）：{sorted(set(sources_all) ^ expected_sources)}"
        )

        for source_id in sources_all:
            page.select_option("#dockSource", source_id)
            # 等两帧循环重画（depth/rgb 等懒初始化来源）
            page.wait_for_timeout(350)
            state = page.evaluate(
                """() => ({
                    note: document.querySelector('#dockNote')?.textContent?.trim() || '',
                    canvasHidden: document.querySelector('#dockCanvas')?.hidden,
                    canvasW: document.querySelector('#dockCanvas')?.width || 0,
                    readoutRows: document.querySelectorAll('#dockReadout div').length,
                })"""
            )
            canvas_kinds = {"depth", "height", "trail", "lidar", "cloud", "rgb"}
            if source_id in canvas_kinds:
                assert not state["canvasHidden"], f"{source_id}: 画布来源却隐藏了 canvas"
            else:
                assert state["canvasHidden"], f"{source_id}: 读数来源却显示了空 canvas"
            # 读数行口径（sensor_dock.js::readoutRows）：depth/trail 是纯画布来源、无行定义；
            # odom/imu 是纯读数来源、note 恒为「—」（无图可注），信息在行里 —— 行值不能是空 div。
            if source_id not in ("depth", "trail"):
                assert state["readoutRows"] >= 1, f"{source_id}: 读数表为空（空白面板）"
            if source_id in canvas_kinds and source_id not in ("depth", "trail"):
                # 有图也有数的来源（height/lidar/cloud/rgb）note 必须交代图的尺度
                assert state["note"] and state["note"] != "—", f"{source_id}: 画布来源 note 空白"

        _shot(page, "advanced-dock-sources.png")
        assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"console error：{watched['console_errors']}"
    finally:
        context.close()


def test_advanced_depth_camera_pipeline(audit_browser, base_url):
    """深度相机全链路（PIE 策略）：ONNX 深度输入 → 浏览器 raycast 帧 → dock 画布真渲染。

    这是 pie_depth.js `mj_name2id` 枚举对象回归的守门用例：该参数必须是 int，
    传 emscripten 枚举对象时每帧抛 `Cannot convert "[object Object]" to int`，
    深度链路整个断掉（画布空 + 仿真时钟停在 0）。修复后应看到 60×86 真帧。
    """
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        page.goto(
            f"{base_url}/web/sim2sim/index.html?debug=1&surface=advanced"
            "&robot=unitree_go2&policy=go2-pie-parkour",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector("#loading.is-hidden", state="attached", timeout=READY_TIMEOUT_MS)
        page.wait_for_function(
            "() => window.__sim2simDebug.state().policyMode === 'recurrent-depth'", timeout=30_000,
        )

        # 深度帧在 runPolicy 推理时捕获 → 让实时帧循环跑一会儿
        page.wait_for_timeout(3_000)
        state = page.evaluate("() => window.__sim2simDebug.state()")
        assert state["time"] and state["time"] > 0.1, (
            f"深度策略下仿真时钟未推进（time={state['time']}）—— 深度帧链路可能仍在每帧抛错"
        )

        # 勾上深度相机插件 → depth 来源出现 → 画布尺寸对齐深度帧 60×86
        page.evaluate("() => document.querySelector('#dockPlugins input[data-plugin=\"depth\"]').click()")
        page.wait_for_timeout(200)
        assert "depth" in page.evaluate(
            "() => Array.from(document.querySelectorAll('#dockSource option')).map(o => o.value)"
        ), "勾选深度插件后 depth 来源未出现在下拉"
        page.select_option("#dockSource", "depth")
        page.wait_for_timeout(600)

        note = page.inner_text("#dockNote").strip()
        assert "60×86" in note, f"深度画布 note 未呈现帧尺寸（应为 60×86）：{note}"
        canvas_w, canvas_h = page.evaluate(
            "() => [document.querySelector('#dockCanvas').width, document.querySelector('#dockCanvas').height]"
        )
        assert (canvas_w, canvas_h) == (86, 60), f"深度画布像素尺寸应 86×60：{canvas_w}×{canvas_h}"

        _shot(page, "advanced-dock-depth.png")
        assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
    finally:
        context.close()


def test_advanced_dock_plugin_toggle_linkage(audit_browser, base_url):
    """插件勾选联动：关掉 LiDAR → lidar/cloud 来源从下拉消失；重勾 → 恢复（fail-closed 回落）。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        _open_sim(page, base_url, ADVANCED_URL)
        page.evaluate(
            """() => { for (const box of document.querySelectorAll('#dockPlugins input[data-plugin]')) {
                if (!box.checked) box.click(); } }"""
        )
        page.wait_for_timeout(150)

        # 切到 lidar 来源后取消 lidar 插件 → 来源被关掉，回落到第一个可选来源
        page.select_option("#dockSource", "lidar")
        page.evaluate(
            """() => document.querySelector('#dockPlugins input[data-plugin="lidar"]').click()"""
        )
        page.wait_for_timeout(150)
        values = page.evaluate(
            """() => ({
                options: Array.from(document.querySelectorAll('#dockSource option')).map(o => o.value),
                current: document.querySelector('#dockSource').value,
            })"""
        )
        assert "lidar" not in values["options"] and "cloud" not in values["options"], (
            f"取消 LiDAR 插件后来源清单未联动：{values['options']}"
        )
        assert values["current"] in values["options"], "当前来源被关掉后未回落到可选来源"

        # 重勾 → lidar/cloud 回到下拉（选择本身回落设计如此，不要求自动恢复）
        page.evaluate(
            """() => document.querySelector('#dockPlugins input[data-plugin="lidar"]').click()"""
        )
        page.wait_for_timeout(150)
        options_after = page.evaluate(
            """() => Array.from(document.querySelectorAll('#dockSource option')).map(o => o.value)"""
        )
        assert {"lidar", "cloud"} <= set(options_after), f"重勾 LiDAR 后来源未恢复：{options_after}"

        assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
    finally:
        context.close()


def test_advanced_dock_mount_editor_six_fields(audit_browser, base_url):
    """装配编辑六格输入框：改一格 → 覆盖生效 + 组高亮；改回默认 → 覆盖删除（高亮消失）。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        _open_sim(page, base_url, ADVANCED_URL)
        page.evaluate(
            """() => { for (const box of document.querySelectorAll('#dockPlugins input[data-plugin]')) {
                if (!box.checked) box.click(); } }"""
        )
        page.wait_for_timeout(150)
        page.evaluate("() => document.querySelector('.dock-mounts')?.setAttribute('open', '')")

        boxes = page.evaluate(
            """() => Array.from(document.querySelectorAll('#dockMounts input[data-mount]'))
                .filter(i => i.dataset.mount === 'depth')
                .map(i => ({key: i.dataset.key, index: i.dataset.index}))"""
        )
        assert len(boxes) == 6, f"装配编辑器应为六格（pos xyz + rpy xyz），实际 {len(boxes)}"

        # 改位置 x：+0.05 → 组进入 overridden 高亮
        page.fill('#dockMounts input[data-mount="depth"][data-key="pos"][data-index="0"]', "0.33")
        page.dispatch_event('#dockMounts input[data-mount="depth"][data-key="pos"][data-index="0"]', "change")
        page.wait_for_timeout(150)
        overridden = page.eval_on_selector(
            '#dockMounts .dock-mount-group:nth-of-type(1), .dock-mount-group',
            """el => {
              const group = Array.from(document.querySelectorAll('.dock-mount-group'))
                .find(g => g.querySelector('input[data-mount="depth"]'));
              return group ? group.classList.contains('overridden') : null;
            }""",
        )
        assert overridden, "改装配后组未标记 overridden"

        # 改回默认值 → 覆盖整条删除、高亮消失（applyMountEdit 的核心约定）
        page.fill('#dockMounts input[data-mount="depth"][data-key="pos"][data-index="0"]', "0.28")
        page.dispatch_event('#dockMounts input[data-mount="depth"][data-key="pos"][data-index="0"]', "change")
        page.wait_for_timeout(150)
        overridden_after = page.evaluate(
            """() => {
              const group = Array.from(document.querySelectorAll('.dock-mount-group'))
                .find(g => g.querySelector('input[data-mount="depth"]'));
              return group ? group.classList.contains('overridden') : null;
            }"""
        )
        assert overridden_after is False, "改回默认值后覆盖未删除（overridden 高亮仍在）"

        assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
    finally:
        context.close()


def test_advanced_dock_layout_layering(audit_browser, base_url):
    """外观叠层：悬浮窗钉在视口左上角、不与品牌/工具栏重叠、不随控制面板滚动。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        _open_sim(page, base_url, ADVANCED_URL)

        dock = _rect(page, "#sensorDock")
        assert dock["x"] <= 16 and dock["y"] <= 16, f"悬浮窗不在视口左上角：({dock['x']}, {dock['y']})"

        # 工具栏（hud-top）与悬浮窗不得相交
        toolbar = _rect(page, ".toolbar")
        overlap_x = min(dock["right"], toolbar["right"]) - max(dock["left"], toolbar["left"])
        overlap_y = min(dock["bottom"], toolbar["bottom"]) - max(dock["top"], toolbar["top"])
        assert overlap_x <= 0 or overlap_y <= 0, (
            f"悬浮窗与工具栏重叠（交叠 {overlap_x:.0f}×{overlap_y:.0f}px）"
        )

        # 控制面板滚动不影响悬浮窗位置（修复前 dock 是面板子元素，会被滚出视口）
        page.evaluate("() => { document.querySelector('.panel-left').scrollTop = 400; }")
        page.wait_for_timeout(200)
        dock_after = _rect(page, "#sensorDock")
        assert abs(dock_after["y"] - dock["y"]) <= 2, (
            f"悬浮窗随面板滚动位移（{dock['y']} → {dock_after['y']}）：定位基准不在 viewer"
        )

        assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
    finally:
        context.close()
