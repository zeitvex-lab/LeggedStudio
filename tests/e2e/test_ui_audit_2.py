"""Web 页面结构级 UI 巡检（第二批）—— 训练监控 / 评测 / 产物库 / 部署 / 地图编辑器。

覆盖页面（与 /web 静态挂载一一对应，均由真实 uvicorn 控制面伺服）：
    training_monitor.html   训练监控详情（空态 + 真实 task_id 全分区渲染）
    evaluation.html         策略验证 / 质量矩阵（选择器联动 + 历史报告）
    artifacts.html          策略产物库（列表加载）
    deploy.html             部署向导（表单 / 校验按钮，不真生成部署包）
    navigation_editor.html  地图编辑器（只读巡检：地图加载 / 航点显示，不点保存/清空）

口径（与 test_ui_audit.py / test_all_models.py 一致，按仓库"诚实降级"约定）：
    - 页面自身 JS 错误（pageerror / 非 "Failed to load resource" 的 console error）
      算失败；
    - 资源加载类 console error 单独归入 resource_errors，如实记录但不拦；
    - 数据驱动的区块只断言容器渲染到终态（有数据或显式空态/降级文案均可）；
    - 地图编辑器为只读巡检：不点「保存地图」「清空」，不做任何 PUT /maps 写操作，
      不弄脏 workspace 数据。

训练监控页的真实 task_id 从 /api/training/list 动态取第一项（workspace 里有历史
Run 即有数据；一个都没有时退化为只验空态参数页）。

截图证据落 workspace/e2e-screenshots/audit/<page>-<viewport>.png（gitignore 内）。

运行：
    uv run --no-sync python -m pytest tests/e2e/test_ui_audit_2.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "audit"

# 资源加载类 console error（"Failed to load resource: ..."）由 response 监听按
# URL+状态码归类为 resource_errors（诚实记录但不拦）——页面自身 JS 错误才算失败。
_RESOURCE_CONSOLE_NOISE = re.compile(r"Failed to load resource", re.I)
# favicon 与被测页面自身无关（后端亦有 204 兜底），豁免避免每页一行噪音。
_BENIGN_RESOURCE = re.compile(r"/favicon\.ico$", re.I)

# 骨架 / 加载中占位（出现即视为"还在读数据"，终态断言要求其消失）
_LOADING_HINTS = ("加载中", "正在加载", "正在读取", "检测中", "等待", "Loading", "加载机器人列表")

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# 公共夹具与工具
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


def _container_settled(page: Page, selector: str) -> bool:
    """容器是否已到终态：非空文本且不含"加载中"类占位（空态/降级文案都算终态）。"""
    handle = page.query_selector(selector)
    if handle is None:
        return False
    text = (handle.inner_text() or "").strip()
    if not text:
        return False
    return not any(hint in text for hint in _LOADING_HINTS)


def _wait_settled(page: Page, selector: str, timeout_ms: int = 20_000) -> bool:
    page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
    waited = 0
    while waited < timeout_ms and not _container_settled(page, selector):
        page.wait_for_timeout(250)
        waited += 250
    return _container_settled(page, selector)


def _shot(page: Page, name: str, suffix: str) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / f"{name}-{suffix}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


@pytest.fixture(scope="module")
def audit_browser(browser):
    """模块级复用浏览器实例，页面级开短命 context（隔离监听器与缓存）。"""
    return browser


@pytest.fixture(scope="module")
def first_task_id(audit_browser, base_url) -> str:
    """从 /api/training/list 动态取一个真实 task_id（列表页第一项口径）。

    没有任何历史任务时返回空串——依赖它的监控详情用例按 skip 跳过（无数据可看
    是环境事实，不是页面缺陷），空态用例仍然照跑。
    """
    context = audit_browser.new_context()
    page = context.new_page()
    try:
        response = page.request.get(f"{base_url}/api/training/list")
        data = response.json()
        tasks = data.get("tasks") or []
        return str(tasks[0]["task_id"]) if tasks else ""
    finally:
        context.close()


def _overflow_px(page: Page) -> int:
    return page.evaluate(
        "() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)"
        " - Math.max(window.innerWidth, 1)"
    )


# ---------------------------------------------------------------------------
# 1) 训练监控页 training_monitor.html
# ---------------------------------------------------------------------------

def test_monitor_empty_state_no_task_id(audit_browser, base_url):
    """无 ?task_id 参数：主界面隐藏，缺参提示与「返回任务列表」入口在位。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        page.goto(f"{base_url}/web/training_monitor.html", wait_until="domcontentloaded")
        page.wait_for_selector("#missingIdBox", state="visible", timeout=10_000)
        assert page.eval_on_selector("#monitorBody", "el => getComputedStyle(el).display") == "none", (
            "缺参时主界面未隐藏"
        )
        text = page.inner_text("#missingIdText")
        assert "缺少任务 ID" in text, f"缺参提示文案异常：{text!r}"
        assert page.query_selector("#missingIdBox a.button") is not None, "缺参页缺少返回任务列表入口"
        assert watched["page_errors"] == [], f"空态页 JS 错误：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"空态页 console error：{watched['console_errors']}"
        _shot(page, "training_monitor-empty", "1280x720")
    finally:
        context.close()


