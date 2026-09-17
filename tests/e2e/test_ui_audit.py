"""Web 页面结构级 UI 巡检 —— 五个功能页的加载健康 + 关键元素在位 + console 归类。

覆盖页面（与 /web 静态挂载一一对应，均由真实 uvicorn 控制面伺服）：
    workbench.html      首页工作台（侧边栏导航 + 首页四区 + 内嵌 iframe 页）
    dashboard.html      控制台（旧版多页入口，仍从顶栏 brand 可达）
    assets.html         包管理 / 机器人工作台入口
    training_create.html训练配置页（机型/档案/三段分区/章节导航）
    training_list.html  训练列表（汇总卡 / 过滤栏 / 表格 / 空态）

口径（与 test_all_models.py 一致，按仓库"诚实降级"约定）：
    - 页面自身 JS 错误（pageerror / 非"Failed to load resource"的 console error）
      算失败；
    - 资源加载类 console error（Failed to load resource ...）单独归入
      resource_errors，如实记录但不拦（数据缺失类降级是页面的设计行为）；
    - 数据驱动的区块（demo 卡 / 资产卡 / 训练行）数量不作硬性断言，只断言
      容器已渲染出"非加载中"的终态（骨架屏消失 / 空态或内容二选一）。

截图证据落 workspace/e2e-screenshots/audit/<page>-<viewport>.png（gitignore 内）。

运行：
    uv run --no-sync python -m pytest tests/e2e/test_ui_audit.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "audit"

# 资源加载类 console error（"Failed to load resource: ..."）由 console 监听按
# 文本归类为 resource_errors（诚实记录但不拦）——页面自身 JS 错误才算失败。
_RESOURCE_CONSOLE_NOISE = re.compile(r"Failed to load resource", re.I)
# favicon 已由后端 204 兜底；即便命中 404 也与被测页面自身无关。
_BENIGN_RESOURCE = re.compile(r"/favicon\.ico$", re.I)

# 骨架 / 加载中占位（出现即视为"还在读数据"，终态断言要求其消失）
_LOADING_HINTS = ("正在读取", "加载中", "正在加载", "检查运行环境", "检查中", "Loading")

# 每页结构清单：(相对 URL, 必须在位的关键选择器, 必须渲染到终态的容器选择器)
# 终态口径：容器内不再只有"加载中/骨架"占位 —— 有数据或显式空态/降级文案均可。
PAGE_SPECS: list[dict] = [
    {
        "name": "workbench",
        "url": "/web/workbench.html",
        "required": [
            ".sidebar .side-item",            # 侧边栏导航
            "#home.active-view",              # 首页默认激活
            "#homeCapabilities",              # 系统状态容器
            "#homeNextStepBody",              # 下一步建议四态容器
            "#homeDemos",                     # demo 卡容器
            "#homeRuns",                      # 最近实验容器
            "#assetLibraryGrid",              # 资产库容器
            "#robot",                         # 机器人工作台视图（iframe 宿主）
            "#configFrame",                   # 训练配置 iframe
        ],
        "settle": [
            "#homeCapabilities",
            "#homeNextStepBody",
            "#homeDemos",
            "#homeRuns",
            "#assetLibraryGrid",
        ],
    },
    {
        "name": "dashboard",
        "url": "/web/dashboard.html",
        "required": [
            ".page-header h1",                # 页头
            "#quickList",                     # 快速体验卡
            "#systemRows",                    # 系统状态
            "#statsGrid",                     # 训练统计
            ".workflow-grid",                 # 工作流步骤
            "#trainingList",                  # 最近训练
        ],
        "settle": [
            "#systemRows",
            "#statsGrid",
            "#trainingList",
        ],
    },
    {
        "name": "assets",
        "url": "/web/assets.html",
        "required": [
            ".page-header h1",                # 页头「包管理」
            "#importPath",                    # 导入路径输入
            "#importBtn",                     # 导入按钮
            "#refresh",                       # 刷新索引
            "#packageList",                   # 包卡片容器
        ],
        "settle": ["#packageList"],
    },
    {
        "name": "training_create",
        "url": "/web/training_create.html?v=0.44.0",
        "required": [
            "#robotSelect",                   # 机型选择
            "#robotImportBtn",                # 导入新机器人入口
            "#robotMetaBox",                  # 当前机器人摘要框
            "#profileSelect",                 # 档案选择
            "#chapterNav .toc-item",          # 章节导航（5 章 + 预览）
            "#layer-physics",                 # 第一段：物理（只读）
            "#layer-task",                    # 第二段：任务（Recipe）
            "#layer-runtime",                 # 第三段：运行参数
            "#layer-expert",                  # 专家模式逃生门
            "#taskChips",                     # 任务预设 chips
            "#rewardBoard",                   # 奖励四层看板
            "#cmdGrid",                       # 速度指令范围
            "#previewList",                   # 配置预览 KV
            ".sticky-bar #submitBtn",         # 粘性提交栏 + 启动训练
        ],
        "settle": ["#robotSelect"],
    },
    {
        "name": "training_list",
        "url": "/web/training_list.html?v=0.44.0",
        "required": [
            ".summary-grid .summary-card",    # 汇总卡（5 张）
            "#filterStatus",                  # 状态筛选
            "#searchInput",                   # 搜索框
            ".table-header",                  # 表头
            "#tableBody",                     # 表体
            "#tableFooter",                   # 页脚（最后更新时间）
            "#packStrip",                     # 模块化资源包条
        ],
        "settle": ["#tableBody", "#packStrip"],
    },
]


def _container_is_loading(page: Page, selector: str) -> bool:
    """容器是否仍处于"加载中"态：文本命中加载提示，或仍是骨架屏。

    诚实口径：空态 / 降级文案（如「读取失败：...」「暂无…」）都算终态 ——
    只有"还在读"才算未终态。
    """
    handle = page.query_selector(selector)
    if handle is None:
        return True
    if handle.query_selector(".skeleton-line") is not None:
        return True
    text = (handle.inner_text() or "").strip()
    if not text:
        return True
    return any(hint in text for hint in _LOADING_HINTS)


def _wait_settled(page: Page, selectors: list[str], timeout_ms: int = 20_000) -> None:
    for selector in selectors:
        page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
        # 轮询等待"加载中"占位消失（页面用 setTimeout 轮询，无事件可挂）
        waited = 0
        while waited < timeout_ms and _container_is_loading(page, selector):
            page.wait_for_timeout(250)
            waited += 250


def _audit_page(browser, base_url: str, spec: dict, viewport: dict, suffix: str) -> dict:
    """打开页面 → 等终态 → 结构断言数据 + 截图 → 三类错误与 HTTP 4xx/5xx 清单。

    页面自身 JS 错误 / console error / 关键元素缺失由调用方断言 —— 这里只采集，
    保证失败信息里同时带得上错误清单与截图路径。
    """
    context = browser.new_context(viewport=viewport, device_scale_factor=1)
    page = context.new_page()
    page_errors: list[str] = []
    console_errors: list[str] = []
    resource_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: (
            console_errors.append(msg.text)
            if msg.type == "error" and not _RESOURCE_CONSOLE_NOISE.search(msg.text)
            else None
        ),
    )
    page.on(
        "response",
        lambda response: (
            resource_errors.append(f"{response.status} {response.url}")
            if response.status >= 400 and not _BENIGN_RESOURCE.search(response.url)
            else None
        ),
    )
    page.goto(f"{base_url}{spec['url']}", wait_until="domcontentloaded")
    _wait_settled(page, spec["settle"])

    missing = [s for s in spec["required"] if page.query_selector(s) is None]
    stuck = [s for s in spec["settle"] if _container_is_loading(page, s)]
    overflow_px = page.evaluate(
        "() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)"
        " - Math.max(window.innerWidth, 1)"
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shot = ARTIFACT_DIR / f"{spec['name']}-{suffix}.png"
    page.screenshot(path=str(shot), full_page=True)
    context.close()
    return {
        "name": spec["name"],
        "viewport": suffix,
        "screenshot": shot,
        "page_errors": page_errors,
        "console_errors": console_errors,
        "resource_errors": resource_errors,
        "missing": missing,
        "stuck": stuck,
        "overflow_px": overflow_px,
    }


@pytest.fixture(scope="module")
def audit_browser(browser):
    """模块级复用浏览器实例，页面级开短命 context（隔离监听器与缓存）。"""
    return browser


@pytest.mark.e2e
@pytest.mark.parametrize("spec", PAGE_SPECS, ids=lambda s: s["name"])
def test_page_load_health_1280(audit_browser, base_url, spec):
    """1280×720：HTTP 加载 + 页面自身 JS 零错误 + 关键结构在位 + 容器到终态。"""
    result = _audit_page(
        audit_browser, base_url, spec,
        viewport={"width": 1280, "height": 720}, suffix="1280x720",
    )
    assert result["page_errors"] == [], (
        f"{result['name']}: 页面自身 JS 错误 {result['page_errors']}（截图 {result['screenshot'].name}）"
    )
    assert result["console_errors"] == [], (
        f"{result['name']}: console error {result['console_errors']}"
    )
    assert result["missing"] == [], f"{result['name']}: 关键元素缺失 {result['missing']}"
    assert result["stuck"] == [], (
        f"{result['name']}: 容器停留在加载中/骨架态 {result['stuck']}"
    )
    # 资源错误如实汇报（不拦）：有则打印，供人工归类"可选依赖缺失"。
    if result["resource_errors"]:
        print(f"\n[{result['name']}] resource_errors（不拦，如实记录）: {result['resource_errors']}")


@pytest.mark.e2e
@pytest.mark.parametrize("spec", PAGE_SPECS, ids=lambda s: s["name"])
def test_page_no_break_1920(audit_browser, base_url, spec):
    """1920×1080：页面自身 JS 零错误 + 文档无水平溢出（破版检测），截图留证。"""
    result = _audit_page(
        audit_browser, base_url, spec,
        viewport={"width": 1920, "height": 1080}, suffix="1920x1080",
    )
    assert result["page_errors"] == [], f"{result['name']}: 页面自身 JS 错误 {result['page_errors']}"
    # 水平破版检测：文档滚动宽度不应超过视口宽度（容差 2px 抗亚像素）。
    assert result["overflow_px"] <= 2, (
        f"{result['name']}: 1920 档水平溢出 {result['overflow_px']}px（截图 {result['screenshot'].name}）"
    )


# ---------------------------------------------------------------------------
# 训练配置页联动（真实数据流：选机型 → 档案列表变化 → 机器人摘要刷新）
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_training_create_robot_profile_linkage(audit_browser, base_url):
    """选机型后档案下拉与「当前机器人」摘要随之刷新（前后端联动证据）。"""
    context = audit_browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    try:
        page.goto(f"{base_url}/web/training_create.html?v=0.44.0", wait_until="domcontentloaded")
        page.wait_for_selector(
            "#robotSelect option[value]:not([value=''])", state="attached", timeout=20_000
        )
        options = page.eval_on_selector_all(
            "#robotSelect option", "els => els.map(e => ({v: e.value, t: e.textContent}))"
        )
        assert len(options) >= 1, "机型下拉没有可用机器人"

        first = options[0]["v"]
        second = options[1]["v"] if len(options) > 1 else None
        page.select_option("#robotSelect", first)
        page.wait_for_timeout(600)
        meta_first = page.inner_text("#robotMetaBox")
        profiles_first = page.eval_on_selector_all(
            "#profileSelect option", "els => els.map(e => e.value)"
        )
        assert meta_first.strip() not in ("", "-"), "选机型后机器人摘要框未刷新"

        if second:
            page.select_option("#robotSelect", second)
            page.wait_for_timeout(600)
            meta_second = page.inner_text("#robotMetaBox")
            profiles_second = page.eval_on_selector_all(
                "#profileSelect option", "els => els.map(e => e.value)"
            )
            assert meta_second != meta_first or profiles_second != profiles_first, (
                "切换机型后档案列表与机器人摘要均无变化（联动断）"
            )
        assert page_errors == [], f"联动过程中页面 JS 错误：{page_errors}"
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 训练列表交互（汇总卡点击即筛选）
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_training_list_summary_filter_linkage(audit_browser, base_url):
    """汇总卡点击 → filterStatus 同步；表格渲染出列表/空态/错误态之一。"""
    context = audit_browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    try:
        page.goto(f"{base_url}/web/training_list.html?v=0.44.0", wait_until="domcontentloaded")
        _wait_settled(page, ["#tableBody"])
        page.click('.summary-card[data-filter="completed"]')
        page.wait_for_timeout(200)
        assert page.input_value("#filterStatus") == "completed", "汇总卡点击未同步状态筛选"
        assert page_errors == [], f"交互过程中页面 JS 错误：{page_errors}"
    finally:
        context.close()