def test_monitor_full_page_with_real_task(audit_browser, base_url, first_task_id):
    """真实 task_id：四件套 Run 档案 / 健康仪表盘 / 告警条 / 三段侧栏全部渲染到终态。"""
    if not first_task_id:
        pytest.skip("workspace 里没有任何训练任务（/api/training/list 为空），无真实数据可看")
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        page.goto(f"{base_url}/web/training_monitor.html?task_id={first_task_id}", wait_until="domcontentloaded")

        # 运行头部：task_id 出标题、状态徽标不再是加载中
        page.wait_for_selector("#runIdTitle", state="attached", timeout=10_000)
        page.wait_for_function(
            "() => document.querySelector('#runIdTitle')?.textContent"
            " && document.querySelector('#runIdTitle').textContent !== '加载中...'",
            timeout=20_000,
        )
        assert page.inner_text("#runIdTitle").strip() == first_task_id, "标题未显示真实 task_id"
        assert page.inner_text("#statusPill").strip() not in ("", "..."), "状态徽标停留在占位"

        # 进度条 + 七格实时数字
        assert _wait_settled(page, ".progress-strip", timeout_ms=15_000), "进度条未渲染到终态"
        for metric_id in ("metricIteration", "metricMaxIter", "metricReward",
                          "metricSuccess", "metricSpeed", "metricElapsed", "metricEta"):
            assert page.query_selector(f"#{metric_id}") is not None, f"实时数字 {metric_id} 缺失"

        # 三段概览侧栏：环境 / 配置 / 摘要
        for sel in ("#envList", "#configList", "#summaryList"):
            assert _wait_settled(page, sel, timeout_ms=15_000), f"侧栏 {sel} 停留在加载中"

        # 健康仪表盘：仪表盘卡片渲染（pass/warn/fail 皆是终态，alert 条仅 alerts 非空才出现）
        assert _wait_settled(page, "#healthGauges", timeout_ms=15_000), "健康仪表盘停留在加载中"
        gauge_count = page.eval_on_selector_all(
            "#healthGauges .gauge-card", "els => els.length")
        assert gauge_count >= 1, "健康仪表盘没有渲染出任何仪表卡片"

        # Run 档案四件套（B9）：该任务建链后应 available；对账结论是 pass/fail 皆可
        assert _wait_settled(page, "#runArchiveList", timeout_ms=15_000), "Run 档案停留在加载中"
        archive_text = page.inner_text("#runArchiveList")
        assert ("run_id" in archive_text) or ("该任务" in archive_text), (
            f"Run 档案既无四件套也无显式说明：{archive_text[:120]!r}"
        )

        # 检查点与产物列表到终态
        assert _wait_settled(page, "#ckptList", timeout_ms=15_000), "检查点列表停留在加载中"

        # 训练日志到终态（空日志也是显式终态文案）
        assert _wait_settled(page, "#logContainer", timeout_ms=15_000), "训练日志停留在加载中"

        # 关键元素在位
        for sel in ("#healthAlerts", "#termsGrid", "#metricsGrid", "#stopBtn", "#refreshBtn",
                    "#copyIdBtn", "#promoteBtn", "#artifactPill", "#rawConfigDetails"):
            assert page.query_selector(sel) is not None, f"关键元素 {sel} 缺失"

        assert watched["page_errors"] == [], f"监控页 JS 错误：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"监控页 console error：{watched['console_errors']}"
        if watched["resource_errors"]:
            print(f"\n[training_monitor] resource_errors（不拦，如实记录）: {watched['resource_errors']}")
        _shot(page, f"training_monitor-{first_task_id[:40]}", "1280x720")

        # 交互：刷新按钮可用且不抛错（只读动作）
        page.click("#refreshBtn")
        page.wait_for_timeout(600)
        assert watched["page_errors"] == [], "点击刷新后出现 JS 错误"
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 2) 评测 / 质量矩阵页 evaluation.html
# ---------------------------------------------------------------------------

def test_evaluation_selectors_and_history(audit_browser, base_url):
    """机器人/策略选择器联动 + 四档切换 + 历史报告表（不点「跑评测」——那会真跑 MuJoCo）。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        page.goto(f"{base_url}/web/evaluation.html", wait_until="domcontentloaded")

        # 机器人下拉联动加载（此前 loadQualityRobots 未定义 → 页面加载即抛 JS 错，本用例守住该回归）
        page.wait_for_function(
            "() => { const el = document.querySelector('#q-robot');"
            " return el && el.options.length > 0 && !/加载中/.test(el.options[0].textContent); }",
            timeout=20_000,
        )
        robots = page.eval_on_selector_all(
            "#q-robot option", "els => els.map(e => e.value).filter(Boolean)")
        assert robots, "质量矩阵机器人下拉为空"

        # 联动：选机器人 → 策略下拉随之刷新出该包声明的策略 id
        page.select_option("#q-robot", robots[0])
        page.wait_for_function(
            "() => { const el = document.querySelector('#q-policy');"
            " return el && el.options.length > 0 && !/加载中/.test(el.options[0].textContent); }",
            timeout=20_000,
        )
        policies = page.eval_on_selector_all(
            "#q-policy option", "els => els.map(e => e.value).filter(Boolean)")
        assert policies, f"选机器人 {robots[0]} 后策略下拉仍为空（联动断）"

        # 四档切换：single / multi / level / stress 四个选项在位且可切换
        tiers = page.eval_on_selector_all("#q-tier option", "els => els.map(e => e.value)")
        assert tiers == ["single", "multi", "level", "stress"], f"档位选项异常：{tiers}"
        for tier in tiers[1:]:
            page.select_option("#q-tier", tier)
        page.select_option("#q-tier", "single")

        # 历史报告容器到终态（无报告也有显式空态文案）
        assert _wait_settled(page, "#q-list", timeout_ms=20_000), "历史报告区停留在加载中"

        # 顶部 Sim2Sim 验证表单 + 结果区在位
        for sel in ("#task", "#episodes", "#run", "#result", "#q-run", "#q-min", "#q-steps", "#q-magnitudes"):
            assert page.query_selector(sel) is not None, f"关键元素 {sel} 缺失"

        assert watched["page_errors"] == [], f"评测页 JS 错误：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"评测页 console error：{watched['console_errors']}"
        if watched["resource_errors"]:
            print(f"\n[evaluation] resource_errors（不拦，如实记录）: {watched['resource_errors']}")
        _shot(page, "evaluation", "1280x720")
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 3) 策略产物库 artifacts.html
# ---------------------------------------------------------------------------

def test_artifacts_list_loads(audit_browser, base_url):
    """列表加载到终态（有任务渲染行 / 无任务渲染显式空态），刷新按钮在位。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        page.goto(f"{base_url}/web/artifacts.html", wait_until="domcontentloaded")
        assert _wait_settled(page, "#list", timeout_ms=20_000), "产物列表停留在加载中"
        text = page.inner_text("#list")
        assert "加载中" not in text, "产物列表未到终态"

        assert page.query_selector("#refresh") is not None, "刷新按钮缺失"
        page.click("#refresh")
        page.wait_for_timeout(800)
        assert watched["page_errors"] == [], f"刷新后 JS 错误：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"产物页 console error：{watched['console_errors']}"
        if watched["resource_errors"]:
            print(f"\n[artifacts] resource_errors（不拦，如实记录）: {watched['resource_errors']}")
        _shot(page, "artifacts", "1280x720")
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 4) 部署向导 deploy.html
# ---------------------------------------------------------------------------

def test_deploy_wizard_form_and_gate(audit_browser, base_url):
    """表单渲染 + 步骤 2 gate 校验按钮可点不抛错（校验结果 pass/block 皆为合法终态）。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        page.goto(f"{base_url}/web/deploy.html", wait_until="domcontentloaded")

        # 步骤 1：机器人下拉加载出真实包 + 目标平台三选
        page.wait_for_function(
            "() => { const el = document.querySelector('#robotSelect');"
            " return el && el.options.length > 0 && !/加载/.test(el.options[0].textContent); }",
            timeout=20_000,
        )
        robots = page.eval_on_selector_all(
            "#robotSelect option", "els => els.map(e => e.value).filter(Boolean)")
        assert robots, "部署向导机器人下拉为空"
        platforms = page.eval_on_selector_all(
            "#platformSelect option", "els => els.map(e => e.value)")
        assert "unitree_sdk2" in platforms and "ros2" in platforms, f"目标平台选项异常：{platforms}"

        # 步骤 2：下一步解锁 → gate 校验按钮可点，结果落到 gate-list（不真生成部署包）
        page.select_option("#robotSelect", robots[0])
        assert page.eval_on_selector("#toGate", "el => !el.disabled"), "选机型后「下一步」仍禁用"
        page.click("#toGate")
        page.wait_for_selector("#gatePanel:not(.hidden)", timeout=5_000)
        page.click("#runGate")
        page.wait_for_function(
            "() => { const el = document.querySelector('#gateList');"
            " return el && el.children.length > 0; }",
            timeout=30_000,
        )
        gate_text = page.inner_text("#gateList")
        assert gate_text.strip(), "gate 校验结果为空"

        # 步骤 3 面板结构存在（不点「生成部署包 zip」，避免写 workspace/deploy）
        assert page.query_selector("#packPanel") is not None, "步骤 3 面板缺失"
        assert page.query_selector("#degradedToggle") is not None, "劣化参数档开关缺失"
        assert page.query_selector("#benchToggle") is not None, "台架模式开关缺失"

        assert watched["page_errors"] == [], f"部署页 JS 错误：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"部署页 console error：{watched['console_errors']}"
        if watched["resource_errors"]:
            print(f"\n[deploy] resource_errors（不拦，如实记录）: {watched['resource_errors']}")
        _shot(page, "deploy", "1280x720")
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 5) 导航地图编辑器 navigation_editor.html（只读巡检）
# ---------------------------------------------------------------------------

def test_navigation_editor_readonly(audit_browser, base_url):
    """地图加载 + 航点/障碍画布显示；只读巡检——不点保存/清空，不写 workspace。"""
    context = audit_browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        page.goto(f"{base_url}/web/navigation_editor.html", wait_until="domcontentloaded")

        # 地图下拉加载 + 默认选中第一张
        page.wait_for_function(
            "() => { const el = document.querySelector('#mapSelect');"
            " return el && el.options.length > 0; }",
            timeout=20_000,
        )
        maps = page.eval_on_selector_all("#mapSelect option", "els => els.map(e => e.value)")
        assert maps, "地图下拉为空"

        # 状态行到终态：显示 地图 · 障碍 N · 航点 N
        page.wait_for_function(
            "() => /障碍 \\d+ · 航点 \\d+/.test(document.querySelector('#status')?.textContent || '')",
            timeout=20_000,
        )
        status_text = page.inner_text("#status")
        match = re.search(r"障碍 (\d+) · 航点 (\d+)", status_text)
        assert match, f"状态行文案异常：{status_text!r}"

        # warehouse 等导航地图应带默认航点（flat 是纯平面，航点 0 合法）
        if "warehouse" in maps:
            page.select_option("#mapSelect", "warehouse")
            page.wait_for_function(
                "() => /障碍 \\d+ · 航点 \\d+/.test(document.querySelector('#status')?.textContent || '')"
                " && document.querySelector('#status').textContent.includes('航点 4')",
                timeout=15_000,
            )

        # 画布真的在画东西：非空白像素 > 0
        painted = page.evaluate(
            """() => {
              const canvas = document.querySelector('#mapCanvas');
              const ctx = canvas.getContext('2d');
              const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
              let painted = 0;
              for (let i = 3; i < data.length; i += 4) { if (data[i] > 0) painted += 1; }
              return painted;
            }"""
        )
        assert painted > 0, "画布完全空白（draw 未执行）"

        # 工具按钮组在位（航点显示依赖的绘制链路；不做编辑/保存动作）
        for sel in ("#btnObstacle", "#btnWaypoint", "#btnMove", "#btnErase",
                    "#btnPlan", "#btnSave", "#algorithm"):
            assert page.query_selector(sel) is not None, f"工具/控件 {sel} 缺失"

        assert watched["page_errors"] == [], f"地图编辑器 JS 错误：{watched['page_errors']}"
        assert watched["console_errors"] == [], f"地图编辑器 console error：{watched['console_errors']}"
        if watched["resource_errors"]:
            print(f"\n[navigation_editor] resource_errors（不拦，如实记录）: {watched['resource_errors']}")
        _shot(page, "navigation_editor", "1280x720")
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 1920×1080 破版巡检（五页一遍过）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,url",
    [
        ("training_monitor", "/web/training_monitor.html"),
        ("evaluation", "/web/evaluation.html"),
        ("artifacts", "/web/artifacts.html"),
        ("deploy", "/web/deploy.html"),
        ("navigation_editor", "/web/navigation_editor.html"),
    ],
    ids=lambda v: v,
)
def test_pages_no_break_1920(audit_browser, base_url, first_task_id, name, url):
    """1920×1080：页面自身 JS 零错误 + 文档无水平溢出（破版检测），截图留证。"""
    context = audit_browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    page = context.new_page()
    watched = _watch(page)
    try:
        target = f"{base_url}{url}"
        if name == "training_monitor" and first_task_id:
            target += f"?task_id={first_task_id}"
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)  # 等首屏数据渲染（空态/降级也算终态）
        overflow_px = _overflow_px(page)
        _shot(page, name, "1920x1080")
        assert watched["page_errors"] == [], f"{name} @1920 页面 JS 错误：{watched['page_errors']}"
        # 水平破版检测：文档滚动宽度不应超过视口宽度（容差 2px 抗亚像素）。
        assert overflow_px <= 2, f"{name} @1920 水平溢出 {overflow_px}px"
    finally:
        context.close()
